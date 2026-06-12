import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from knowledge_manager.http_server import create_app


@pytest.fixture
def client(tmp_path):
    kb = tmp_path / "test_kb"
    kb.mkdir()
    from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata
    from knowledge_manager.storage import save_index, save_module

    idx = Index(description="Test KB")
    save_index(idx, kb)

    mod = Module(
        id="test-mod", category="general", title="Test Module Title",
        summary="A test module for HTTP tests.",
        content=ModuleContent(overview="test overview content", details="test details content here"),
        metadata=ModuleMetadata(tags=["test", "api"], confidence="high", status="published"),
    )
    save_module(mod, kb)

    app = create_app(kb)
    return TestClient(app)


class TestHealth:
    def test_health_ok(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert "overall_score" in data
        assert "total_modules" in data


class TestTree:
    def test_tree_ok(self, client):
        r = client.get("/api/tree")
        assert r.status_code == 200
        data = r.json()
        assert data["type"] == "root"
        assert len(data["children"]) >= 0

    def test_tree_subtree(self, client):
        r = client.get("/api/tree/general/test-mod")
        assert r.status_code == 200
        data = r.json()
        assert data["type"] == "module"
        assert data["id"] == "general/test-mod"

    def test_tree_subtree_404(self, client):
        r = client.get("/api/tree/general/nonexistent")
        assert r.status_code == 404


class TestModules:
    def test_list_modules(self, client):
        r = client.get("/api/modules")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        assert "items" in data
        assert data["page"] == 1

    def test_list_modules_filter_category(self, client):
        r = client.get("/api/modules?category=general")
        assert r.status_code == 200
        data = r.json()
        assert all(m["category"] == "general" for m in data["items"])

    def test_list_modules_pagination(self, client):
        r = client.get("/api/modules?page=1&limit=1")
        assert r.status_code == 200
        data = r.json()
        assert data["limit"] == 1
        assert data["pages"] >= 1

    def test_list_modules_limit_validation(self, client):
        r = client.get("/api/modules?limit=999")
        assert r.status_code == 422

    def test_list_modules_honors_tenant_filter(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata
        from knowledge_manager.storage import save_index, save_module

        save_index(Index(description="Tenant KB"), kb)
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
            kb,
        )
        save_module(
            Module(
                id="tenant-b",
                category="ops",
                title="Tenant B Guide",
                summary="Tenant B operational guidance.",
                content=ModuleContent(
                    overview="Tenant B overview.",
                    details="Tenant B details with enough length for validation.",
                ),
                metadata=ModuleMetadata(tenant_id="team-b"),
            ),
            kb,
        )

        tenant_client = TestClient(create_app(kb))
        r = tenant_client.get("/api/modules?tenant_id=team-a")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == "tenant-a"

    def test_module_detail(self, client):
        r = client.get("/api/modules/general/test-mod")
        assert r.status_code == 200
        data = r.json()
        assert data["title"] == "Test Module Title"
        assert data["category"] == "general"

    def test_module_detail_404(self, client):
        r = client.get("/api/modules/general/nonexistent")
        assert r.status_code == 404

    def test_module_detail_honors_tenant_filter(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata
        from knowledge_manager.storage import save_index, save_module

        save_index(Index(description="Tenant Detail KB"), kb)
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
            kb,
        )

        tenant_client = TestClient(create_app(kb))
        r = tenant_client.get("/api/modules/ops/tenant-a?tenant_id=team-b")
        assert r.status_code == 404

    def test_module_md_available(self, client):
        r = client.get("/api/modules/general/test-mod.md")
        assert r.status_code == 200
        assert "text/markdown" in r.headers["content-type"]


class TestSearch:
    def test_search_ok(self, client):
        r = client.post("/api/search", json={"query": "test module", "top_k": 5})
        assert r.status_code == 200
        data = r.json()
        assert data["intent"] in ("how-to", "reference", "decision-record", "general")
        assert "results" in data
        assert "policy_reasons" in data["results"][0]

    def test_search_empty_query(self, client):
        r = client.post("/api/search", json={"query": ""})
        assert r.status_code == 422

    def test_search_category_filter(self, client):
        r = client.post("/api/search", json={"query": "test", "category": "general"})
        assert r.status_code == 200

    def test_search_honors_tenant_filter(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata
        from knowledge_manager.storage import save_index, save_module

        save_index(Index(description="Tenant Search KB"), kb)
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
            kb,
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
            kb,
        )

        tenant_client = TestClient(create_app(kb))
        r = tenant_client.post("/api/search", json={"query": "rollback safely", "tenant_id": "team-a"})
        assert r.status_code == 200
        data = r.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["id"] == "tenant-a"

    def test_search_accepts_agent_task_and_risk_policy_inputs(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        from knowledge_manager.schemas import Index, Module, ModuleContent
        from knowledge_manager.storage import save_index, save_module

        save_index(Index(description="Policy KB"), kb)
        (kb / "config.json").write_text(
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
            kb,
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
            kb,
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
            kb,
        )

        policy_client = TestClient(create_app(kb))
        r = policy_client.post(
            "/api/search",
            json={
                "query": "sensitive rollout workflow",
                "task_type": "incident-response",
                "risk_level": "high",
                "agent_id": "incident-agent",
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert data["results"][0]["id"] in {"jwt-runbook", "sensitive-rollout"}
        assert any(result["id"] == "change-approval" for result in data["results"])

    def test_search_filters_disallowed_statuses_from_policy(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata
        from knowledge_manager.storage import save_index, save_module

        save_index(Index(description="Policy KB"), kb)
        (kb / "config.json").write_text(
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
            kb,
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
            kb,
        )

        policy_client = TestClient(create_app(kb))
        r = policy_client.post(
            "/api/search",
            json={"query": "sensitive rollout", "risk_level": "high"},
        )

        assert r.status_code == 200
        ids = [result["id"] for result in r.json()["results"]]
        assert "published-runbook" in ids
        assert "draft-runbook" not in ids

    def test_access_explain_endpoint_returns_scope_mismatch(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        from knowledge_manager.schemas import Index
        from knowledge_manager.storage import save_index

        save_index(Index(description="Access explain KB"), kb)
        access_client = TestClient(create_app(kb))
        r = access_client.post(
            "/api/access/explain",
            json={
                "groups": ["grp-reviewers"],
                "category": "finance",
                "module_id": "fin-1",
                "roles": {"reviewer": {"permissions": ["module:read"], "scopes": ["category:policy"]}},
                "group_mapping": {"grp-reviewers": ["reviewer"]},
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["allowed"] is False
        assert "scope_mismatch" in data["reasons"]


class TestGraph:
    def test_graph_ok(self, client):
        r = client.get("/api/graph")
        assert r.status_code == 200
        data = r.json()
        assert "nodes" in data
        assert "edges" in data

    def test_graph_subgraph(self, client):
        r = client.get("/api/graph/general/test-mod")
        assert r.status_code == 200
        data = r.json()
        assert len(data["nodes"]) >= 1

    def test_graph_subgraph_404(self, client):
        r = client.get("/api/graph/general/nonexistent")
        assert r.status_code == 404


class TestFallback:
    def test_fallback_ui(self, client):
        r = client.get("/ui/fallback")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "Knowledge Manager" in r.text
        assert "htmx" in r.text.lower()

    def test_ui_redirects_to_fallback(self, client):
        r = client.get("/ui", follow_redirects=False)
        assert r.status_code in (200, 302, 307)


class TestRecommendations:
    def test_recommendations_ok(self, client):
        r = client.get("/api/recommendations")
        assert r.status_code == 200
        data = r.json()
        assert "archive_candidates" in data


class TestOps:
    def test_ops_report_ok(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata
        from knowledge_manager.storage import save_index, save_module

        save_index(Index(description="Ops KB"), kb)
        (kb / "config.json").write_text(
            json.dumps({"routing_policy": {"risk_level_allowed_statuses": {"high": ["published"]}}}),
            encoding="utf-8",
        )
        save_module(
            Module(
                id="draft-guide",
                category="ops",
                title="Draft guide",
                summary="Draft guide for operators.",
                content=ModuleContent(
                    overview="Draft guide overview.",
                    details="Draft guide details with enough length for validation.",
                ),
                metadata=ModuleMetadata(status="draft"),
            ),
            kb,
        )

        ops_client = TestClient(create_app(kb))
        r = ops_client.get("/api/ops")
        assert r.status_code == 200
        data = r.json()
        assert "source_backlog" in data
        assert "lifecycle_backlog" in data
        assert "policy_suppressed_modules" in data

    def test_ops_backlog_endpoint_returns_review_export(self, tmp_path):
        from knowledge_manager.schemas import Index, Module, ModuleContent, StagingMeta
        from knowledge_manager.storage import save_index, save_staging_meta, save_to_staging

        kb = tmp_path / "kb"
        kb.mkdir()
        save_index(Index(description="ops backlog"), kb)
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
        save_to_staging(staged, kb / ".staging")
        save_staging_meta(StagingMeta(module_id="review-me", status="pending"), kb / ".staging")

        ops_client = TestClient(create_app(kb))
        r = ops_client.get("/api/ops/backlog")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["module_id"] == "review-me"

    def test_ops_backlog_risky_misses_endpoint_returns_export(self, tmp_path):
        from knowledge_manager.schemas import Index
        from knowledge_manager.storage import record_search_event, save_index

        kb = tmp_path / "kb"
        kb.mkdir()
        save_index(Index(description="ops backlog risky"), kb)
        record_search_event("deploy rollback", [], kb)

        ops_client = TestClient(create_app(kb))
        r = ops_client.get("/api/ops/backlog/risky-misses")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["query_terms"]

    def test_ops_backlog_source_endpoint_returns_export(self, tmp_path):
        from knowledge_manager.schemas import ConfluenceSourceConfig, Index, SourceDefinition
        from knowledge_manager.source_ingestion import upsert_source
        from knowledge_manager.storage import save_index

        kb = tmp_path / "kb"
        kb.mkdir()
        save_index(Index(description="ops backlog source"), kb)
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
            kb,
        )

        ops_client = TestClient(create_app(kb))
        r = ops_client.get("/api/ops/backlog/source")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["source_id"] == "team-docs"

    def test_dual_view_endpoint_returns_projection(self, tmp_path):
        from knowledge_manager.schemas import (
            ConfluenceSourceConfig,
            Index,
            Module,
            ModuleContent,
            ModuleMetadata,
            SourceDefinition,
            SourceDocumentRef,
        )
        from knowledge_manager.source_ingestion import upsert_source
        from knowledge_manager.storage import save_index, save_module

        kb = tmp_path / "kb"
        kb.mkdir()
        save_index(Index(description="dual view"), kb)
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
            kb,
        )
        save_module(
            Module(
                id="mod-1",
                category="ops",
                title="Ops Runbook",
                summary="Ops runbook summary.",
                content=ModuleContent(
                    overview="Ops runbook overview.",
                    details="Ops runbook details with enough length for validation.",
                ),
                metadata=ModuleMetadata(
                    source_documents=[
                        SourceDocumentRef(
                            source_type="confluence",
                            source_id="team-docs",
                            external_id="page-1",
                            title="Runbook",
                        )
                    ]
                ),
            ),
            kb,
        )

        dual_client = TestClient(create_app(kb))
        r = dual_client.get("/api/dual-view")
        assert r.status_code == 200
        data = r.json()
        assert data["sources"][0]["source_id"] == "team-docs"
        assert data["modules"][0]["module_id"] == "ops/mod-1"

    def test_source_jobs_endpoint_returns_ingestion_jobs(self, tmp_path):
        from knowledge_manager.ingestion_jobs import create_ingestion_job
        from knowledge_manager.schemas import Index
        from knowledge_manager.storage import save_index

        kb = tmp_path / "kb"
        kb.mkdir()
        save_index(Index(description="jobs view"), kb)
        create_ingestion_job(kb, source_id="team-docs", trigger="manual")

        jobs_client = TestClient(create_app(kb))
        r = jobs_client.get("/api/source/jobs")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["source_id"] == "team-docs"

    def test_migrate_dry_run_endpoint_returns_summary(self, tmp_path):
        from knowledge_manager.schemas import Index
        from knowledge_manager.storage import save_index

        kb = tmp_path / "kb"
        kb.mkdir()
        save_index(Index(description="migration view"), kb)
        export_path = tmp_path / "legacy-export.json"
        export_path.write_text(
            json.dumps([{"id": "page-1", "title": "Runbook", "body": "rollback safely"}]),
            encoding="utf-8",
        )

        jobs_client = TestClient(create_app(kb))
        r = jobs_client.post(
            "/api/migrate/dry-run",
            json={"source_path": str(export_path), "source_kind": "llm_wiki"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["total_documents"] == 1
        assert data["creates"] == 1

    def test_migrate_dry_run_endpoint_returns_404_for_missing_source(self, tmp_path):
        from knowledge_manager.schemas import Index
        from knowledge_manager.storage import save_index

        kb = tmp_path / "kb"
        kb.mkdir()
        save_index(Index(description="migration missing source"), kb)

        jobs_client = TestClient(create_app(kb))
        r = jobs_client.post(
            "/api/migrate/dry-run",
            json={"source_path": str(tmp_path / "missing.json"), "source_kind": "llm_wiki"},
        )
        assert r.status_code == 404
        assert r.json()["detail"] == "migration source not found"

    def test_admin_dashboard_endpoint_returns_aggregates(self, tmp_path):
        from knowledge_manager.ingestion_jobs import create_ingestion_job
        from knowledge_manager.schemas import Index, Module, ModuleContent, StagingMeta
        from knowledge_manager.storage import save_index, save_staging_meta, save_to_staging

        kb = tmp_path / "kb"
        kb.mkdir()
        save_index(Index(description="admin dashboard"), kb)
        create_ingestion_job(kb, source_id="team-docs", trigger="manual")
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
        save_to_staging(staged, kb / ".staging")
        save_staging_meta(StagingMeta(module_id="review-me", status="pending"), kb / ".staging")

        dashboard_client = TestClient(create_app(kb))
        r = dashboard_client.get("/api/admin/dashboard")
        assert r.status_code == 200
        data = r.json()
        assert "ingestion_jobs" in data
        assert "review_backlog" in data
        assert "stale_sources" in data
        assert "eval_regressions" in data


class TestStats:
    def test_stats_ok(self, client):
        r = client.get("/api/stats")
        assert r.status_code == 200
        data = r.json()
        assert "total_searches" in data
