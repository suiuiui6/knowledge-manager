from __future__ import annotations

from pathlib import Path
from typing import Any

from knowledge_manager.ingestion_jobs import list_ingestion_jobs
from knowledge_manager.materialized_views import (
    load_fresh_materialized_view,
    store_materialized_view,
)
from knowledge_manager.ops_export import (
    generate_review_backlog_export,
    generate_source_backlog_export,
)
from knowledge_manager.source_ingestion import load_source_registry
from knowledge_manager.storage import generate_ops_report, list_staging_meta
from knowledge_manager.tenancy import TenantContext, module_visible_to_tenant
from knowledge_manager.storage import list_staging


def build_admin_dashboard(kb_path: Path, tenant: TenantContext | None = None) -> dict[str, Any]:
    cached = load_fresh_materialized_view(kb_path, "admin_dashboard") if tenant is None else None
    if cached is not None:
        return cached
    jobs = list_ingestion_jobs(kb_path)
    staging_meta = list_staging_meta(kb_path / ".staging")
    ops_report = generate_ops_report(kb_path, staging_meta=staging_meta)
    registry = load_source_registry(kb_path)

    if tenant is not None:
        jobs = [
            job for job in jobs
            if (
                (not job.tenant_id and tenant.allow_global_reads)
                or job.tenant_id == tenant.tenant_id
            )
        ]
        visible_staging_ids = {
            module.id
            for module in list_staging(kb_path / ".staging")
            if module_visible_to_tenant(module, tenant)
        }
        staging_meta = [meta for meta in staging_meta if meta.module_id in visible_staging_ids]
        visible_source_ids = {
            source_id
            for source_id, source in registry.sources.items()
            if (
                (not source.tenant_id and tenant.allow_global_reads)
                or source.tenant_id == tenant.tenant_id
            )
        }
    else:
        visible_source_ids = set(registry.sources.keys())

    stale_sources = [
        item
        for item in generate_source_backlog_export(kb_path, report=ops_report).get("items", [])
        if item.get("source_id", "") in visible_source_ids
    ]
    review_backlog = [
        item
        for item in generate_review_backlog_export(
            kb_path,
            report=ops_report,
            staging_meta=staging_meta,
        ).get("items", [])
        if item.get("module_id", "") in {meta.module_id for meta in staging_meta}
    ]
    payload = {
        "ingestion_jobs": [job.model_dump(mode="json") for job in jobs],
        "stale_sources": stale_sources,
        "review_backlog": review_backlog,
        "eval_regressions": [],
    }
    return store_materialized_view(kb_path, "admin_dashboard", payload) if tenant is None else payload
