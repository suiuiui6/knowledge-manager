import json
import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata
from knowledge_manager.storage import load_module, save_module, save_index


def make_module(id="auth-jwt", category="auth") -> Module:
    return Module(
        id=id, category=category,
        title="JWT Authentication Guide",
        summary="How JWT tokens work in our system for authentication",
        content=ModuleContent(
            overview="JWT tokens are used for stateless authentication",
            details="Tokens are signed with RS256 and expire after 24 hours",
        ),
    )


@pytest.fixture
def kb_path(tmp_path):
    path = tmp_path / "kb"
    path.mkdir()
    return path


@pytest.fixture
def server(kb_path):
    from knowledge_manager.mcp_server import create_server
    return create_server(kb_path)


def test_server_creates_fastmcp_instance(server):
    from mcp.server.fastmcp import FastMCP
    assert isinstance(server, FastMCP)


@pytest.mark.asyncio
async def test_resource_index_returns_json(server, kb_path):
    index = Index(description="Test KB")
    module = make_module()
    index.add_module(module)
    save_index(index, kb_path)

    result = await server.read_resource("knowledge://index")
    content = result[0].content if hasattr(result[0], "content") else str(result[0])
    data = json.loads(content)
    assert "categories" in data or "description" in data


@pytest.mark.asyncio
async def test_multi_tenant_mcp_disables_global_resources(kb_path):
    from knowledge_manager.mcp_server import create_server

    server = create_server(
        kb_path,
        session_tenant=None,
        security_mode="multi_tenant",
    )

    with pytest.raises(Exception):
        await server.read_resource("knowledge://index")


@pytest.mark.asyncio
async def test_tool_load_module_found(server, kb_path):
    module = make_module()
    save_module(module, kb_path)

    result = await server.call_tool("load_module", {"module_id": "auth-jwt", "category": "auth"})
    content = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert "JWT" in content


@pytest.mark.asyncio
async def test_tool_load_module_honors_tenant_filter(server, kb_path):
    module = Module(
        id="tenant-a",
        category="ops",
        title="Tenant A Guide",
        summary="Tenant A operational guidance.",
        content=ModuleContent(
            overview="Tenant A overview.",
            details="Tenant A details with enough length for validation.",
        ),
        metadata=ModuleMetadata(tenant_id="team-a"),
    )
    save_module(module, kb_path)

    result = await server.call_tool(
        "load_module",
        {"module_id": "tenant-a", "category": "ops", "tenant_id": "team-b"},
    )
    content = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert "not found" in content.lower()


@pytest.mark.asyncio
async def test_tool_load_module_rejects_cross_tenant_override_for_session(kb_path):
    from knowledge_manager.mcp_server import create_server
    from knowledge_manager.tenancy import TenantContext

    save_module(
        Module(
            id="tenant-a",
            category="ops",
            title="Tenant A Guide",
            summary="Tenant A operational guidance.",
            content=ModuleContent(
                overview="Tenant A overview.",
                details="Tenant A details with enough length for validation.",
            ),
            metadata=ModuleMetadata(tenant_id="team-a"),
        ),
        kb_path,
    )
    server = create_server(kb_path, session_tenant=TenantContext(tenant_id="team-a"))

    result = await server.call_tool(
        "load_module",
        {"module_id": "tenant-a", "category": "ops", "tenant_id": "team-b"},
    )
    content = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert "tenant override is not allowed" in content.lower()


@pytest.mark.asyncio
async def test_tool_load_module_not_found(server, kb_path):
    result = await server.call_tool("load_module", {"module_id": "missing", "category": "auth"})
    content = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert "not found" in content.lower()


@pytest.mark.asyncio
async def test_tool_search_modules(server, kb_path):
    save_module(make_module("auth-jwt", "auth"), kb_path)
    save_module(make_module("db-conn", "database"), kb_path)

    result = await server.call_tool("search_modules", {"query": "JWT authentication"})
    raw = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert "auth-jwt" in raw
    assert '"source": "direct"' in raw
    assert '"confidence": "medium"' in raw
    assert '"caveats"' in raw
    assert '"related_modules"' in raw
    assert '"policy_reasons"' in raw


@pytest.mark.asyncio
async def test_tool_search_modules_uses_compact_json_serialization(server, kb_path, monkeypatch):
    from knowledge_manager import mcp_server as mcp_module

    save_module(make_module("auth-jwt", "auth"), kb_path)
    captured: dict[str, object] = {}
    original_dumps = mcp_module.json.dumps

    def wrapped_dumps(*args, **kwargs):
        if "policy_reasons" in str(args[0]):
            captured["indent"] = kwargs.get("indent")
            captured["separators"] = kwargs.get("separators")
        return original_dumps(*args, **kwargs)

    monkeypatch.setattr(mcp_module.json, "dumps", wrapped_dumps)

    result = await server.call_tool("search_modules", {"query": "JWT authentication"})
    raw = result[0].text if hasattr(result[0], "text") else str(result[0])

    assert "auth-jwt" in raw
    assert captured["indent"] is None
    assert captured["separators"] == (",", ":")


@pytest.mark.asyncio
async def test_tool_search_modules_avoids_full_hydration_for_projection_hits(server, kb_path, monkeypatch):
    save_module(
        Module(
            id="auth-jwt",
            category="auth",
            title="JWT Authentication Guide",
            summary="Authentication guidance for stateless production tokens.",
            content=ModuleContent(
                overview="Stateless authentication overview for production tokens.",
                details="Detailed authentication guidance with signing, verification, and rollback steps.",
            ),
        ),
        kb_path,
    )

    def explode(*_args, **_kwargs):
        raise AssertionError("MCP search should not hydrate full modules for projection-backed hits")

    monkeypatch.setattr("knowledge_manager.storage.load_module", explode)
    monkeypatch.setattr("knowledge_manager.mcp_server.load_module", explode)

    result = await server.call_tool("search_modules", {"query": "authentication guide"})
    raw = result[0].text if hasattr(result[0], "text") else str(result[0])

    assert "auth-jwt" in raw
    assert '"snippet"' in raw


@pytest.mark.asyncio
async def test_tool_search_modules_honors_tenant_filter(server, kb_path):
    save_module(
        Module(
            id="tenant-a",
            category="ops",
            title="Rollback Guide A",
            summary="Tenant A rollback guidance.",
            content=ModuleContent(
                overview="Rollback safely for tenant A.",
                details="Tenant A rollback details with enough length for validation.",
            ),
            metadata=ModuleMetadata(tenant_id="team-a"),
        ),
        kb_path,
    )
    save_module(
        Module(
            id="tenant-b",
            category="ops",
            title="Rollback Guide B",
            summary="Tenant B rollback guidance.",
            content=ModuleContent(
                overview="Rollback safely for tenant B.",
                details="Tenant B rollback details with enough length for validation.",
            ),
            metadata=ModuleMetadata(tenant_id="team-b"),
        ),
        kb_path,
    )

    result = await server.call_tool("search_modules", {"query": "rollback safely", "tenant_id": "team-a"})
    raw = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert '"tenant-a"' in raw
    assert '"tenant-b"' not in raw


@pytest.mark.asyncio
async def test_tool_search_modules_accepts_agent_task_and_risk_inputs(server, kb_path):
    (kb_path / "config.json").write_text(
        json.dumps(
            {
                "routing_policy": {
                    "task_type_category_priorities": {"incident-response": ["runbook"]},
                    "risk_level_companions": {"high": ["policy/change-approval"]},
                }
            }
        ),
        encoding="utf-8",
    )
    save_module(
        Module(
            id="jwt-runbook",
            category="runbook",
            title="JWT incident runbook",
            summary="JWT incident response runbook.",
            content=ModuleContent(
                overview="JWT incident response overview.",
                details="JWT incident response details with enough length for validation.",
            ),
        ),
        kb_path,
    )
    save_module(
        Module(
            id="sensitive-rollout",
            category="runbook",
            title="Sensitive rollout workflow",
            summary="Sensitive rollout workflow for production updates.",
            content=ModuleContent(
                overview="Sensitive rollout workflow overview.",
                details="Sensitive rollout workflow details with enough length for validation.",
            ),
        ),
        kb_path,
    )
    save_module(
        Module(
            id="change-approval",
            category="policy",
            title="High-risk change approval",
            summary="Mandatory approval policy for high-risk changes.",
            content=ModuleContent(
                overview="High-risk approval overview.",
                details="High-risk approval details with enough length for validation.",
            ),
        ),
        kb_path,
    )

    result = await server.call_tool(
        "search_modules",
        {
            "query": "sensitive rollout workflow",
            "task_type": "incident-response",
            "risk_level": "high",
            "agent_id": "incident-agent",
        },
    )
    raw = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert '"sensitive-rollout"' in raw
    assert '"change-approval"' in raw
    assert '"risk_level:high"' in raw


@pytest.mark.asyncio
async def test_tool_explain_access_returns_scope_mismatch(server, kb_path):
    result = await server.call_tool(
        "explain_access",
        {
            "groups": ["grp-reviewers"],
            "category": "finance",
            "module_id": "fin-1",
            "roles": {"reviewer": {"permissions": ["module:read"], "scopes": ["category:policy"]}},
            "group_mapping": {"grp-reviewers": ["reviewer"]},
        },
    )
    raw = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert '"allowed": false' in raw.lower()
    assert "scope_mismatch" in raw


@pytest.mark.asyncio
async def test_tool_list_categories_honors_tenant_filter(server, kb_path):
    save_module(
        Module(
            id="tenant-a",
            category="ops",
            title="Tenant A Guide",
            summary="Tenant A operational guidance.",
            content=ModuleContent(
                overview="Tenant A overview.",
                details="Tenant A details with enough length for validation.",
            ),
            metadata=ModuleMetadata(tenant_id="team-a"),
        ),
        kb_path,
    )
    save_module(
        Module(
            id="tenant-b",
            category="finance",
            title="Tenant B Guide",
            summary="Tenant B finance guidance.",
            content=ModuleContent(
                overview="Tenant B overview.",
                details="Tenant B details with enough length for validation.",
            ),
            metadata=ModuleMetadata(tenant_id="team-b"),
        ),
        kb_path,
    )

    result = await server.call_tool("list_categories", {"tenant_id": "team-a"})
    raw = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert '"ops"' in raw
    assert '"finance"' not in raw


@pytest.mark.asyncio
async def test_session_tenant_ignores_caller_supplied_tenant_for_search(kb_path):
    from knowledge_manager.mcp_server import create_server
    from knowledge_manager.tenancy import TenantContext

    save_module(
        Module(
            id="tenant-a",
            category="ops",
            title="Rollback Guide A",
            summary="Tenant A rollback guidance.",
            content=ModuleContent(
                overview="Rollback safely for tenant A.",
                details="Tenant A rollback details with enough length for validation.",
            ),
            metadata=ModuleMetadata(tenant_id="team-a"),
        ),
        kb_path,
    )
    save_module(
        Module(
            id="tenant-b",
            category="ops",
            title="Rollback Guide B",
            summary="Tenant B rollback guidance.",
            content=ModuleContent(
                overview="Rollback safely for tenant B.",
                details="Tenant B rollback details with enough length for validation.",
            ),
            metadata=ModuleMetadata(tenant_id="team-b"),
        ),
        kb_path,
    )
    server = create_server(kb_path, session_tenant=TenantContext(tenant_id="team-a"))

    result = await server.call_tool(
        "search_modules",
        {"query": "rollback safely", "tenant_id": "team-a"},
    )
    raw = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert '"tenant-a"' in raw
    assert '"tenant-b"' not in raw


@pytest.mark.asyncio
async def test_tool_search_modules_filters_disallowed_statuses(server, kb_path):
    (kb_path / "config.json").write_text(
        json.dumps(
            {
                "routing_policy": {
                    "risk_level_allowed_statuses": {"high": ["published"]}
                }
            }
        ),
        encoding="utf-8",
    )
    save_module(
        Module(
            id="draft-runbook",
            category="ops",
            title="Sensitive rollout draft",
            summary="Sensitive rollout draft guidance.",
            content=ModuleContent(
                overview="Sensitive rollout draft overview.",
                details="Sensitive rollout draft details with enough length for validation.",
            ),
            metadata=ModuleMetadata(status="draft"),
        ),
        kb_path,
    )
    save_module(
        Module(
            id="published-runbook",
            category="ops",
            title="Sensitive rollout published",
            summary="Sensitive rollout published guidance.",
            content=ModuleContent(
                overview="Sensitive rollout published overview.",
                details="Sensitive rollout published details with enough length for validation.",
            ),
            metadata=ModuleMetadata(status="published"),
        ),
        kb_path,
    )

    result = await server.call_tool(
        "search_modules",
        {"query": "sensitive rollout", "risk_level": "high"},
    )
    raw = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert '"published-runbook"' in raw
    assert '"draft-runbook"' not in raw


@pytest.mark.asyncio
async def test_tool_list_categories(server, kb_path):
    save_module(make_module("auth-jwt", "auth"), kb_path)
    save_module(make_module("db-conn", "database"), kb_path)
    index = Index()
    index.add_module(make_module("auth-jwt", "auth"))
    index.add_module(make_module("db-conn", "database"))
    save_index(index, kb_path)

    result = await server.call_tool("list_categories", {})
    content = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert "auth" in content


@pytest.mark.asyncio
async def test_tool_expand_module_returns_module_and_neighbors(server, kb_path):
    from knowledge_manager.schemas import ModuleMetadata
    main = Module(
        id="jwt", category="auth",
        title="JWT tokens",
        summary="Handling JSON Web Tokens for auth",
        content=ModuleContent(
            overview="A JWT overview for testing expand",
            details="Detailed JWT notes for testing expand tool behavior",
        ),
        metadata=ModuleMetadata(tags=["auth"], related_modules=["auth/oauth-flow"]),
    )
    neighbor = Module(
        id="oauth-flow", category="auth",
        title="OAuth 2.0 flow",
        summary="OAuth 2.0 authorization flow setup",
        content=ModuleContent(
            overview="OAuth overview for expand testing",
            details="Detailed OAuth notes for testing expand tool behavior",
        ),
        metadata=ModuleMetadata(tags=["oauth"]),
    )
    save_module(main, kb_path)
    save_module(neighbor, kb_path)

    result = await server.call_tool("expand_module", {"module_id": "jwt", "category": "auth"})
    content = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert "jwt" in content
    assert "oauth-flow" in content


@pytest.mark.asyncio
async def test_tool_expand_module_honors_trusted_session_tenant(kb_path):
    from knowledge_manager.mcp_server import create_server
    from knowledge_manager.tenancy import TenantContext
    from knowledge_manager.schemas import ModuleMetadata

    main = Module(
        id="jwt", category="auth",
        title="JWT tokens",
        summary="Handling JSON Web Tokens for auth",
        content=ModuleContent(
            overview="A JWT overview for testing expand",
            details="Detailed JWT notes for testing expand tool behavior",
        ),
        metadata=ModuleMetadata(tags=["auth"], related_modules=["auth/oauth-flow"], tenant_id="team-a"),
    )
    neighbor = Module(
        id="oauth-flow", category="auth",
        title="OAuth 2.0 flow",
        summary="OAuth 2.0 authorization flow setup",
        content=ModuleContent(
            overview="OAuth overview for expand testing",
            details="Detailed OAuth notes for testing expand tool behavior",
        ),
        metadata=ModuleMetadata(tags=["oauth"], tenant_id="team-b"),
    )
    save_module(main, kb_path)
    save_module(neighbor, kb_path)
    server = create_server(kb_path, session_tenant=TenantContext(tenant_id="team-a"))

    result = await server.call_tool("expand_module", {"module_id": "jwt", "category": "auth"})
    content = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert "jwt" in content
    assert "oauth-flow" not in content


@pytest.mark.asyncio
async def test_tool_expand_module_not_found(server, kb_path):
    result = await server.call_tool("expand_module", {"module_id": "missing", "category": "auth"})
    content = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert "not found" in content.lower()


@pytest.mark.asyncio
async def test_tool_deep_search_returns_full_content(server, kb_path):
    from knowledge_manager.schemas import ModuleMetadata
    main = Module(
        id="auth-jwt", category="auth",
        title="JWT authentication module",
        summary="How JWT tokens work in our system",
        content=ModuleContent(
            overview="JWT tokens are used for stateless authentication in our system.",
            details="Tokens are signed with RS256 and expire after 24 hours by default.",
        ),
        metadata=ModuleMetadata(tags=["jwt"], related_modules=["auth/oauth-flow"]),
    )
    neighbor = Module(
        id="oauth-flow", category="auth",
        title="OAuth flow module",
        summary="OAuth authorization flow details",
        content=ModuleContent(
            overview="OAuth 2.0 flow for authentication delegation.",
            details="OAuth authorization code flow with PKCE extension for secure exchange.",
        ),
        metadata=ModuleMetadata(tags=["oauth"]),
    )
    save_module(main, kb_path)
    save_module(neighbor, kb_path)

    result = await server.call_tool("deep_search", {"query": "JWT authentication"})
    content = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert "auth-jwt" in content
    assert "details" in content  # Full content loaded
    assert "neighbors" in content  # Graph expanded
    assert "oauth-flow" in content  # Neighbor included


@pytest.mark.asyncio
async def test_tool_deep_search_honors_trusted_session_tenant(kb_path):
    from knowledge_manager.mcp_server import create_server
    from knowledge_manager.tenancy import TenantContext
    from knowledge_manager.schemas import ModuleMetadata

    main = Module(
        id="auth-jwt", category="auth",
        title="JWT authentication module",
        summary="How JWT tokens work in our system",
        content=ModuleContent(
            overview="JWT tokens are used for stateless authentication in our system.",
            details="Tokens are signed with RS256 and expire after 24 hours by default.",
        ),
        metadata=ModuleMetadata(tags=["jwt"], related_modules=["auth/oauth-flow"], tenant_id="team-a"),
    )
    neighbor = Module(
        id="oauth-flow", category="auth",
        title="OAuth flow module",
        summary="OAuth authorization flow details",
        content=ModuleContent(
            overview="OAuth 2.0 flow for authentication delegation.",
            details="OAuth authorization code flow with PKCE extension for secure exchange.",
        ),
        metadata=ModuleMetadata(tags=["oauth"], tenant_id="team-b"),
    )
    save_module(main, kb_path)
    save_module(neighbor, kb_path)
    server = create_server(kb_path, session_tenant=TenantContext(tenant_id="team-a"))

    result = await server.call_tool("deep_search", {"query": "JWT authentication"})
    content = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert "auth-jwt" in content
    assert "oauth-flow" not in content


@pytest.mark.asyncio
async def test_tool_deep_search_avoids_unnecessary_full_hydration(server, kb_path, monkeypatch):
    from knowledge_manager.schemas import ModuleMetadata

    main = Module(
        id="auth-jwt", category="auth",
        title="JWT authentication module",
        summary="Stateless authentication guidance for production tokens.",
        content=ModuleContent(
            overview="Stateless authentication overview for production tokens.",
            details="Detailed authentication guidance with signing, verification, and rollback steps.",
        ),
        metadata=ModuleMetadata(tags=["jwt"], related_modules=["auth/oauth-flow"]),
    )
    neighbor = Module(
        id="oauth-flow", category="auth",
        title="OAuth flow module",
        summary="OAuth authorization flow details",
        content=ModuleContent(
            overview="OAuth 2.0 flow for authentication delegation.",
            details="OAuth authorization code flow with PKCE extension for secure exchange.",
        ),
        metadata=ModuleMetadata(tags=["oauth"]),
    )
    save_module(main, kb_path)
    save_module(neighbor, kb_path)

    def explode(*_args, **_kwargs):
        raise AssertionError("deep_search should reuse projection-backed content instead of hydrating modules")

    monkeypatch.setattr("knowledge_manager.storage.load_module", explode)
    monkeypatch.setattr("knowledge_manager.mcp_server.load_module", explode)

    result = await server.call_tool("deep_search", {"query": "stateless authentication"})
    content = result[0].text if hasattr(result[0], "text") else str(result[0])

    assert "auth-jwt" in content
    assert "details" in content
    assert "neighbors" in content
    assert "oauth-flow" in content


@pytest.mark.asyncio
async def test_session_context_boosts_recently_loaded(server, kb_path):
    """Loading a module should boost it in subsequent searches within the session."""
    save_module(Module(
        id="mod-a", category="general",
        title="Zanzibar quick reference",
        summary="Quick reference for zanzibar topic",
        content=ModuleContent(
            overview="Zanzibar overview for session boost comparison.",
            details="Zanzibar details for mod-a — this module covers the basics.",
        ),
    ), kb_path)
    save_module(Module(
        id="mod-b", category="general",
        title="Zanzibar deep dive",
        summary="In-depth zanzibar module with details",
        content=ModuleContent(
            overview="Zanzibar overview for session boost testing.",
            details="Zanzibar details for mod-b — provides comprehensive coverage.",
        ),
    ), kb_path)

    # Load mod-b first
    await server.call_tool("load_module", {"module_id": "mod-b", "category": "general"})

    # Verify load succeeded
    load_result = await server.call_tool("load_module", {"module_id": "mod-b", "category": "general"})
    load_content = load_result[0].text if hasattr(load_result[0], "text") else str(load_result[0])
    assert "mod-b" in load_content, f"Load should succeed, got: {load_content[:200]}"

    # Search for a term both modules match — mod-b should rank first due to session boost
    result = await server.call_tool("search_modules", {"query": "zanzibar"})
    content = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert "mod-b" in content, f"Search should find mod-b, got: {content[:300]}"
    assert "mod-a" in content, f"Search should find mod-a, got: {content[:300]}"
    # mod-b should appear before mod-a (session boost applied after loading mod-b)
    assert content.index("mod-b") < content.index("mod-a"), \
        f"Session boost should rank loaded mod-b before mod-a"


# ── Phase 2C: MCP changelog resources ──


@pytest.mark.asyncio
async def test_resource_changelog_returns_json(server, kb_path):
    """knowledge://changelog should return valid JSON."""
    (kb_path / ".changelog").mkdir(exist_ok=True)
    from datetime import date
    changelog_file = kb_path / ".changelog" / f"{date.today().isoformat()}.json"
    changelog_file.write_text(json.dumps({
        "date": date.today().isoformat(),
        "commits": [{"hash": "abc1234", "author": "test", "message": "add module", "changes": {"added": ["test/mod"], "modified": [], "deleted": []}}],
    }))

    result = await server.read_resource("knowledge://changelog")
    content = result[0].content if hasattr(result[0], "content") else str(result[0])
    data = json.loads(content)
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["commits"][0]["hash"] == "abc1234"


@pytest.mark.asyncio
async def test_resource_changelog_module_specific(server, kb_path):
    """knowledge://changelog/<key> should return entries for a specific module."""
    (kb_path / ".changelog").mkdir(exist_ok=True)
    from datetime import date
    changelog_file = kb_path / ".changelog" / f"{date.today().isoformat()}.json"
    changelog_file.write_text(json.dumps({
        "date": date.today().isoformat(),
        "commits": [{"hash": "abc1234", "author": "test", "message": "add module", "changes": {"added": ["simplemod"], "modified": [], "deleted": []}}],
    }))

    # Simple key without slash for FastMCP template compatibility
    result = await server.read_resource("knowledge://changelog/simplemod")
    content = result[0].content if hasattr(result[0], "content") else str(result[0])
    data = json.loads(content)
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_resource_changelog_empty_when_missing(server, kb_path):
    """knowledge://changelog should return empty list when no changelogs exist."""
    result = await server.read_resource("knowledge://changelog")
    content = result[0].content if hasattr(result[0], "content") else str(result[0])
    data = json.loads(content)
    assert isinstance(data, list)
    assert len(data) == 0


# ── Phase 2D: archived/deprecated search filtering via MCP ──


@pytest.mark.asyncio
async def test_search_modules_excludes_archived_by_default(server, kb_path):
    """search_modules should exclude archived modules when include_archived=false."""
    from knowledge_manager.schemas import ModuleMetadata
    active = Module(
        id="active", category="test",
        title="Active Module",
        summary="An active test module for search",
        content=ModuleContent(overview="Active module overview for testing.", details="Details for active module that are long enough."),
        metadata=ModuleMetadata(status="published"),
    )
    archived = Module(
        id="archived", category="test",
        title="Archived Module",
        summary="An archived test module for search",
        content=ModuleContent(overview="Archived module overview for testing.", details="Details for archived module that are long enough."),
        metadata=ModuleMetadata(status="archived"),
    )
    save_module(active, kb_path)
    save_module(archived, kb_path)

    result = await server.call_tool("search_modules", {"query": "module"})
    content = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert "active" in content
    assert "archived" not in content


@pytest.mark.asyncio
async def test_search_modules_includes_archived_when_requested(server, kb_path):
    """search_modules should include archived modules when include_archived=true."""
    from knowledge_manager.schemas import ModuleMetadata
    active = Module(
        id="active2", category="test",
        title="Active Module 2",
        summary="Another active module for search",
        content=ModuleContent(overview="Active 2 overview for testing.", details="Details for active2 that are long enough."),
        metadata=ModuleMetadata(status="published"),
    )
    archived = Module(
        id="archived2", category="test",
        title="Archived Module 2",
        summary="Another archived module for search",
        content=ModuleContent(overview="Archived 2 overview for testing.", details="Details for archived2 that are long enough."),
        metadata=ModuleMetadata(status="archived"),
    )
    save_module(active, kb_path)
    save_module(archived, kb_path)

    result = await server.call_tool("search_modules", {"query": "module", "include_archived": True})
    content = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert "active2" in content
    assert "archived2" in content


# ── Phase 3A: MCP health resources ──


@pytest.mark.asyncio
async def test_resource_health_returns_report(server, kb_path):
    """knowledge://health should return health report JSON."""
    from knowledge_manager.storage import save_module, rebuild_index
    mod = make_module("h1", "auth")
    save_module(mod, kb_path)
    rebuild_index(kb_path)

    result = await server.read_resource("knowledge://health")
    content = result[0].content if hasattr(result[0], "content") else str(result[0])
    data = json.loads(content)
    assert "total_modules" in data
    assert data["total_modules"] == 1
    assert "overall_score" in data


@pytest.mark.asyncio
async def test_resource_health_module_specific(server, kb_path):
    """knowledge://health/<key> should return single module health (single-segment key)."""
    from knowledge_manager.storage import save_module, rebuild_index
    mod = make_module("h2mod", "auth")
    save_module(mod, kb_path)
    rebuild_index(kb_path)

    # Use a key without slash for FastMCP template compatibility
    result = await server.read_resource("knowledge://health/h2mod")
    content = result[0].content if hasattr(result[0], "content") else str(result[0])
    data = json.loads(content)
    # Single-segment key without slash won't parse as category/id → error expected
    assert "error" in data or "module_id" in data


@pytest.mark.asyncio
async def test_resource_health_empty_kb(server, kb_path):
    """knowledge://health on empty KB should return zero-count report."""
    result = await server.read_resource("knowledge://health")
    content = result[0].content if hasattr(result[0], "content") else str(result[0])
    data = json.loads(content)
    assert data["total_modules"] == 0


# ── Phase 3B: MCP stats resource ──


@pytest.mark.asyncio
async def test_resource_stats_returns_json(server, kb_path):
    """knowledge://stats should return usage statistics JSON."""
    (kb_path / ".telemetry").mkdir(exist_ok=True)

    result = await server.read_resource("knowledge://stats")
    content = result[0].content if hasattr(result[0], "content") else str(result[0])
    data = json.loads(content)
    assert "total_searches" in data
    assert "period_days" in data


# ── Phase 3C: knowledge_graph MCP tool ──


@pytest.mark.asyncio
async def test_tool_knowledge_graph_global(server, kb_path):
    """knowledge_graph without query should return global stats + clusters."""
    from knowledge_manager.storage import save_module, rebuild_index
    mod = make_module("kg1", "auth")
    mod.metadata.related_modules = ["db/kg2"]
    save_module(mod, kb_path)
    mod2 = make_module("kg2", "db")
    mod2.metadata.related_modules = ["auth/kg1"]
    save_module(mod2, kb_path)
    rebuild_index(kb_path)

    result = await server.call_tool("knowledge_graph", {})
    raw = result[0][0].text
    data = json.loads(raw)
    assert "stats" in data
    assert "clusters" in data


@pytest.mark.asyncio
async def test_tool_knowledge_graph_with_query(server, kb_path):
    """knowledge_graph with query should return related modules for matched modules."""
    from knowledge_manager.storage import save_module, rebuild_index
    mod = make_module("kg3", "auth")
    mod.metadata.related_modules = ["db/kg4"]
    save_module(mod, kb_path)
    mod2 = make_module("kg4", "db")
    save_module(mod2, kb_path)
    rebuild_index(kb_path)

    result = await server.call_tool("knowledge_graph", {"query": "JWT"})
    raw = result[0][0].text
    data = json.loads(raw)
    assert "query" in data
    assert "results" in data


@pytest.mark.asyncio
async def test_tool_knowledge_graph_honors_trusted_session_tenant(kb_path):
    from knowledge_manager.mcp_server import create_server
    from knowledge_manager.tenancy import TenantContext
    from knowledge_manager.storage import rebuild_index

    mod = Module(
        id="kg-team-a",
        category="auth",
        title="Tenant A JWT guide",
        summary="Tenant A JWT guidance",
        content=ModuleContent(
            overview="JWT tokens are used for tenant A.",
            details="Detailed tenant A JWT guidance with enough length for validation.",
        ),
        metadata=ModuleMetadata(tenant_id="team-a"),
    )
    mod2 = Module(
        id="kg-team-b",
        category="auth",
        title="Tenant B JWT guide",
        summary="Tenant B JWT guidance",
        content=ModuleContent(
            overview="JWT tokens are used for tenant B.",
            details="Detailed tenant B JWT guidance with enough length for validation.",
        ),
        metadata=ModuleMetadata(tenant_id="team-b"),
    )
    save_module(mod, kb_path)
    save_module(mod2, kb_path)
    rebuild_index(kb_path)
    server = create_server(kb_path, session_tenant=TenantContext(tenant_id="team-a"))

    result = await server.call_tool("knowledge_graph", {"query": "JWT", "tenant_id": "team-a"})
    raw = result[0][0].text
    assert "kg-team-a" in raw
    assert "kg-team-b" not in raw


# ── Phase 3D: knowledge://recommendations MCP resource ──


@pytest.mark.asyncio
async def test_resource_recommendations_returns_json(server, kb_path):
    """knowledge://recommendations should return recommendation report JSON."""
    from knowledge_manager.storage import save_module, rebuild_index
    mod = make_module("r1", "auth")
    save_module(mod, kb_path)
    rebuild_index(kb_path)

    result = await server.read_resource("knowledge://recommendations")
    content = result[0].content if hasattr(result[0], "content") else str(result[0])
    data = json.loads(content)
    assert "archive_candidates" in data
    assert "enrichment_needed" in data
    assert "suggested_links" in data
    assert "review_reminders" in data


@pytest.mark.asyncio
async def test_resource_recommendations_empty_kb(server, kb_path):
    """knowledge://recommendations on empty KB should return zero-count report."""
    result = await server.read_resource("knowledge://recommendations")
    content = result[0].content if hasattr(result[0], "content") else str(result[0])
    data = json.loads(content)
    assert data["archive_candidates"] == []
    assert data["enrichment_needed"] == []


@pytest.mark.asyncio
async def test_resource_ops_returns_json(server, kb_path):
    result = await server.read_resource("knowledge://ops")
    content = result[0].content if hasattr(result[0], "content") else str(result[0])
    data = json.loads(content)
    assert "source_backlog" in data
    assert "lifecycle_backlog" in data
    assert "policy_suppressed_modules" in data


@pytest.mark.asyncio
async def test_resource_dual_view_returns_json(server, kb_path):
    from knowledge_manager.schemas import ConfluenceSourceConfig, SourceDefinition
    from knowledge_manager.source_ingestion import upsert_source

    upsert_source(
        SourceDefinition(
            id="team-docs",
            confluence=ConfluenceSourceConfig(
                base_url="https://example.atlassian.net/wiki",
                space_key="ENG",
                email="docs@example.com",
                api_token_env="CONFLUENCE_API_TOKEN",
            ),
        ),
        kb_path,
    )
    save_module(make_module("auth-jwt", "auth"), kb_path)

    result = await server.read_resource("knowledge://dual-view")
    content = result[0].content if hasattr(result[0], "content") else str(result[0])
    data = json.loads(content)
    assert "sources" in data
    assert "modules" in data


@pytest.mark.asyncio
async def test_resource_ops_backlog_review_returns_json(server, kb_path):
    from knowledge_manager.schemas import Module, ModuleContent, StagingMeta
    from knowledge_manager.storage import save_staging_meta, save_to_staging

    staged = Module(
        id="review-me",
        category="ops",
        title="Review me",
        summary="Review me summary for operators.",
        content=ModuleContent(
            overview="Review me overview.",
            details="Review me details with enough length for validation.",
        ),
    )
    save_to_staging(staged, kb_path / ".staging")
    save_staging_meta(StagingMeta(module_id="review-me", status="pending"), kb_path / ".staging")

    result = await server.read_resource("knowledge://ops/backlog/review")
    content = result[0].content if hasattr(result[0], "content") else str(result[0])
    data = json.loads(content)
    assert data["total"] == 1
    assert data["items"][0]["module_id"] == "review-me"


@pytest.mark.asyncio
async def test_resource_ops_backlog_risky_misses_returns_json(server, kb_path):
    from knowledge_manager.storage import record_search_event

    record_search_event("deploy rollback", [], kb_path)

    result = await server.read_resource("knowledge://ops/backlog/risky-misses")
    content = result[0].content if hasattr(result[0], "content") else str(result[0])
    data = json.loads(content)
    assert data["total"] == 1
    assert data["items"][0]["query_terms"]


@pytest.mark.asyncio
async def test_resource_ops_backlog_source_returns_json(server, kb_path):
    from knowledge_manager.schemas import ConfluenceSourceConfig, SourceDefinition
    from knowledge_manager.source_ingestion import upsert_source

    upsert_source(
        SourceDefinition(
            id="team-docs",
            confluence=ConfluenceSourceConfig(
                base_url="https://example.atlassian.net/wiki",
                space_key="ENG",
                email="docs@example.com",
                api_token_env="CONFLUENCE_API_TOKEN",
            ),
        ),
        kb_path,
    )

    result = await server.read_resource("knowledge://ops/backlog/source")
    content = result[0].content if hasattr(result[0], "content") else str(result[0])
    data = json.loads(content)
    assert data["total"] == 1
    assert data["items"][0]["source_id"] == "team-docs"


# ── Phase 4B: Federation MCP tests ──


@pytest.fixture
def federated_server(tmp_path):
    """Create an MCP server with two federated namespaces."""
    from knowledge_manager.mcp_server import create_server
    from knowledge_manager.storage import save_module, rebuild_index, save_index
    from knowledge_manager.schemas import Index

    main_path = tmp_path / "main-kb"
    main_path.mkdir()
    save_index(Index(description="Main KB"), main_path)
    mod = make_module("main-mod", "general")
    save_module(mod, main_path)
    rebuild_index(main_path)

    ns_path = tmp_path / "team-auth-kb"
    ns_path.mkdir()
    save_index(Index(description="Auth team KB"), ns_path)
    ns_mod = make_module("auth-mod", "auth")
    ns_mod.title = "Auth Team Module"
    save_module(ns_mod, ns_path)
    rebuild_index(ns_path)

    federation = {
        "auth": {
            "index": load_index(ns_path),
            "path": ns_path,
            "description": "Auth team KB",
            "search_default": True,
        }
    }
    return create_server(main_path, federation=federation), main_path, ns_path


def load_index(path: Path):
    from knowledge_manager.storage import load_index as _load
    return _load(path)


@pytest.mark.asyncio
async def test_resource_federation_index(federated_server):
    """knowledge://federation/index should list all namespaces."""
    server, main_path, ns_path = federated_server

    result = await server.read_resource("knowledge://federation/index")
    content = result[0].content if hasattr(result[0], "content") else str(result[0])
    data = json.loads(content)
    assert "namespaces" in data
    assert "auth" in data["namespaces"]
    assert data["namespaces"]["auth"]["description"] == "Auth team KB"
    assert data["total_namespaces"] == 1


@pytest.mark.asyncio
async def test_tool_federated_search(federated_server):
    """federated_search should return results grouped by namespace."""
    server, main_path, ns_path = federated_server

    result = await server.call_tool("federated_search", {"query": "module", "top_per_ns": 3})
    raw = result[0][0].text
    data = json.loads(raw)
    assert "results" in data
    assert "auth" in data["results"]
    # auth namespace should have auth-mod
    auth_results = data["results"]["auth"]
    assert any("auth-mod" in str(r) for r in auth_results)


@pytest.mark.asyncio
async def test_tool_federated_search_avoids_full_hydration_for_projection_hits(federated_server, monkeypatch):
    server, main_path, ns_path = federated_server

    def explode(*_args, **_kwargs):
        raise AssertionError("federated search should not hydrate full modules for projection-backed hits")

    monkeypatch.setattr("knowledge_manager.storage.load_module", explode)
    monkeypatch.setattr("knowledge_manager.mcp_server.load_module", explode)

    result = await server.call_tool("federated_search", {"query": "authentication guide", "top_per_ns": 3})
    raw = result[0][0].text
    data = json.loads(raw)

    assert any("auth-mod" in str(r) for r in data["results"]["auth"])


@pytest.mark.asyncio
async def test_tool_search_modules_with_namespace(federated_server):
    """search_modules with namespace=auth should search the auth KB only."""
    server, main_path, ns_path = federated_server

    result = await server.call_tool("search_modules", {"query": "auth", "namespace": "auth"})
    raw = result[0][0].text
    data = json.loads(raw)
    assert any("auth-mod" in str(r) for r in data)


@pytest.mark.asyncio
async def test_tool_load_module_with_namespace(federated_server):
    """load_module with namespace=auth should load from the auth KB."""
    server, main_path, ns_path = federated_server

    result = await server.call_tool("load_module", {"module_id": "auth-mod", "category": "auth", "namespace": "auth"})
    raw = result[0][0].text
    assert "Auth Team Module" in raw


@pytest.mark.asyncio
async def test_tool_list_categories_with_namespace(federated_server):
    """list_categories with namespace should list the correct KB's categories."""
    server, main_path, ns_path = federated_server

    result = await server.call_tool("list_categories", {"namespace": "auth"})
    raw = result[0][0].text
    data = json.loads(raw)
    assert any(c["category"] == "auth" for c in data)


@pytest.mark.asyncio
async def test_research_tool_returns_json_error_or_result_instead_of_name_error(server, kb_path):
    result = await server.call_tool("research", {"query": "rollback workflow", "depth": "shallow"})
    raw = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert "_load_config_safe" not in raw


@pytest.mark.asyncio
async def test_research_tool_returns_success_payload_when_provider_is_configured(server, kb_path, monkeypatch):
    class FakeConfig:
        research = SimpleNamespace()

        def get_default_provider(self):
            return "fake", SimpleNamespace()

    class FakeResearcher:
        def __init__(self, kb_path, config, llm_client):
            self.kb_path = kb_path
            self.config = config
            self.llm_client = llm_client

        async def research(self, query, depth):
            return SimpleNamespace(
                query=query,
                answer_synthesis="Rollback answer",
                staged_ids=["stage-1"],
                sources_used=["source-1"],
                took_ms=12.5,
            )

    monkeypatch.setattr("knowledge_manager.mcp_server._load_config_safe", lambda _kb_path: FakeConfig())
    monkeypatch.setattr("knowledge_manager.llm_clients.create_client", lambda *_args, **_kwargs: object())
    monkeypatch.setattr("knowledge_manager.researcher.Researcher", FakeResearcher)

    result = await server.call_tool("research", {"query": "rollback workflow", "depth": "shallow"})
    raw = result[0].text if hasattr(result[0], "text") else str(result[0])

    assert '"temporary_answer": "Rollback answer"' in raw
    assert '"staged_modules": [' in raw


@pytest.mark.asyncio
async def test_tool_update_module_persists_changes(server, kb_path):
    save_module(make_module("auth-jwt", "auth"), kb_path)

    result = await server.call_tool(
        "update_module",
        {
            "module_id": "auth-jwt",
            "category": "auth",
            "summary": "Updated MCP summary for authentication guidance.",
        },
    )
    raw = result[0].text if hasattr(result[0], "text") else str(result[0])

    assert '"status": "updated"' in raw

    updated = load_module("auth-jwt", "auth", kb_path)
    assert updated is not None
    assert updated.summary == "Updated MCP summary for authentication guidance."


@pytest.mark.asyncio
async def test_tool_delete_module_archives_module(server, kb_path):
    save_module(make_module("auth-jwt", "auth"), kb_path)

    result = await server.call_tool(
        "delete_module",
        {
            "module_id": "auth-jwt",
            "category": "auth",
        },
    )
    raw = result[0].text if hasattr(result[0], "text") else str(result[0])

    assert '"status": "archived"' in raw

    archived = load_module("auth-jwt", "auth", kb_path)
    assert archived is not None
    assert archived.metadata.status == "archived"
