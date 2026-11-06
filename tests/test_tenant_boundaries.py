import json

import pytest
from fastapi.testclient import TestClient

from knowledge_manager.http_server import create_app
from knowledge_manager.mcp_server import create_server
from knowledge_manager.schemas import (
    Index,
    Module,
    ModuleContent,
    ModuleMetadata,
    StagingMeta,
)
from knowledge_manager.storage import (
    generate_ops_report,
    load_module,
    save_index,
    save_module,
    save_staging_meta,
    save_to_staging,
    search_modules,
)
from knowledge_manager.tenancy import TenantContext


def decode(result):
    if isinstance(result, tuple):
        result = result[0]
    return json.loads(next(block.text for block in result if hasattr(block, "text")))


@pytest.fixture
def scoped_kb(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="Tenant regression"), kb)
    (kb / "config.json").write_text(
        json.dumps({"security": {"multi_tenant_mode": True}}), encoding="utf-8"
    )
    tokens = {
        "a": {"sub": "alice", "tenant_id": "a", "workspace_id": "one"},
        "b": {"sub": "bob", "tenant_id": "b", "workspace_id": "one"},
    }
    (kb / "auth.json").write_text(
        json.dumps({"provider": "token", "oidc_config": {"static_tokens": tokens}}),
        encoding="utf-8",
    )
    (kb / "rbac.json").write_text(
        json.dumps({"users": {"alice": "reviewer", "bob": "reviewer"}}), encoding="utf-8"
    )
    for name, tenant, workspace, status in [
        ("visible", "a", "one", "published"),
        ("foreign", "b", "one", "draft"),
        ("workspace", "a", "two", "archived"),
        ("shared", "a", "", "published"),
    ]:
        module = Module(
            id=name,
            category="ops",
            title=f"Authentication {name}",
            summary="Authentication guidance for operators.",
            content=ModuleContent(
                overview="Authentication policy overview.",
                details=f"Confidential body for {name}, with enough length for validation.",
            ),
            metadata=ModuleMetadata(
                tenant_id=tenant,
                workspace_id=workspace,
                status=status,
                related_modules=(
                    ["ops/foreign", "ops/workspace", "ops/shared"] if name == "visible" else []
                ),
            ),
        )
        save_module(module, kb)
        if name != "shared":
            save_to_staging(module, kb / ".staging")
            save_staging_meta(
                StagingMeta(
                    module_id=name,
                    status="pending" if name == "visible" else "changes-requested",
                ),
                kb / ".staging",
            )
    return kb


@pytest.mark.parametrize("suffix", ["", ".md"])
def test_http_workspace_detail_is_hidden_even_with_markdown_file(scoped_kb, suffix):
    (scoped_kb / "ops" / "workspace.md").write_text("SECRET", encoding="utf-8")
    client = TestClient(create_app(scoped_kb))
    response = client.get(
        f"/api/modules/ops/workspace{suffix}", headers={"Authorization": "Bearer a"}
    )
    assert response.status_code == 404
    assert "SECRET" not in response.text


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_review_denies_foreign_workspace_and_audits(scoped_kb, action):
    client = TestClient(create_app(scoped_kb))
    response = client.post(
        f"/api/staging/workspace/{action}",
        headers={"Authorization": "Bearer a", "X-Request-ID": "workspace-denial"},
        json={"comment": "must be denied"},
    )
    assert response.status_code == 404
    events = [
        json.loads(line)
        for line in (scoped_kb / ".audit" / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert any(
        event["operation"] == "authz.denied"
        and event["user"] == "alice"
        and event["tenant_id"] == "a"
        and event["request_id"] == "workspace-denial"
        for event in events
    )


@pytest.mark.parametrize("query", ["auth", "authentication"])
def test_storage_search_filters_workspace_and_companions(scoped_kb, query):
    config_path = scoped_kb / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["routing_policy"] = {"mandatory_companions": {"ops": ["ops/foreign", "ops/workspace"]}}
    config_path.write_text(json.dumps(config), encoding="utf-8")
    results = search_modules(
        query,
        scoped_kb,
        include_archived=True,
        tenant=TenantContext(tenant_id="a", workspace_id="one", allow_global_reads=False),
    )
    assert {r.module.id for r in results} == {"visible", "shared"}


@pytest.mark.parametrize("warmup", ["none", "global", "a", "b"])
def test_ops_scope_is_independent_of_cache_request_order(scoped_kb, warmup):
    client = TestClient(create_app(scoped_kb))
    if warmup == "global":
        generate_ops_report(scoped_kb)
    elif warmup != "none":
        assert (
            client.get("/api/ops", headers={"Authorization": f"Bearer {warmup}"}).status_code == 200
        )
    for token, counts, staging in [
        ("a", {"published": 2}, {"pending": 1}),
        ("b", {"draft": 1}, {"changes-requested": 1}),
        ("a", {"published": 2}, {"pending": 1}),
    ]:
        response = client.get("/api/ops", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["lifecycle_backlog"] == {
            "status_counts": counts,
            "staging_status_counts": staging,
        }
    global_report = generate_ops_report(scoped_kb)
    assert global_report.lifecycle_backlog.status_counts == {
        "published": 2,
        "draft": 1,
        "archived": 1,
    }
    assert global_report.lifecycle_backlog.staging_status_counts == {
        "pending": 1,
        "changes-requested": 2,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool", ["search_modules", "deep_search", "load_module", "expand_module", "knowledge_graph"]
)
async def test_mcp_filters_hidden_references_without_mutating_storage(scoped_kb, tool):
    server = create_server(
        scoped_kb, session_tenant=TenantContext(tenant_id="a", workspace_id="one")
    )
    args = (
        {"module_id": "visible", "category": "ops"}
        if tool in {"load_module", "expand_module"}
        else {"query": "authentication"}
    )
    result = decode(await server.call_tool(tool, args))
    raw = json.dumps(result)
    assert "foreign" not in raw
    assert "workspace" not in raw.replace('"workspace_id"', '"scope"')
    assert "shared" in raw or tool == "expand_module"
    assert load_module("visible", "ops", scoped_kb).metadata.related_modules == [
        "ops/foreign",
        "ops/workspace",
        "ops/shared",
    ]


@pytest.mark.asyncio
async def test_mcp_load_cache_does_not_bypass_workspace(scoped_kb):
    from knowledge_manager.cache import ModuleCache

    cache = ModuleCache()
    wide = create_server(scoped_kb, cache=cache)
    await wide.call_tool("load_module", {"module_id": "workspace", "category": "ops"})
    scoped = create_server(
        scoped_kb, cache=cache, session_tenant=TenantContext(tenant_id="a", workspace_id="one")
    )
    result = await scoped.call_tool("load_module", {"module_id": "workspace", "category": "ops"})
    assert "Confidential body" not in str(result)
    assert "not found" in str(result).lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["update_module", "delete_module"])
@pytest.mark.parametrize("module_id", ["foreign", "workspace"])
async def test_mcp_writes_cannot_modify_hidden_modules(scoped_kb, tool, module_id):
    before = load_module(module_id, "ops", scoped_kb).model_dump()
    server = create_server(
        scoped_kb, session_tenant=TenantContext(tenant_id="a", workspace_id="one")
    )
    args = {"module_id": module_id, "category": "ops"}
    if tool == "update_module":
        args["title"] = "Forbidden update"
    result = decode(await server.call_tool(tool, args))
    assert "not found" in result.get("error", "").lower()
    assert load_module(module_id, "ops", scoped_kb).model_dump() == before
    events = [
        json.loads(line)
        for line in (scoped_kb / ".audit" / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert any(
        e["operation"] == "authz.denied"
        and e["tenant_id"] == "a"
        and e["resource"] == f"ops/{module_id}"
        for e in events
    )


@pytest.mark.asyncio
async def test_mcp_create_stamps_trusted_scope(scoped_kb):
    from knowledge_manager.storage import list_staging

    server = create_server(
        scoped_kb, session_tenant=TenantContext(tenant_id="a", workspace_id="one")
    )
    result = decode(
        await server.call_tool(
            "create_module",
            {
                "title": "Scoped module",
                "content": "A scoped module containing sufficient content.",
            },
        )
    )
    staged = next(m for m in list_staging(scoped_kb / ".staging") if m.id == result["module_id"])
    assert staged.metadata.tenant_id == "a"
    assert staged.metadata.workspace_id == "one"


@pytest.mark.asyncio
async def test_federated_search_uses_trusted_scope(scoped_kb):
    server = create_server(
        scoped_kb,
        session_tenant=TenantContext(tenant_id="a", workspace_id="one"),
        federation={"other": {"path": scoped_kb, "search_default": True}},
    )
    result = decode(await server.call_tool("federated_search", {"query": "authentication"}))
    assert {m["id"] for m in result["results"]["other"]} == {"visible", "shared"}
    assert "foreign" not in json.dumps(result)


@pytest.mark.parametrize("allow_global", [False, True])
def test_workspace_and_explicit_global_read_semantics(scoped_kb, allow_global):
    from knowledge_manager.tenancy import scope_visible_to_tenant

    tenant = TenantContext(tenant_id="a", workspace_id="one", allow_global_reads=allow_global)
    assert scope_visible_to_tenant("a", "", tenant)
    assert scope_visible_to_tenant("a", "one", tenant)
    assert not scope_visible_to_tenant("a", "two", tenant)
    assert scope_visible_to_tenant("", "", tenant) == allow_global
    assert not scope_visible_to_tenant("b", "one", tenant)


@pytest.mark.asyncio
@pytest.mark.parametrize("resource", ["index", "ops"])
async def test_mcp_resources_enforce_configured_global_read_policy(scoped_kb, resource):
    module = load_module("shared", "ops", scoped_kb)
    module.id = "global-secret"
    module.metadata.tenant_id = ""
    save_module(module, scoped_kb)
    server = create_server(
        scoped_kb, session_tenant=TenantContext(tenant_id="a", workspace_id="one")
    )
    result = await server.read_resource(f"knowledge://{resource}")
    payload = json.loads(next(block.content for block in result))
    if resource == "ops":
        assert payload["lifecycle_backlog"]["status_counts"] == {"published": 2}
    else:
        assert "global-secret" not in json.dumps(payload)


def test_ops_source_stale_counts_use_module_scope(scoped_kb):
    from knowledge_manager.schemas import (
        ConfluenceSourceConfig,
        SourceDefinition,
        SourceDocumentRef,
    )
    from knowledge_manager.source_ingestion import upsert_source

    for source_id, workspace in [("shared-source", ""), ("hidden-source", "two")]:
        upsert_source(
            SourceDefinition(
                id=source_id,
                tenant_id="a",
                workspace_id=workspace,
                confluence=ConfluenceSourceConfig(
                    base_url="https://example.com",
                    space_key="OPS",
                    email="ops@example.com",
                    api_token_env="TEST_TOKEN",
                ),
            ),
            scoped_kb,
        )
    for module_id in ["visible", "foreign", "workspace"]:
        module = load_module(module_id, "ops", scoped_kb)
        module.metadata.stale_due_to_source_change = True
        module.metadata.source_documents = [
            SourceDocumentRef(
                source_id="shared-source",
                source_type="confluence",
                external_id=module_id,
                title=module.title,
            )
        ]
        save_module(module, scoped_kb)
    report = generate_ops_report(
        scoped_kb, tenant=TenantContext(tenant_id="a", workspace_id="one", allow_global_reads=False)
    )
    assert [(s.source_id, s.stale_module_count) for s in report.source_backlog] == [
        ("shared-source", 1)
    ]


@pytest.mark.asyncio
async def test_multi_tenant_omits_unscoped_lint_and_namespace_resources(scoped_kb):
    server = create_server(
        scoped_kb,
        session_tenant=TenantContext(tenant_id="a", workspace_id="one"),
        federation={"other": {"path": scoped_kb, "search_default": True}},
    )
    uris = {str(resource.uri) for resource in await server.list_resources()}
    assert "knowledge://lint" not in uris
    assert not any(
        uri.startswith("knowledge://other/") or uri == "knowledge://federation/index"
        for uri in uris
    )
