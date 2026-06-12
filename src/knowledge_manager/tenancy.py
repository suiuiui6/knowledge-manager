from __future__ import annotations

from pydantic import BaseModel

from knowledge_manager.schemas import Module


class TenantContext(BaseModel):
    tenant_id: str
    workspace_id: str = ""
    allow_global_reads: bool = True


def module_visible_to_tenant(module: Module, tenant: TenantContext | None) -> bool:
    if tenant is None:
        return True
    module_tenant = module.metadata.tenant_id
    if module_tenant == tenant.tenant_id:
        return True
    return tenant.allow_global_reads and not module_tenant
