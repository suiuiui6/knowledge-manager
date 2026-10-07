from pathlib import Path

from fastapi import HTTPException, Request

from knowledge_manager.audit import AuditEvent, log_audit_event
from knowledge_manager.auth import AuthSubject, load_auth_config
from knowledge_manager.rbac import check_permission
from knowledge_manager.schemas import Module
from knowledge_manager.schemas import Config
from knowledge_manager.tenancy import TenantContext

SUPPORTED_AUTH_PROVIDERS = {"token", "oidc"}


def _log_authz_denial(
    request: Request,
    kb_path: Path,
    detail: str,
    *,
    tenant_id: str = "",
    resource: str = "",
) -> None:
    subject = getattr(request.state, "auth_subject", None)
    user = subject.user if subject is not None else "anonymous"
    subject_tenant = subject.tenant_id if subject is not None else ""
    log_audit_event(
        kb_path,
        AuditEvent(
            user=user,
            operation="authz.denied",
            details=detail,
            tenant_id=tenant_id or subject_tenant,
            resource=resource or str(request.url.path),
            result="denied",
            request_id=getattr(request.state, "request_id", ""),
        ),
    )


def _load_config_safe(kb_path: Path) -> Config | None:
    cfg_path = kb_path / "config.json"
    if not cfg_path.exists():
        return None
    try:
        return Config.model_validate_json(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def require_auth_system_ready(kb_path: Path) -> None:
    cfg = _load_config_safe(kb_path)
    production_mode = bool(cfg and cfg.security.production_mode)
    auth_cfg = load_auth_config(kb_path)
    if production_mode and (auth_cfg is None or not auth_cfg.provider):
        raise HTTPException(
            status_code=503,
            detail="Authentication must be configured in production_mode",
        )
    if auth_cfg and auth_cfg.provider and auth_cfg.provider not in SUPPORTED_AUTH_PROVIDERS:
        raise HTTPException(
            status_code=503,
            detail=f"Unsupported authentication provider: {auth_cfg.provider}",
        )


def require_identity(request: Request, kb_path: Path, permission: str | None = None) -> AuthSubject:
    require_auth_system_ready(kb_path)
    auth_cfg = load_auth_config(kb_path)
    subject = getattr(request.state, "auth_subject", None)
    auth_disabled = auth_cfg is None or not auth_cfg.provider
    if subject is None:
        if auth_disabled:
            return AuthSubject(user="anonymous")
        _log_authz_denial(request, kb_path, "Authentication required")
        raise HTTPException(status_code=401, detail="Authentication required")
    if auth_disabled:
        return subject
    if permission and not check_permission(subject.user, permission, kb_path):
        _log_authz_denial(request, kb_path, f"Permission denied: {permission}")
        raise HTTPException(status_code=403, detail=f"Permission denied: {permission}")
    return subject


def resolve_tenant_context(
    request: Request,
    kb_path: Path,
    *,
    tenant_id: str = "",
    workspace_id: str = "",
    allow_global_reads: bool = True,
) -> TenantContext | None:
    require_auth_system_ready(kb_path)
    auth_cfg = load_auth_config(kb_path)
    subject = getattr(request.state, "auth_subject", None)

    if subject is None:
        if auth_cfg is None or not auth_cfg.provider:
            return TenantContext(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                allow_global_reads=allow_global_reads,
            ) if tenant_id else None
        return None

    requested_tenant = tenant_id.strip()
    requested_workspace = workspace_id.strip()
    if requested_tenant and requested_tenant != subject.tenant_id:
        if not check_permission(subject.user, "config.manage", kb_path):
            _log_authz_denial(
                request,
                kb_path,
                "Tenant override requires admin access",
                tenant_id=requested_tenant,
            )
            raise HTTPException(status_code=403, detail="Tenant override requires admin access")
    if requested_workspace and requested_workspace != subject.workspace_id:
        if not check_permission(subject.user, "config.manage", kb_path):
            _log_authz_denial(
                request,
                kb_path,
                "Workspace override requires admin access",
                tenant_id=requested_tenant or subject.tenant_id,
            )
            raise HTTPException(status_code=403, detail="Workspace override requires admin access")

    resolved_tenant = requested_tenant or subject.tenant_id
    resolved_workspace = requested_workspace or subject.workspace_id
    if not resolved_tenant and not resolved_workspace:
        return None
    return TenantContext(
        tenant_id=resolved_tenant,
        workspace_id=resolved_workspace,
        allow_global_reads=allow_global_reads,
    )


def subject_is_admin(subject: AuthSubject, kb_path: Path) -> bool:
    return check_permission(subject.user, "config.manage", kb_path)


def enforce_subject_module_access(subject: AuthSubject, module: Module, kb_path: Path) -> None:
    if subject.user == "anonymous" or subject_is_admin(subject, kb_path):
        return
    module_tenant = module.metadata.tenant_id
    module_workspace = module.metadata.workspace_id
    if module_tenant and subject.tenant_id and module_tenant != subject.tenant_id:
        raise HTTPException(status_code=404, detail=f"Module not found: {module.category}/{module.id}")
    if module_workspace and subject.workspace_id and module_workspace != subject.workspace_id:
        raise HTTPException(status_code=404, detail=f"Module not found: {module.category}/{module.id}")


def enforce_subject_metadata_override(
    request: Request,
    subject: AuthSubject,
    kb_path: Path,
    *,
    tenant_id: str = "",
    workspace_id: str = "",
) -> None:
    if subject.user == "anonymous" or subject_is_admin(subject, kb_path):
        return
    if tenant_id and subject.tenant_id and tenant_id != subject.tenant_id:
        _log_authz_denial(
            request,
            kb_path,
            "Tenant override requires admin access",
            tenant_id=tenant_id,
        )
        raise HTTPException(status_code=403, detail="Tenant override requires admin access")
    if workspace_id and subject.workspace_id and workspace_id != subject.workspace_id:
        _log_authz_denial(
            request,
            kb_path,
            "Workspace override requires admin access",
            tenant_id=tenant_id or subject.tenant_id,
        )
        raise HTTPException(status_code=403, detail="Workspace override requires admin access")
