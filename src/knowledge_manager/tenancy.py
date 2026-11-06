from __future__ import annotations

from pydantic import BaseModel

from knowledge_manager.schemas import Module


class TenantContext(BaseModel):
    tenant_id: str
    workspace_id: str = ""
    allow_global_reads: bool = True


def module_visible_to_tenant(module: Module, tenant: TenantContext | None) -> bool:
    return scope_visible_to_tenant(module.metadata.tenant_id, module.metadata.workspace_id, tenant)


def scope_visible_to_tenant(
    tenant_id: str, workspace_id: str, tenant: TenantContext | None
) -> bool:
    """An empty resource workspace is tenant-wide; an empty context spans workspaces."""
    if tenant is None:
        return True
    tenant_matches = tenant_id == tenant.tenant_id or (tenant.allow_global_reads and not tenant_id)
    workspace_matches = (
        not tenant.workspace_id or not workspace_id or workspace_id == tenant.workspace_id
    )
    return tenant_matches and workspace_matches
