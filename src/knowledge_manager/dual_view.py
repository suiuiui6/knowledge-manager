from __future__ import annotations

from pathlib import Path
from typing import Any

from knowledge_manager.source_ingestion import load_source_registry
from knowledge_manager.storage import list_modules
from knowledge_manager.tenancy import TenantContext, module_visible_to_tenant


def build_dual_view(kb_path: Path, tenant: TenantContext | None = None) -> dict[str, Any]:
    modules = list_modules(kb_path, tenant=tenant)
    registry = load_source_registry(kb_path)

    sources: list[dict[str, Any]] = []
    for source_id, definition in registry.sources.items():
        if tenant is not None and not (
            (not definition.tenant_id and tenant.allow_global_reads)
            or definition.tenant_id == tenant.tenant_id
        ):
            continue
        module_ids: list[str] = []
        for module in modules:
            if any(doc.source_id == source_id for doc in module.metadata.source_documents):
                module_ids.append(f"{module.category}/{module.id}")
        sources.append(
            {
                "source_id": source_id,
                "source_type": definition.type,
                "module_ids": sorted(module_ids),
                "tracked_pages": len(definition.sync.page_versions),
            }
        )

    module_items: list[dict[str, Any]] = []
    for module in modules:
        module_items.append(
            {
                "module_id": f"{module.category}/{module.id}",
                "source_ids": sorted({doc.source_id for doc in module.metadata.source_documents}),
                "stale_due_to_source_change": module.metadata.stale_due_to_source_change,
            }
        )

    return {"sources": sources, "modules": module_items}
