"""Read-only application audit using an isolated synthetic knowledge base."""
import asyncio
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from fastapi.testclient import TestClient
from knowledge_manager.http_server import create_app
from knowledge_manager.mcp_server import create_server
from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata, StagingMeta
from knowledge_manager.storage import save_index, save_module, save_to_staging, save_staging_meta, generate_ops_report
from knowledge_manager.materialized_views import invalidate_materialized_views
from knowledge_manager.tenancy import TenantContext


def module(name, tenant, workspace, status="published", related=None):
    return Module(id=name, category="ops", title=f"Authentication {name}",
                  summary="Authentication guidance for operators.",
                  content=ModuleContent(overview="Authentication policy overview.",
                                        details=f"Unique confidential body for {name}, with enough validation content."),
                  metadata=ModuleMetadata(tenant_id=tenant, workspace_id=workspace,
                                          status=status, related_modules=related or []))


def decode(result):
    if isinstance(result, tuple):
        result = result[0]
    return json.loads(next(item.text for item in result if hasattr(item, "text")))


async def main():
    with tempfile.TemporaryDirectory(prefix="km-tenant-audit-", dir=ROOT.parent / "km-install-temp") as temp:
        kb = Path(temp)
        save_index(Index(description="synthetic audit"), kb)
        (kb / "config.json").write_text(json.dumps({
            "security": {"multi_tenant_mode": True},
            "routing_policy": {"risk_level_allowed_statuses": {"high": ["published"]}}
        }), encoding="utf-8")
        (kb / "auth.json").write_text(json.dumps({"provider": "token", "oidc_config": {"static_tokens": {
            "a": {"sub": "reviewer-a", "tenant_id": "team-a", "workspace_id": "ws-a"},
            "b": {"sub": "reviewer-b", "tenant_id": "team-b", "workspace_id": "ws-b"}
        }}}), encoding="utf-8")
        (kb / "rbac.json").write_text(json.dumps({"users": {"reviewer-a": "reviewer", "reviewer-b": "reviewer"}}), encoding="utf-8")
        for item in [module("visible-a", "team-a", "ws-a", related=["ops/hidden-b"]),
                     module("hidden-b", "team-b", "ws-b", "draft"),
                     module("other-workspace", "team-a", "ws-other")]:
            save_module(item, kb)
        for name, tenant, workspace, status in [("stage-a", "team-a", "ws-a", "pending"),
                                                ("stage-b", "team-b", "ws-b", "changes-requested")]:
            save_to_staging(module(name, tenant, workspace), kb / ".staging")
            save_staging_meta(StagingMeta(module_id=name, status=status), kb / ".staging")

        client = TestClient(create_app(kb))
        headers = {"Authorization": "Bearer a"}
        output = {}
        invalidate_materialized_views(kb)
        output["cold_ops_a"] = client.get("/api/ops", headers=headers).json()
        output["after_a_ops_b"] = client.get("/api/ops", headers={"Authorization": "Bearer b"}).json()
        output["global_after_tenant"] = generate_ops_report(kb).model_dump(mode="json")
        invalidate_materialized_views(kb)
        generate_ops_report(kb)
        output["global_warmed_ops_a"] = client.get("/api/ops", headers=headers).json()
        output["same_tenant_other_workspace_detail"] = {
            "status": client.get("/api/modules/ops/other-workspace", headers=headers).status_code}
        output["workspace_override"] = {
            "status": client.get("/api/ops?workspace_id=ws-other", headers=headers).status_code}
        server = create_server(kb, session_tenant=TenantContext(tenant_id="team-a", workspace_id="ws-a"))
        output["mcp_deep_search"] = decode(await server.call_tool("deep_search", {"query": "Authentication"}))
        output["mcp_search"] = decode(await server.call_tool("search_modules", {"query": "Authentication"}))
        output["mcp_workspace_load"] = decode(await server.call_tool("load_module", {
            "module_id": "other-workspace", "category": "ops"}))
        forged = client.post("/api/staging/stage-a/approve", headers=headers, json={"reviewer": "forged"})
        output["forged_reviewer"] = {"status": forged.status_code, "body": forged.json()}
        approved = client.post("/api/staging/stage-a/approve", headers=headers, json={"comment": "actual reviewer"})
        output["authenticated_approval"] = {"status": approved.status_code, "body": approved.json()}
        output["audit"] = [json.loads(line) for line in (kb / ".audit" / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
        output["source_head"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        output["source_sha256"] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in (ROOT / "src" / "knowledge_manager").glob("*.py")}
        (Path(__file__).parent / "probe.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"cold_ops_a": output["cold_ops_a"]["lifecycle_backlog"],
                          "after_a_ops_b": output["after_a_ops_b"]["lifecycle_backlog"],
                          "global_after_tenant": output["global_after_tenant"]["lifecycle_backlog"],
                          "global_warmed_ops_a": output["global_warmed_ops_a"]["lifecycle_backlog"],
                          "workspace_detail": output["same_tenant_other_workspace_detail"],
                          "workspace_override": output["workspace_override"],
                          "mcp_ids": [r["id"] for r in output["mcp_deep_search"]],
                          "mcp_related": output["mcp_deep_search"][0]["related_modules"],
                          "forged_reviewer": output["forged_reviewer"],
                          "authenticated_approval": output["authenticated_approval"]}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
