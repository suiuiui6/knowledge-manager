import json

from fastapi.testclient import TestClient

from knowledge_manager.http_server import create_app
from knowledge_manager.schemas import Index
from knowledge_manager.storage import save_index
from knowledge_manager.audit import read_audit_log


def _write_auth_fixture(kb):
    (kb / "auth.json").write_text(
        json.dumps(
            {
                "provider": "token",
                "oidc_config": {
                    "static_tokens": {
                        "reviewer-team-a": {"sub": "rachel", "tenant_id": "team-a", "workspace_id": "ws-a"},
                        "editor-team-a": {"sub": "alice", "tenant_id": "team-a", "workspace_id": "ws-a"},
                        "admin-root": {"sub": "root", "groups": ["admins"]},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (kb / "rbac.json").write_text(
        json.dumps({"users": {"alice": "editor", "rachel": "reviewer", "root": "admin"}}),
        encoding="utf-8",
    )


def test_module_create_emits_audit_event_with_user_tenant_and_request_id(tmp_path, monkeypatch):
    kb = tmp_path / "kb"
    kb.mkdir()
    _write_auth_fixture(kb)
    save_index(Index(description="audit"), kb)
    monkeypatch.setattr(
        "knowledge_manager.storage.schedule_maintenance_job",
        lambda *_args, **_kwargs: {"deferred": True, "action": "module_saved"},
    )
    client = TestClient(create_app(kb))

    response = client.post(
        "/api/modules",
        headers={"Authorization": "Bearer editor-team-a"},
        json={
            "id": "audit-mod",
            "category": "ops",
            "title": "Audit module",
            "summary": "Audit module summary.",
            "content": {"overview": "Audit overview.", "details": "Audit details long enough for validation."},
            "submit_to_staging": False,
        },
    )

    events = read_audit_log(kb)
    assert response.headers["X-Request-ID"]
    assert any(
        event["operation"] == "module.create"
        and event["user"] == "alice"
        and event["tenant_id"] == "team-a"
        and event["request_id"]
        for event in events
    )


def test_tenant_override_denial_is_audited(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    _write_auth_fixture(kb)
    save_index(Index(description="audit"), kb)
    client = TestClient(create_app(kb))

    response = client.get("/api/index?tenant_id=team-b", headers={"Authorization": "Bearer editor-team-a"})

    events = read_audit_log(kb)
    assert response.status_code == 403
    assert any(event["operation"] == "authz.denied" and event["result"] == "denied" for event in events)


def test_module_create_tenant_override_denial_is_audited(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    _write_auth_fixture(kb)
    save_index(Index(description="audit"), kb)
    client = TestClient(create_app(kb))

    response = client.post(
        "/api/modules",
        headers={"Authorization": "Bearer editor-team-a"},
        json={
            "id": "cross-tenant-create",
            "category": "ops",
            "title": "Cross tenant create",
            "summary": "Cross tenant create summary.",
            "content": {
                "overview": "Cross tenant create overview.",
                "details": "Cross tenant create details long enough for validation.",
            },
            "metadata": {"tenant_id": "team-b"},
            "submit_to_staging": False,
        },
    )

    events = read_audit_log(kb)
    assert response.status_code == 403
    assert any(
        event["operation"] == "authz.denied"
        and event["result"] == "denied"
        and event["user"] == "alice"
        and event["tenant_id"] == "team-b"
        and event["resource"] == "/api/modules"
        for event in events
    )


def test_module_update_emits_audit_event(tmp_path, monkeypatch):
    from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata
    from knowledge_manager.storage import save_index, save_module

    kb = tmp_path / "kb"
    kb.mkdir()
    _write_auth_fixture(kb)
    save_index(Index(description="audit"), kb)
    save_module(
        Module(
            id="audit-mod",
            category="ops",
            title="Audit module",
            summary="Audit module summary.",
            content=ModuleContent(
                overview="Audit overview.",
                details="Audit details long enough for validation.",
            ),
            metadata=ModuleMetadata(tenant_id="team-a", workspace_id="ws-a"),
        ),
        kb,
    )
    monkeypatch.setattr(
        "knowledge_manager.storage.schedule_maintenance_job",
        lambda *_args, **_kwargs: {"deferred": True, "action": "module_saved"},
    )
    client = TestClient(create_app(kb))

    response = client.put(
        "/api/modules/ops/audit-mod",
        headers={"Authorization": "Bearer editor-team-a"},
        json={"title": "Updated title"},
    )

    events = read_audit_log(kb)
    assert response.status_code == 200
    assert any(
        event["operation"] == "module.update"
        and event["user"] == "alice"
        and event["module_id"] == "audit-mod"
        and event["request_id"]
        for event in events
    )


def test_module_update_tenant_override_denial_is_audited(tmp_path):
    from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata
    from knowledge_manager.storage import save_index, save_module

    kb = tmp_path / "kb"
    kb.mkdir()
    _write_auth_fixture(kb)
    save_index(Index(description="audit"), kb)
    save_module(
        Module(
            id="audit-mod",
            category="ops",
            title="Audit module",
            summary="Audit module summary.",
            content=ModuleContent(
                overview="Audit overview.",
                details="Audit details long enough for validation.",
            ),
            metadata=ModuleMetadata(tenant_id="team-a", workspace_id="ws-a"),
        ),
        kb,
    )
    client = TestClient(create_app(kb))

    response = client.put(
        "/api/modules/ops/audit-mod",
        headers={"Authorization": "Bearer editor-team-a"},
        json={"metadata": {"tenant_id": "team-b"}},
    )

    events = read_audit_log(kb)
    assert response.status_code == 403
    assert any(
        event["operation"] == "authz.denied"
        and event["result"] == "denied"
        and event["user"] == "alice"
        and event["tenant_id"] == "team-b"
        and event["resource"] == "/api/modules/ops/audit-mod"
        for event in events
    )


def test_module_delete_emits_audit_event(tmp_path, monkeypatch):
    from knowledge_manager.schemas import Index, Module, ModuleContent
    from knowledge_manager.storage import save_index, save_module

    kb = tmp_path / "kb"
    kb.mkdir()
    _write_auth_fixture(kb)
    save_index(Index(description="audit"), kb)
    save_module(
        Module(
            id="delete-me",
            category="ops",
            title="Delete me",
            summary="Delete me summary.",
            content=ModuleContent(
                overview="Delete overview.",
                details="Delete details long enough for validation.",
            ),
        ),
        kb,
    )
    monkeypatch.setattr("knowledge_manager.storage.delete_module", lambda *_args, **_kwargs: True)
    client = TestClient(create_app(kb))

    response = client.delete(
        "/api/modules/ops/delete-me",
        headers={"Authorization": "Bearer admin-root"},
    )

    events = read_audit_log(kb)
    assert response.status_code == 200
    assert any(
        event["operation"] == "module.delete"
        and event["user"] == "root"
        and event["module_id"] == "delete-me"
        and event["request_id"]
        for event in events
    )


def test_staging_approve_emits_audit_event(tmp_path, monkeypatch):
    from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata, StagingMeta
    from knowledge_manager.storage import save_index, save_staging_meta, save_to_staging

    kb = tmp_path / "kb"
    kb.mkdir()
    _write_auth_fixture(kb)
    save_index(Index(description="audit"), kb)
    staged = Module(
        id="review-me",
        category="ops",
        title="Review me",
        summary="Review me summary for operators.",
        content=ModuleContent(
            overview="Review overview.",
            details="Review details long enough for validation.",
        ),
        metadata=ModuleMetadata(tenant_id="team-a", workspace_id="ws-a"),
    )
    save_to_staging(staged, kb / ".staging")
    save_staging_meta(StagingMeta(module_id="review-me", status="pending"), kb / ".staging")
    monkeypatch.setattr("knowledge_manager.storage.approve_from_staging", lambda *_args, **_kwargs: None)
    client = TestClient(create_app(kb))

    response = client.post(
        "/api/staging/review-me/approve",
        headers={"Authorization": "Bearer reviewer-team-a"},
        json={"comment": "approved"},
    )

    events = read_audit_log(kb)
    assert response.status_code == 200
    assert any(
        event["operation"] == "staging.approve"
        and event["user"] == "rachel"
        and event["module_id"] == "review-me"
        and event["request_id"]
        for event in events
    )


def test_staging_approve_pending_emits_audit_event(tmp_path):
    from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata, StagingMeta
    from knowledge_manager.storage import save_index, save_staging_meta, save_to_staging

    kb = tmp_path / "kb"
    kb.mkdir()
    _write_auth_fixture(kb)
    save_index(Index(description="audit"), kb)
    (kb / "config.json").write_text(json.dumps({"review": {"required_approvals": 2}}), encoding="utf-8")
    staged = Module(
        id="review-me",
        category="ops",
        title="Review me",
        summary="Review me summary for operators.",
        content=ModuleContent(
            overview="Review overview.",
            details="Review details long enough for validation.",
        ),
        metadata=ModuleMetadata(tenant_id="team-a", workspace_id="ws-a"),
    )
    save_to_staging(staged, kb / ".staging")
    save_staging_meta(StagingMeta(module_id="review-me", status="pending"), kb / ".staging")
    client = TestClient(create_app(kb))

    response = client.post(
        "/api/staging/review-me/approve",
        headers={"Authorization": "Bearer reviewer-team-a"},
        json={"comment": "first approval"},
    )

    events = read_audit_log(kb)
    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert any(
        event["operation"] == "staging.approve"
        and event["user"] == "rachel"
        and event["module_id"] == "review-me"
        and event["result"] == "pending"
        for event in events
    )


def test_staging_reject_emits_audit_event(tmp_path):
    from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata, StagingMeta
    from knowledge_manager.storage import save_index, save_staging_meta, save_to_staging

    kb = tmp_path / "kb"
    kb.mkdir()
    _write_auth_fixture(kb)
    save_index(Index(description="audit"), kb)
    staged = Module(
        id="reject-me",
        category="ops",
        title="Reject me",
        summary="Reject me summary for operators.",
        content=ModuleContent(
            overview="Reject overview.",
            details="Reject details long enough for validation.",
        ),
        metadata=ModuleMetadata(tenant_id="team-a", workspace_id="ws-a"),
    )
    save_to_staging(staged, kb / ".staging")
    save_staging_meta(StagingMeta(module_id="reject-me", status="pending"), kb / ".staging")
    client = TestClient(create_app(kb))

    response = client.post(
        "/api/staging/reject-me/reject",
        headers={"Authorization": "Bearer reviewer-team-a"},
        json={"comment": "needs changes"},
    )

    events = read_audit_log(kb)
    assert response.status_code == 200
    assert any(
        event["operation"] == "staging.reject"
        and event["user"] == "rachel"
        and event["module_id"] == "reject-me"
        and event["request_id"]
        for event in events
    )


def test_admin_dashboard_read_emits_audit_event(tmp_path, monkeypatch):
    from knowledge_manager.schemas import Index
    from knowledge_manager.storage import save_index

    kb = tmp_path / "kb"
    kb.mkdir()
    _write_auth_fixture(kb)
    save_index(Index(description="audit"), kb)
    monkeypatch.setattr("knowledge_manager.admin_views.build_admin_dashboard", lambda *_args, **_kwargs: {"ok": True})
    client = TestClient(create_app(kb))

    response = client.get(
        "/api/admin/dashboard",
        headers={"Authorization": "Bearer admin-root"},
    )

    events = read_audit_log(kb)
    assert response.status_code == 200
    assert any(
        event["operation"] == "admin.dashboard.read"
        and event["user"] == "root"
        and event["request_id"]
        for event in events
    )


def test_source_jobs_read_emits_audit_event(tmp_path, monkeypatch):
    from knowledge_manager.ingestion_jobs import IngestionJob
    from knowledge_manager.schemas import Index
    from knowledge_manager.storage import save_index

    kb = tmp_path / "kb"
    kb.mkdir()
    _write_auth_fixture(kb)
    save_index(Index(description="audit"), kb)
    monkeypatch.setattr(
        "knowledge_manager.ingestion_jobs.list_ingestion_jobs",
        lambda *_args, **_kwargs: [
            IngestionJob(
                job_id="job-1",
                source_id="team-docs-a",
                trigger="manual",
                tenant_id="team-a",
                workspace_id="ws-a",
            )
        ],
    )
    client = TestClient(create_app(kb))

    response = client.get(
        "/api/source/jobs",
        headers={"Authorization": "Bearer reviewer-team-a"},
    )

    events = read_audit_log(kb)
    assert response.status_code == 200
    assert any(
        event["operation"] == "source.jobs.read"
        and event["user"] == "rachel"
        and event["request_id"]
        for event in events
    )


def test_upload_enqueue_emits_audit_event(tmp_path, monkeypatch):
    from knowledge_manager.schemas import Index
    from knowledge_manager.storage import save_index

    kb = tmp_path / "kb"
    kb.mkdir()
    _write_auth_fixture(kb)
    save_index(Index(description="audit"), kb)
    monkeypatch.setattr("knowledge_manager.http_server._start_upload_job", lambda *_args, **_kwargs: "job-upload-1")
    client = TestClient(create_app(kb))

    response = client.post(
        "/api/upload",
        headers={"Authorization": "Bearer editor-team-a"},
        files={"file": ("demo.md", b"# title", "text/markdown")},
    )

    events = read_audit_log(kb)
    assert response.status_code == 202
    assert any(
        event["operation"] == "source.job.enqueue"
        and event["user"] == "alice"
        and event["result"] == "accepted"
        and event["request_id"]
        for event in events
    )
