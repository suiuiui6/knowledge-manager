from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata
from knowledge_manager.storage import list_modules, save_module
from knowledge_manager.tenancy import TenantContext, module_visible_to_tenant


def test_list_modules_only_returns_requested_tenant_modules(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    save_module(
        Module(
            id="auth-a",
            category="auth",
            title="Auth A Module",
            summary="Tenant A auth guidance for production.",
            content=ModuleContent(
                overview="Tenant A auth overview.",
                details="Tenant A auth details with enough length for validation.",
            ),
            metadata=ModuleMetadata(tenant_id="team-a"),
        ),
        kb,
    )
    save_module(
        Module(
            id="auth-b",
            category="auth",
            title="Auth B Module",
            summary="Tenant B auth guidance for production.",
            content=ModuleContent(
                overview="Tenant B auth overview.",
                details="Tenant B auth details with enough length for validation.",
            ),
            metadata=ModuleMetadata(tenant_id="team-b"),
        ),
        kb,
    )

    modules = list_modules(kb, tenant=TenantContext(tenant_id="team-a"))

    assert [module.id for module in modules] == ["auth-a"]


def test_module_visible_to_tenant_allows_global_reads():
    module = Module(
        id="shared-guide",
        category="ops",
        title="Shared Guide",
        summary="Shared operational guidance for all tenants.",
        content=ModuleContent(
            overview="Shared guide overview.",
            details="Shared guide details with enough length for validation.",
        ),
    )

    assert module_visible_to_tenant(module, TenantContext(tenant_id="team-a")) is True
