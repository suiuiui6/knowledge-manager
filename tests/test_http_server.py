import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from knowledge_manager.chat import ChatPipeline
from knowledge_manager.http_server import create_app


def _write_auth_fixture(kb: Path) -> None:
    (kb / "auth.json").write_text(
        json.dumps(
            {
                "provider": "token",
                "oidc_config": {
                    "static_tokens": {
                        "viewer-team-a": {"sub": "victor", "tenant_id": "team-a", "workspace_id": "ws-a"},
                        "reviewer-team-a": {"sub": "rachel", "tenant_id": "team-a", "workspace_id": "ws-a"},
                        "editor-team-a": {"sub": "alice", "tenant_id": "team-a", "workspace_id": "ws-a"},
                        "admin-team-a": {"sub": "ada", "tenant_id": "team-a", "workspace_id": "ws-a"},
                        "admin-root": {"sub": "root", "groups": ["admins"]},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (kb / "rbac.json").write_text(
        json.dumps(
            {
                "users": {
                    "victor": "viewer",
                    "rachel": "reviewer",
                    "alice": "editor",
                    "ada": "admin",
                    "root": "admin",
                }
            }
        ),
        encoding="utf-8",
    )


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

    def test_ready_reports_config_error_when_default_provider_missing(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        from knowledge_manager.schemas import Index
        from knowledge_manager.storage import save_index

        save_index(Index(description="ready"), kb)
        (kb / "config.json").write_text('{"llm_providers": {}}', encoding="utf-8")

        ready_client = TestClient(create_app(kb))
        response = ready_client.get("/api/ready")

        assert response.status_code == 503
        assert "default provider" in response.json()["reasons"][0].lower()

    def test_metrics_endpoint_returns_prometheus_text(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        from knowledge_manager.schemas import Index
        from knowledge_manager.storage import save_index

        save_index(Index(description="metrics"), kb)
        metrics_client = TestClient(create_app(kb))
        response = metrics_client.get("/api/metrics")

        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        assert "knowledge_manager_modules_total" in response.text

    def test_production_mode_without_auth_config_fails_closed(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        from knowledge_manager.schemas import Index
        from knowledge_manager.storage import save_index

        save_index(Index(description="secured"), kb)
        (kb / "config.json").write_text(
            json.dumps(
                {
                    "llm_providers": {"x": {"api_key": "k", "model": "m", "default": True}},
                    "security": {"production_mode": True},
                }
            ),
            encoding="utf-8",
        )

        secured_client = TestClient(create_app(kb))

        assert secured_client.get("/api/ready").status_code == 503
        assert secured_client.post(
            "/api/modules",
            json={
                "id": "ops-guide",
                "category": "ops",
                "title": "Ops Guide",
                "summary": "Ops guide summary.",
                "content": {
                    "overview": "Ops overview.",
                    "details": "Ops details long enough for validation.",
                },
                "submit_to_staging": False,
            },
        ).status_code == 503


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

    def test_tree_uses_authenticated_tenant_scope(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata
        from knowledge_manager.storage import save_index, save_module

        _write_auth_fixture(kb)
        save_index(Index(description="Tenant Tree KB"), kb)
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
        response = tenant_client.get("/api/tree", headers={"Authorization": "Bearer editor-team-a"})

        assert response.status_code == 200
        data = response.json()
        assert len(data["children"]) == 1
        assert data["children"][0]["children"][0]["id"] == "ops/tenant-a"


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

    def test_list_modules_uses_authenticated_tenant_scope(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata
        from knowledge_manager.storage import save_index, save_module

        _write_auth_fixture(kb)
        save_index(Index(description="Tenant Auth KB"), kb)
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
        response = tenant_client.get("/api/modules", headers={"Authorization": "Bearer editor-team-a"})

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == "tenant-a"

    def test_list_modules_rejects_non_admin_tenant_override(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        from knowledge_manager.schemas import Index
        from knowledge_manager.storage import save_index

        _write_auth_fixture(kb)
        save_index(Index(description="Tenant override"), kb)

        tenant_client = TestClient(create_app(kb))
        response = tenant_client.get(
            "/api/modules?tenant_id=team-b",
            headers={"Authorization": "Bearer editor-team-a"},
        )

        assert response.status_code == 403

    def test_list_modules_allows_admin_tenant_override(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata
        from knowledge_manager.storage import save_index, save_module

        _write_auth_fixture(kb)
        save_index(Index(description="Tenant override"), kb)
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
        response = tenant_client.get(
            "/api/modules?tenant_id=team-b",
            headers={"Authorization": "Bearer admin-root"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == "tenant-b"

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

    def test_module_detail_uses_authenticated_tenant_scope(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata
        from knowledge_manager.storage import save_index, save_module

        _write_auth_fixture(kb)
        save_index(Index(description="Tenant detail auth"), kb)
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
        response = tenant_client.get(
            "/api/modules/ops/tenant-b",
            headers={"Authorization": "Bearer editor-team-a"},
        )

        assert response.status_code == 404

    def test_module_md_available(self, client):
        r = client.get("/api/modules/general/test-mod.md")
        assert r.status_code == 200
        assert "text/markdown" in r.headers["content-type"]

    def test_module_create_does_not_require_full_rebuild(self, tmp_path, monkeypatch):
        from knowledge_manager.schemas import Index
        from knowledge_manager.storage import save_index

        kb = tmp_path / "kb"
        kb.mkdir()
        save_index(Index(description="write path"), kb)
        monkeypatch.setattr(
            "knowledge_manager.storage.rebuild_index",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("full rebuild should not run")),
        )

        write_client = TestClient(create_app(kb))
        r = write_client.post(
            "/api/modules",
            json={
                "id": "ops-guide",
                "category": "ops",
                "title": "Ops Guide",
                "summary": "Ops guide summary.",
                "content": {
                    "overview": "Ops guide overview.",
                    "details": "Ops guide details long enough for validation.",
                },
                "submit_to_staging": False,
            },
        )
        assert r.status_code == 200

    def test_module_create_endpoint_returns_maintenance_state(self, tmp_path):
        from knowledge_manager.schemas import Index
        from knowledge_manager.storage import save_index

        kb = tmp_path / "kb"
        kb.mkdir()
        save_index(Index(description="write maintenance"), kb)

        write_client = TestClient(create_app(kb))
        r = write_client.post(
            "/api/modules",
            json={
                "id": "perf-write",
                "category": "ops",
                "title": "Perf write",
                "summary": "summary text",
                "content": {"overview": "overview text", "details": "details long enough for validation"},
                "submit_to_staging": False,
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "created"
        assert data["maintenance"]["deferred"] is True
        assert data["id"] == "perf-write"

    def test_module_create_rejects_non_admin_tenant_override(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        from knowledge_manager.schemas import Index
        from knowledge_manager.storage import save_index

        _write_auth_fixture(kb)
        save_index(Index(description="write auth"), kb)

        write_client = TestClient(create_app(kb))
        response = write_client.post(
            "/api/modules",
            headers={"Authorization": "Bearer editor-team-a"},
            json={
                "id": "cross-tenant-write",
                "category": "ops",
                "title": "Cross tenant write",
                "summary": "Cross tenant write summary.",
                "content": {
                    "overview": "Cross tenant overview.",
                    "details": "Cross tenant details long enough for validation.",
                },
                "metadata": {"tenant_id": "team-b"},
                "submit_to_staging": False,
            },
        )

        assert response.status_code == 403

    def test_module_create_allows_admin_tenant_override(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        from knowledge_manager.schemas import Index
        from knowledge_manager.storage import save_index

        _write_auth_fixture(kb)
        save_index(Index(description="write auth"), kb)

        write_client = TestClient(create_app(kb))
        response = write_client.post(
            "/api/modules",
            headers={"Authorization": "Bearer admin-root"},
            json={
                "id": "admin-tenant-write",
                "category": "ops",
                "title": "Admin tenant write",
                "summary": "Admin tenant write summary.",
                "content": {
                    "overview": "Admin tenant overview.",
                    "details": "Admin tenant details long enough for validation.",
                },
                "metadata": {"tenant_id": "team-b"},
                "submit_to_staging": False,
            },
        )

        assert response.status_code == 200
        assert response.json()["metadata"]["tenant_id"] == "team-b"

    def test_module_update_and_delete_return_maintenance_state(self, tmp_path):
        from knowledge_manager.schemas import Index, Module, ModuleContent
        from knowledge_manager.storage import save_index, save_module

        kb = tmp_path / "kb"
        kb.mkdir()
        save_index(Index(description="write maintenance update"), kb)
        save_module(
            Module(
                id="perf-write",
                category="ops",
                title="Perf write",
                summary="summary text",
                content=ModuleContent(
                    overview="overview text",
                    details="details long enough for validation",
                ),
            ),
            kb,
            defer_noncritical=False,
        )

        write_client = TestClient(create_app(kb))
        update_response = write_client.put(
            "/api/modules/ops/perf-write",
            json={"summary": "updated summary text"},
        )
        delete_response = write_client.delete("/api/modules/ops/perf-write")

        assert update_response.status_code == 200
        assert update_response.json()["status"] == "updated"
        assert update_response.json()["maintenance"]["deferred"] is True
        assert delete_response.status_code == 200
        assert delete_response.json()["maintenance"]["deferred"] is True

    def test_module_update_rejects_non_admin_tenant_override(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata
        from knowledge_manager.storage import save_index, save_module

        _write_auth_fixture(kb)
        save_index(Index(description="write auth"), kb)
        save_module(
            Module(
                id="tenant-owned",
                category="ops",
                title="Tenant owned",
                summary="Tenant owned summary.",
                content=ModuleContent(
                    overview="Tenant owned overview.",
                    details="Tenant owned details long enough for validation.",
                ),
                metadata=ModuleMetadata(tenant_id="team-a"),
            ),
            kb,
            defer_noncritical=False,
        )

        write_client = TestClient(create_app(kb))
        response = write_client.put(
            "/api/modules/ops/tenant-owned",
            headers={"Authorization": "Bearer editor-team-a"},
            json={"metadata": {"tenant_id": "team-b"}},
        )

        assert response.status_code == 403

    def test_viewer_cannot_access_write_or_control_plane_routes(self, tmp_path):
        from knowledge_manager.schemas import Index
        from knowledge_manager.storage import save_index

        kb = tmp_path / "kb"
        kb.mkdir()
        _write_auth_fixture(kb)
        save_index(Index(description="secured"), kb)
        secured_client = TestClient(create_app(kb))
        headers = {"Authorization": "Bearer viewer-team-a"}

        assert secured_client.post(
            "/api/modules",
            headers=headers,
            json={
                "id": "viewer-write",
                "category": "ops",
                "title": "Viewer write",
                "summary": "Viewer write summary.",
                "content": {
                    "overview": "Viewer write overview.",
                    "details": "Viewer write details long enough for validation.",
                },
                "submit_to_staging": False,
            },
        ).status_code == 403
        assert secured_client.get("/api/staging", headers=headers).status_code == 403
        assert secured_client.get("/api/ops", headers=headers).status_code == 403

    def test_staging_approve_does_not_require_full_rebuild(self, tmp_path, monkeypatch):
        from knowledge_manager.schemas import Index, Module, ModuleContent, StagingMeta
        from knowledge_manager.storage import save_index, save_staging_meta, save_to_staging

        kb = tmp_path / "kb"
        kb.mkdir()
        save_index(Index(description="staging approve"), kb)
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
        monkeypatch.setattr(
            "knowledge_manager.storage.rebuild_index",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("full rebuild should not run")),
        )

        review_client = TestClient(create_app(kb))
        r = review_client.post("/api/staging/review-me/approve", json={"reviewer": "alice"})
        assert r.status_code == 200
        assert r.json()["status"] == "merged"

    def test_http_staging_rejects_forged_reviewer_identity(self, tmp_path):
        from knowledge_manager.schemas import Index, Module, ModuleContent, StagingMeta
        from knowledge_manager.storage import save_index, save_staging_meta, save_to_staging

        kb = tmp_path / "kb"
        kb.mkdir()
        _write_auth_fixture(kb)
        save_index(Index(description="secured"), kb)
        staged = Module(
            id="review-me",
            category="ops",
            title="Review me",
            summary="Review me summary for operators.",
            content=ModuleContent(
                overview="Review overview.",
                details="Review details long enough for validation.",
            ),
        )
        save_to_staging(staged, kb / ".staging")
        save_staging_meta(StagingMeta(module_id="review-me", status="pending"), kb / ".staging")

        secured_client = TestClient(create_app(kb))
        response = secured_client.post(
            "/api/staging/review-me/approve",
            headers={"Authorization": "Bearer reviewer-team-a"},
            json={"reviewer": "root", "comment": "forged identity"},
        )

        assert response.status_code == 422

    def test_staging_list_uses_authenticated_tenant_scope(self, tmp_path):
        from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata, StagingMeta
        from knowledge_manager.storage import save_index, save_staging_meta, save_to_staging

        kb = tmp_path / "kb"
        kb.mkdir()
        _write_auth_fixture(kb)
        save_index(Index(description="secured"), kb)
        staged_a = Module(
            id="review-a",
            category="ops",
            title="Review a",
            summary="Review a summary for operators.",
            content=ModuleContent(
                overview="Review a overview.",
                details="Review a details long enough for validation.",
            ),
            metadata=ModuleMetadata(tenant_id="team-a", workspace_id="ws-a"),
        )
        staged_b = Module(
            id="review-b",
            category="ops",
            title="Review b",
            summary="Review b summary for operators.",
            content=ModuleContent(
                overview="Review b overview.",
                details="Review b details long enough for validation.",
            ),
            metadata=ModuleMetadata(tenant_id="team-b", workspace_id="ws-b"),
        )
        save_to_staging(staged_a, kb / ".staging")
        save_to_staging(staged_b, kb / ".staging")
        save_staging_meta(StagingMeta(module_id="review-a", status="pending"), kb / ".staging")
        save_staging_meta(StagingMeta(module_id="review-b", status="pending"), kb / ".staging")

        secured_client = TestClient(create_app(kb))
        response = secured_client.get("/api/staging", headers={"Authorization": "Bearer reviewer-team-a"})

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["module_id"] == "review-a"

    def test_staging_approve_rejects_cross_tenant_module(self, tmp_path):
        from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata, StagingMeta
        from knowledge_manager.storage import save_index, save_staging_meta, save_to_staging

        kb = tmp_path / "kb"
        kb.mkdir()
        _write_auth_fixture(kb)
        save_index(Index(description="secured"), kb)
        staged_b = Module(
            id="review-b",
            category="ops",
            title="Review b",
            summary="Review b summary for operators.",
            content=ModuleContent(
                overview="Review b overview.",
                details="Review b details long enough for validation.",
            ),
            metadata=ModuleMetadata(tenant_id="team-b", workspace_id="ws-b"),
        )
        save_to_staging(staged_b, kb / ".staging")
        save_staging_meta(StagingMeta(module_id="review-b", status="pending"), kb / ".staging")

        secured_client = TestClient(create_app(kb))
        response = secured_client.post(
            "/api/staging/review-b/approve",
            headers={"Authorization": "Bearer reviewer-team-a"},
            json={"comment": "should not see cross tenant"},
        )

        assert response.status_code == 404


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

    def test_search_uses_authenticated_tenant_scope(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata
        from knowledge_manager.storage import save_index, save_module

        _write_auth_fixture(kb)
        save_index(Index(description="Tenant Search Auth KB"), kb)
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
        response = tenant_client.post(
            "/api/search",
            headers={"Authorization": "Bearer editor-team-a"},
            json={"query": "rollback safely"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["id"] == "tenant-a"
        assert data["tenant_id"] == "team-a"

    def test_search_rejects_non_admin_tenant_override(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        from knowledge_manager.schemas import Index
        from knowledge_manager.storage import save_index

        _write_auth_fixture(kb)
        save_index(Index(description="Tenant Search Override"), kb)

        tenant_client = TestClient(create_app(kb))
        response = tenant_client.post(
            "/api/search",
            headers={"Authorization": "Bearer editor-team-a"},
            json={"query": "rollback safely", "tenant_id": "team-b"},
        )

        assert response.status_code == 403

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

    def test_graph_uses_authenticated_tenant_scope(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata
        from knowledge_manager.storage import save_index, save_module

        _write_auth_fixture(kb)
        save_index(Index(description="Tenant Graph KB"), kb)
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
                metadata=ModuleMetadata(tenant_id="team-a", related_modules=["ops/tenant-b"]),
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
        response = tenant_client.get("/api/graph", headers={"Authorization": "Bearer editor-team-a"})

        assert response.status_code == 200
        data = response.json()
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["id"] == "ops/tenant-a"
        assert data["edges"] == []


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

    def test_recommendations_use_authenticated_tenant_scope(self, tmp_path, monkeypatch):
        kb = tmp_path / "kb"
        kb.mkdir()
        from knowledge_manager.schemas import (
            Index,
            Module,
            ModuleContent,
            ModuleMetadata,
            Recommendation,
            RecommendationReport,
            RecommendationType,
        )
        from knowledge_manager.storage import save_index, save_module

        _write_auth_fixture(kb)
        save_index(Index(description="Tenant Recommendations KB"), kb)
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

        monkeypatch.setattr(
            "knowledge_manager.tenant_views.generate_recommendations",
            lambda _kb: RecommendationReport(
                archive_candidates=[
                    Recommendation(
                        type=RecommendationType.ARCHIVE,
                        module_id="tenant-a",
                        category="ops",
                        title="Tenant A Guide",
                    ),
                    Recommendation(
                        type=RecommendationType.ARCHIVE,
                        module_id="tenant-b",
                        category="ops",
                        title="Tenant B Guide",
                    ),
                ]
            ),
        )

        tenant_client = TestClient(create_app(kb))
        response = tenant_client.get(
            "/api/recommendations",
            headers={"Authorization": "Bearer editor-team-a"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["archive_candidates"]) == 1
        assert data["archive_candidates"][0]["module_id"] == "tenant-a"


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

    def test_ops_report_uses_authenticated_tenant_scope(self, tmp_path):
        from knowledge_manager.schemas import ConfluenceSourceConfig, Index, Module, ModuleContent, ModuleMetadata, SourceDefinition
        from knowledge_manager.source_ingestion import upsert_source
        from knowledge_manager.storage import save_index, save_module

        kb = tmp_path / "kb"
        kb.mkdir()
        _write_auth_fixture(kb)
        save_index(Index(description="Ops KB"), kb)
        upsert_source(
            SourceDefinition(
                id="team-docs-a",
                tenant_id="team-a",
                workspace_id="ws-a",
                confluence=ConfluenceSourceConfig(
                    base_url="https://example.atlassian.net/wiki",
                    space_key="OPS",
                    email="ops@example.com",
                    api_token_env="CONFLUENCE_API_TOKEN",
                ),
            ),
            kb,
        )
        upsert_source(
            SourceDefinition(
                id="team-docs-b",
                tenant_id="team-b",
                workspace_id="ws-b",
                confluence=ConfluenceSourceConfig(
                    base_url="https://example.atlassian.net/wiki",
                    space_key="ENG",
                    email="eng@example.com",
                    api_token_env="CONFLUENCE_API_TOKEN",
                ),
            ),
            kb,
        )
        save_module(
            Module(
                id="draft-a",
                category="ops",
                title="Draft A",
                summary="Draft A for operators.",
                content=ModuleContent(
                    overview="Draft A overview.",
                    details="Draft A details with enough length for validation.",
                ),
                metadata=ModuleMetadata(status="draft", tenant_id="team-a", workspace_id="ws-a"),
            ),
            kb,
        )
        save_module(
            Module(
                id="draft-b",
                category="ops",
                title="Draft B",
                summary="Draft B for operators.",
                content=ModuleContent(
                    overview="Draft B overview.",
                    details="Draft B details with enough length for validation.",
                ),
                metadata=ModuleMetadata(status="draft", tenant_id="team-b", workspace_id="ws-b"),
            ),
            kb,
        )

        ops_client = TestClient(create_app(kb))
        r = ops_client.get("/api/ops", headers={"Authorization": "Bearer reviewer-team-a"})

        assert r.status_code == 200
        data = r.json()
        assert len(data["source_backlog"]) == 1
        assert data["source_backlog"][0]["source_id"] == "team-docs-a"
        assert len(data["policy_suppressed_modules"]) == 1
        assert data["policy_suppressed_modules"][0]["module_id"] == "draft-a"

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

    def test_ops_backlog_review_uses_authenticated_tenant_scope(self, tmp_path):
        from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata, StagingMeta
        from knowledge_manager.storage import save_index, save_staging_meta, save_to_staging

        kb = tmp_path / "kb"
        kb.mkdir()
        _write_auth_fixture(kb)
        save_index(Index(description="ops backlog"), kb)
        staged_a = Module(
            id="review-a",
            category="ops",
            title="Review a",
            summary="Review a summary for operators.",
            content=ModuleContent(
                overview="Review a overview.",
                details="Review a details with enough length for validation.",
            ),
            metadata=ModuleMetadata(tenant_id="team-a", workspace_id="ws-a"),
        )
        staged_b = Module(
            id="review-b",
            category="ops",
            title="Review b",
            summary="Review b summary for operators.",
            content=ModuleContent(
                overview="Review b overview.",
                details="Review b details with enough length for validation.",
            ),
            metadata=ModuleMetadata(tenant_id="team-b", workspace_id="ws-b"),
        )
        save_to_staging(staged_a, kb / ".staging")
        save_to_staging(staged_b, kb / ".staging")
        save_staging_meta(StagingMeta(module_id="review-a", status="pending"), kb / ".staging")
        save_staging_meta(StagingMeta(module_id="review-b", status="pending"), kb / ".staging")

        ops_client = TestClient(create_app(kb))
        r = ops_client.get("/api/ops/backlog", headers={"Authorization": "Bearer reviewer-team-a"})

        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["module_id"] == "review-a"

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

    def test_ops_backlog_risky_misses_requires_admin_when_auth_is_enabled(self, tmp_path):
        from knowledge_manager.schemas import Index
        from knowledge_manager.storage import record_search_event, save_index

        kb = tmp_path / "kb"
        kb.mkdir()
        _write_auth_fixture(kb)
        save_index(Index(description="ops backlog risky auth"), kb)
        record_search_event("deploy rollback", [], kb)

        ops_client = TestClient(create_app(kb))
        reviewer_response = ops_client.get(
            "/api/ops/backlog/risky-misses",
            headers={"Authorization": "Bearer reviewer-team-a"},
        )
        admin_response = ops_client.get(
            "/api/ops/backlog/risky-misses",
            headers={"Authorization": "Bearer admin-root"},
        )

        assert reviewer_response.status_code == 403
        assert admin_response.status_code == 200

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

    def test_ops_backlog_source_uses_authenticated_tenant_scope(self, tmp_path):
        from knowledge_manager.schemas import ConfluenceSourceConfig, Index, SourceDefinition
        from knowledge_manager.source_ingestion import upsert_source
        from knowledge_manager.storage import save_index

        kb = tmp_path / "kb"
        kb.mkdir()
        _write_auth_fixture(kb)
        save_index(Index(description="ops backlog source"), kb)
        upsert_source(
            SourceDefinition(
                id="team-docs-a",
                tenant_id="team-a",
                workspace_id="ws-a",
                confluence=ConfluenceSourceConfig(
                    base_url="https://example.atlassian.net/wiki",
                    space_key="OPS",
                    email="ops@example.com",
                    api_token_env="CONFLUENCE_API_TOKEN",
                ),
            ),
            kb,
        )
        upsert_source(
            SourceDefinition(
                id="team-docs-b",
                tenant_id="team-b",
                workspace_id="ws-b",
                confluence=ConfluenceSourceConfig(
                    base_url="https://example.atlassian.net/wiki",
                    space_key="ENG",
                    email="eng@example.com",
                    api_token_env="CONFLUENCE_API_TOKEN",
                ),
            ),
            kb,
        )

        ops_client = TestClient(create_app(kb))
        r = ops_client.get("/api/ops/backlog/source", headers={"Authorization": "Bearer reviewer-team-a"})

        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["source_id"] == "team-docs-a"

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

    def test_dual_view_uses_authenticated_tenant_scope(self, tmp_path):
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
        _write_auth_fixture(kb)
        save_index(Index(description="dual view scoped"), kb)
        upsert_source(
            SourceDefinition(
                id="team-docs-a",
                tenant_id="team-a",
                workspace_id="ws-a",
                confluence=ConfluenceSourceConfig(
                    base_url="https://example.atlassian.net/wiki",
                    space_key="OPS",
                    email="ops@example.com",
                    api_token_env="CONFLUENCE_API_TOKEN",
                ),
            ),
            kb,
        )
        upsert_source(
            SourceDefinition(
                id="team-docs-b",
                tenant_id="team-b",
                workspace_id="ws-b",
                confluence=ConfluenceSourceConfig(
                    base_url="https://example.atlassian.net/wiki",
                    space_key="ENG",
                    email="eng@example.com",
                    api_token_env="CONFLUENCE_API_TOKEN",
                ),
            ),
            kb,
        )
        save_module(
            Module(
                id="mod-a",
                category="ops",
                title="Module A",
                summary="Module A summary.",
                content=ModuleContent(
                    overview="Module A overview.",
                    details="Module A details long enough for validation.",
                ),
                metadata=ModuleMetadata(
                    tenant_id="team-a",
                    workspace_id="ws-a",
                    source_documents=[
                        SourceDocumentRef(
                            source_type="confluence",
                            source_id="team-docs-a",
                            external_id="page-a",
                            title="Page A",
                        )
                    ],
                ),
            ),
            kb,
        )
        save_module(
            Module(
                id="mod-b",
                category="ops",
                title="Module B",
                summary="Module B summary.",
                content=ModuleContent(
                    overview="Module B overview.",
                    details="Module B details long enough for validation.",
                ),
                metadata=ModuleMetadata(
                    tenant_id="team-b",
                    workspace_id="ws-b",
                    source_documents=[
                        SourceDocumentRef(
                            source_type="confluence",
                            source_id="team-docs-b",
                            external_id="page-b",
                            title="Page B",
                        )
                    ],
                ),
            ),
            kb,
        )

        dual_client = TestClient(create_app(kb))
        r = dual_client.get("/api/dual-view", headers={"Authorization": "Bearer reviewer-team-a"})

        assert r.status_code == 200
        data = r.json()
        assert len(data["sources"]) == 1
        assert data["sources"][0]["source_id"] == "team-docs-a"
        assert len(data["modules"]) == 1
        assert data["modules"][0]["module_id"] == "ops/mod-a"

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

    def test_source_jobs_endpoint_uses_authenticated_tenant_scope(self, tmp_path):
        from knowledge_manager.ingestion_jobs import create_ingestion_job
        from knowledge_manager.schemas import Index
        from knowledge_manager.storage import save_index

        kb = tmp_path / "kb"
        kb.mkdir()
        _write_auth_fixture(kb)
        save_index(Index(description="jobs tenant view"), kb)
        create_ingestion_job(kb, source_id="team-docs-a", trigger="manual", tenant_id="team-a", workspace_id="ws-a")
        create_ingestion_job(kb, source_id="team-docs-b", trigger="manual", tenant_id="team-b", workspace_id="ws-b")

        jobs_client = TestClient(create_app(kb))
        r = jobs_client.get("/api/source/jobs", headers={"Authorization": "Bearer reviewer-team-a"})

        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["source_id"] == "team-docs-a"

    def test_source_jobs_endpoint_rejects_non_admin_tenant_override(self, tmp_path):
        from knowledge_manager.ingestion_jobs import create_ingestion_job
        from knowledge_manager.schemas import Index
        from knowledge_manager.storage import save_index

        kb = tmp_path / "kb"
        kb.mkdir()
        _write_auth_fixture(kb)
        save_index(Index(description="jobs tenant override"), kb)
        create_ingestion_job(kb, source_id="team-docs-b", trigger="manual", tenant_id="team-b", workspace_id="ws-b")

        jobs_client = TestClient(create_app(kb))
        r = jobs_client.get(
            "/api/source/jobs?tenant_id=team-b",
            headers={"Authorization": "Bearer reviewer-team-a"},
        )

        assert r.status_code == 403

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

    def test_admin_dashboard_uses_authenticated_tenant_scope(self, tmp_path):
        from knowledge_manager.ingestion_jobs import create_ingestion_job
        from knowledge_manager.schemas import (
            ConfluenceSourceConfig,
            Index,
            Module,
            ModuleContent,
            ModuleMetadata,
            SourceDefinition,
            SourceRegistry,
            StagingMeta,
        )
        from knowledge_manager.storage import save_index, save_staging_meta, save_to_staging
        from knowledge_manager.source_ingestion import save_source_registry

        kb = tmp_path / "kb"
        kb.mkdir()
        _write_auth_fixture(kb)
        save_index(Index(description="admin dashboard scoped"), kb)
        save_source_registry(
            SourceRegistry(
                sources={
                    "team-docs-a": SourceDefinition(
                        id="team-docs-a",
                        type="confluence",
                        tenant_id="team-a",
                        workspace_id="ws-a",
                        confluence=ConfluenceSourceConfig(
                            base_url="https://example.com",
                            space_key="OPS",
                            email="ops@example.com",
                            api_token_env="CONF_TOKEN",
                        ),
                    ),
                    "team-docs-b": SourceDefinition(
                        id="team-docs-b",
                        type="confluence",
                        tenant_id="team-b",
                        workspace_id="ws-b",
                        confluence=ConfluenceSourceConfig(
                            base_url="https://example.com",
                            space_key="ENG",
                            email="eng@example.com",
                            api_token_env="CONF_TOKEN",
                        ),
                    ),
                }
            ),
            kb,
        )
        create_ingestion_job(kb, source_id="team-docs-a", trigger="manual", tenant_id="team-a", workspace_id="ws-a")
        create_ingestion_job(kb, source_id="team-docs-b", trigger="manual", tenant_id="team-b", workspace_id="ws-b")

        staged_a = Module(
            id="review-a",
            category="ops",
            title="Review a",
            summary="Review a summary for operators.",
            content=ModuleContent(
                overview="Review a overview.",
                details="Review a details with enough length for validation.",
            ),
            metadata=ModuleMetadata(tenant_id="team-a", workspace_id="ws-a"),
        )
        staged_b = Module(
            id="review-b",
            category="ops",
            title="Review b",
            summary="Review b summary for operators.",
            content=ModuleContent(
                overview="Review b overview.",
                details="Review b details with enough length for validation.",
            ),
            metadata=ModuleMetadata(tenant_id="team-b", workspace_id="ws-b"),
        )
        save_to_staging(staged_a, kb / ".staging")
        save_to_staging(staged_b, kb / ".staging")
        save_staging_meta(StagingMeta(module_id="review-a", status="pending"), kb / ".staging")
        save_staging_meta(StagingMeta(module_id="review-b", status="pending"), kb / ".staging")

        dashboard_client = TestClient(create_app(kb))
        r = dashboard_client.get(
            "/api/admin/dashboard",
            headers={"Authorization": "Bearer admin-team-a"},
        )

        assert r.status_code == 200
        data = r.json()
        assert len(data["ingestion_jobs"]) == 1
        assert data["ingestion_jobs"][0]["source_id"] == "team-docs-a"
        assert len(data["review_backlog"]) == 1
        assert data["review_backlog"][0]["module_id"] == "review-a"
        assert len(data["stale_sources"]) == 1
        assert data["stale_sources"][0]["source_id"] == "team-docs-a"


class TestStats:
    def test_stats_ok(self, client):
        r = client.get("/api/stats")
        assert r.status_code == 200
        data = r.json()
        assert "total_searches" in data


class TestUpload:
    def test_upload_endpoint_returns_accepted_job_id_and_does_not_extract_inline(self, tmp_path, monkeypatch):
        from knowledge_manager.http_server import create_app

        started = {"job_id": ""}

        def fake_start_upload_job(*_args, **_kwargs):
            started["job_id"] = "job-upload-1"
            return "job-upload-1"

        monkeypatch.setattr("knowledge_manager.http_server._start_upload_job", fake_start_upload_job)

        client = TestClient(create_app(tmp_path))
        response = client.post(
            "/api/upload",
            files={"file": ("demo.md", b"# title", "text/markdown")},
        )

        assert response.status_code == 202
        assert response.json()["status"] == "accepted"
        assert response.json()["job_id"] == "job-upload-1"

    def test_upload_endpoint_only_enqueues_job(self, tmp_path, monkeypatch):
        from knowledge_manager.http_server import create_app

        def explode(*_args, **_kwargs):
            raise AssertionError("http upload must not start worker execution inline")

        monkeypatch.setattr("knowledge_manager.job_worker.run_single_job", explode)

        client = TestClient(create_app(tmp_path))
        response = client.post(
            "/api/upload",
            files={"file": ("demo.md", b"# title", "text/markdown")},
        )

        assert response.status_code == 202

    def test_upload_requires_write_permission_when_auth_is_enabled(self, tmp_path, monkeypatch):
        from knowledge_manager.schemas import Index
        from knowledge_manager.storage import save_index

        _write_auth_fixture(tmp_path)
        save_index(Index(description="upload auth"), tmp_path)

        monkeypatch.setattr("knowledge_manager.http_server._start_upload_job", lambda *_args, **_kwargs: "job-upload-1")

        client = TestClient(create_app(tmp_path))
        response = client.post(
            "/api/upload",
            headers={"Authorization": "Bearer viewer-team-a"},
            files={"file": ("demo.md", b"# title", "text/markdown")},
        )

        assert response.status_code == 403


class TestRequestCorrelation:
    def test_request_id_header_is_added(self, tmp_path):
        client = TestClient(create_app(tmp_path))

        response = client.get("/api/health")

        assert response.status_code == 200
        assert response.headers["X-Request-ID"]


class _FakeLLM:
    class _Config:
        model = "test-model"
        base_url = ""
        temperature = 0.3
        max_tokens = 1024

    def __init__(self):
        self.config = self._Config()

    async def complete(self, _prompt: str) -> str:
        return "[]"


@pytest.mark.asyncio
async def test_chat_pipeline_limits_ranked_context_to_three_modules(tmp_path, monkeypatch):
    pipeline = ChatPipeline(tmp_path, _FakeLLM())

    async def fake_rewrite(query, history):
        return query

    async def fake_keyword(query):
        return [
            {
                "key": f"ops/mod-{idx}",
                "title": f"Module {idx}",
                "summary": f"Summary {idx}",
                "confidence": "medium",
                "source": "keyword",
                "module": None,
            }
            for idx in range(6)
        ]

    async def fake_empty(*_args, **_kwargs):
        return []

    captured = {"count": 0}

    def fake_build_system_prompt(modules, intent, max_tokens=8000):
        captured["count"] = len(modules)
        return "system"

    async def fake_stream(_system, _user, temperature=0.3):
        yield "answer"

    monkeypatch.setattr(pipeline, "_rewrite_query", fake_rewrite)
    monkeypatch.setattr(pipeline, "_keyword_recall", fake_keyword)
    monkeypatch.setattr(pipeline, "_tree_recall", fake_empty)
    monkeypatch.setattr(pipeline, "_vector_recall", fake_empty)
    monkeypatch.setattr(pipeline, "_build_system_prompt", fake_build_system_prompt)
    monkeypatch.setattr(pipeline, "_stream_llm", fake_stream)
    monkeypatch.setattr(pipeline, "_generate_follow_ups", fake_empty)

    events = [event async for event in pipeline.chat("rollback", [], "precise")]
    ranking = next(
        event
        for event in events
        if event.type == "status"
        and event.data.get("stage") == "ranking"
        and "selected" in event.data
    )

    assert ranking.data["selected"] == 3
    assert captured["count"] == 3


@pytest.mark.asyncio
async def test_extractor_caps_chunk_size_and_module_budget(monkeypatch):
    from knowledge_manager.extractor import Extractor
    from knowledge_manager.schemas import ExtractionConfig, Module, ModuleContent

    config = ExtractionConfig(
        max_modules_per_extraction=10,
        chunk_size=10000,
        chunk_overlap=50,
        auto_categorize=False,
    )
    extractor = Extractor(_FakeLLM(), config)
    captured = {"chunk_size": 0}

    def fake_chunk_text(text, chunk_size, overlap):
        captured["chunk_size"] = chunk_size
        return ["chunk-1", "chunk-2"]

    async def fake_extract_chunk(text, category, existing_categories, chunk_index, total_chunks):
        return [
            Module(
                id=f"{text}-mod-{idx}",
                category=category,
                title=f"Module {idx}",
                summary="Summary long enough for validation.",
                content=ModuleContent(
                    overview="Overview text.",
                    details="Details long enough for validation.",
                ),
            )
            for idx in range(4)
        ]

    monkeypatch.setattr("knowledge_manager.extractor._chunk_text", fake_chunk_text)
    monkeypatch.setattr(extractor, "_extract_chunk", fake_extract_chunk)

    modules = await extractor.extract("x" * 5000, "ops")

    assert captured["chunk_size"] == 4000
    assert len(modules) == 3
