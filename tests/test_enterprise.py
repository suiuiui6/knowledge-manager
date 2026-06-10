import json
import pytest
from pathlib import Path
from fastapi import FastAPI
from starlette.testclient import TestClient

from knowledge_manager.auth import (
    AuthConfig, AuthMiddleware, load_auth_config, inject_auth_middleware,
)
from knowledge_manager.audit import (
    AuditEvent, log_audit_event, read_audit_log, generate_compliance_report,
)
from knowledge_manager.rbac import (
    RBACConfig, get_user_role, set_user_role, check_permission,
    list_users, remove_user, load_rbac_config,
)


class TestAuthConfig:
    def test_load_nonexistent(self, tmp_path):
        assert load_auth_config(tmp_path) is None

    def test_load_auth_config(self, tmp_path):
        (tmp_path / "auth.json").write_text(json.dumps({
            "provider": "token",
            "oidc_config": {"static_token": "test-token-123"},
        }))
        cfg = load_auth_config(tmp_path)
        assert cfg is not None
        assert cfg.provider == "token"

    def test_auth_config_defaults(self):
        cfg = AuthConfig()
        assert cfg.provider == ""
        assert cfg.oidc_config == {}


class TestAuthMiddleware:
    def test_no_auth_config(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        app = FastAPI()

        @app.get("/api/test")
        def test_route():
            return {"ok": True}

        app.add_middleware(AuthMiddleware, kb_path=kb)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/test")
        assert resp.status_code == 200

    def test_public_paths_allowed(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        (kb / "auth.json").write_text(json.dumps({
            "provider": "token",
            "oidc_config": {"static_token": "secret"},
        }))
        app = FastAPI()

        @app.get("/api/health")
        def health():
            return {"status": "ok"}

        app.add_middleware(AuthMiddleware, kb_path=kb)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_token_auth_rejected(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        (kb / "auth.json").write_text(json.dumps({
            "provider": "token",
            "oidc_config": {"static_token": "secret"},
        }))
        app = FastAPI()

        @app.get("/api/protected")
        def protected():
            return {"ok": True}

        app.add_middleware(AuthMiddleware, kb_path=kb)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/protected")
        assert resp.status_code == 401

    def test_token_auth_accepted(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        (kb / "auth.json").write_text(json.dumps({
            "provider": "token",
            "oidc_config": {"static_token": "secret"},
        }))
        app = FastAPI()

        @app.get("/api/protected")
        def protected():
            return {"ok": True}

        app.add_middleware(AuthMiddleware, kb_path=kb)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/protected", headers={"Authorization": "Bearer secret"})
        assert resp.status_code == 200

    def test_jwt_decode(self):
        header = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        payload = "eyJzdWIiOiJ0ZXN0QGV4YW1wbGUuY29tIn0"
        token = f"{header}.{payload}.sig"
        result = AuthMiddleware._decode_jwt_unsigned(token)
        assert result.get("sub") == "test@example.com"


class TestAudit:
    def test_log_and_read(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        event = AuditEvent(
            user="alice", operation="module.create",
            module_id="test/mod", category="test",
            details="Created test module",
        )
        log_audit_event(kb, event)

        events = read_audit_log(kb)
        assert len(events) == 1
        assert events[0]["user"] == "alice"
        assert events[0]["operation"] == "module.create"

    def test_filter_by_since(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        log_audit_event(kb, AuditEvent(user="alice", operation="module.create"))

        events = read_audit_log(kb, since="2030-01-01")
        assert len(events) == 0

    def test_filter_by_user(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        log_audit_event(kb, AuditEvent(user="alice", operation="module.create"))
        log_audit_event(kb, AuditEvent(user="bob", operation="module.update"))

        alice_events = read_audit_log(kb, user="alice")
        assert len(alice_events) == 1
        assert alice_events[0]["user"] == "alice"

    def test_empty_log(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        assert read_audit_log(kb) == []

    def test_compliance_report(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        log_audit_event(kb, AuditEvent(user="alice", operation="module.create", module_id="m1"))
        log_audit_event(kb, AuditEvent(user="bob", operation="module.update", module_id="m1"))
        log_audit_event(kb, AuditEvent(user="alice", operation="module.approve", module_id="m2"))

        report = generate_compliance_report(kb, fmt="json")
        data = json.loads(report)
        assert data["total_events"] == 3
        assert data["unique_users"] == 2

    def test_compliance_report_text(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        log_audit_event(kb, AuditEvent(user="alice", operation="module.create"))

        report = generate_compliance_report(kb, fmt="text")
        assert "Compliance Report" in report
        assert "module.create" in report


class TestRBAC:
    @pytest.fixture
    def kb(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        return kb

    def test_default_role(self, kb):
        assert get_user_role("unknown", kb) == "viewer"

    def test_set_and_get_role(self, kb):
        assert set_user_role("alice", "admin", kb)
        assert get_user_role("alice", kb) == "admin"

    def test_invalid_role(self, kb):
        assert not set_user_role("bob", "superadmin", kb)

    def test_check_permission(self, kb):
        set_user_role("alice", "editor", kb)
        assert check_permission("alice", "module.write", kb)
        assert not check_permission("alice", "module.delete", kb)

    def test_admin_all_permissions(self, kb):
        set_user_role("admin", "admin", kb)
        assert check_permission("admin", "module.delete", kb)
        assert check_permission("admin", "config.manage", kb)

    def test_viewer_read_only(self, kb):
        assert check_permission("viewer", "module.read", kb)
        assert not check_permission("viewer", "module.write", kb)

    def test_list_users(self, kb):
        set_user_role("alice", "admin", kb)
        set_user_role("bob", "editor", kb)
        users = list_users(kb)
        assert len(users) == 2

    def test_remove_user(self, kb):
        set_user_role("alice", "admin", kb)
        assert remove_user("alice", kb)
        assert get_user_role("alice", kb) == "viewer"

    def test_remove_nonexistent(self, kb):
        assert not remove_user("nonexistent", kb)

    def test_load_rbac_config(self, tmp_path):
        kb = tmp_path / "kb"
        kb.mkdir()
        (kb / "rbac.json").write_text(json.dumps({
            "users": {"alice": "admin", "bob": "reviewer"}
        }))
        cfg = load_rbac_config(kb)
        assert cfg.users["alice"] == "admin"


class TestAuditEvent:
    def test_event_creation(self):
        e = AuditEvent(user="test", operation="module.create")
        assert e.user == "test"
        assert e.timestamp is not None

    def test_event_to_dict(self):
        e = AuditEvent(user="test", operation="module.update",
                       module_id="mod/1", category="cat", details="Updated")
        d = e.to_dict()
        assert d["user"] == "test"
        assert d["module_id"] == "mod/1"
