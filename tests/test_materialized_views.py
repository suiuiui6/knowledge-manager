from __future__ import annotations

import json

from knowledge_manager.admin_views import build_admin_dashboard
from knowledge_manager.ingestion_jobs import create_ingestion_job
from knowledge_manager.schemas import (
    ConfluenceSourceConfig,
    Index,
    Module,
    ModuleContent,
    ModuleMetadata,
    ReviewRecord,
    SourceDefinition,
    SourceRegistry,
    SourceSyncState,
    StagingMeta,
)
from knowledge_manager.source_ingestion import save_source_registry
from knowledge_manager.storage import (
    generate_health_report,
    generate_ops_report,
    generate_recommendations,
    rebuild_index,
    save_index,
    save_module,
    save_staging_meta,
    save_to_staging,
)


def test_health_report_reuses_snapshot_until_storage_changes(tmp_path, monkeypatch):
    from knowledge_manager.materialized_views import load_materialized_view
    import knowledge_manager.storage as storage

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="health snapshot"), kb)
    save_module(
        Module(
            id="ops-health",
            category="ops",
            title="Ops Health",
            summary="Ops health summary.",
            content=ModuleContent(
                overview="Healthy overview.",
                details="Healthy details long enough for validation.",
            ),
            metadata=ModuleMetadata(tags=["ops"]),
        ),
        kb,
    )
    rebuild_index(kb)

    first = generate_health_report(kb)
    snapshot = load_materialized_view(kb, "health")
    assert snapshot is not None
    assert snapshot["payload"]["total_modules"] == 1

    def explode(*_args, **_kwargs):
        raise AssertionError("health report recomputed instead of reusing snapshot")

    monkeypatch.setattr(storage, "compute_module_health", explode)
    second = generate_health_report(kb)

    assert second.total_modules == first.total_modules == 1


def test_recommendations_snapshot_invalidates_after_save_module(tmp_path):
    from knowledge_manager.materialized_views import load_materialized_view

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="recommend snapshot"), kb)
    save_module(
        Module(
            id="incident-core",
            category="ops",
            title="Incident Core",
            summary="Incident summary.",
            content=ModuleContent(
                overview="Rollback alert overview.",
                details="Incident response details long enough for validation.",
            ),
            metadata=ModuleMetadata(tags=["incident", "rollback"]),
        ),
        kb,
    )
    rebuild_index(kb)

    before = generate_recommendations(kb)
    before_snapshot = load_materialized_view(kb, "recommendations")
    assert before_snapshot is not None

    save_module(
        Module(
            id="incident-links",
            category="ops",
            title="Incident Links",
            summary="Incident link summary.",
            content=ModuleContent(
                overview="Rollback alert overview.",
                details="Incident response companion details long enough for validation.",
            ),
            metadata=ModuleMetadata(tags=["incident", "rollback"]),
        ),
        kb,
    )
    rebuild_index(kb)

    after = generate_recommendations(kb)
    after_snapshot = load_materialized_view(kb, "recommendations")

    assert len(before.suggested_links) == 0
    assert len(after.suggested_links) >= 1
    assert after_snapshot is not None
    assert after_snapshot["generated_at"] != before_snapshot["generated_at"]


def test_ops_report_snapshot_invalidates_after_source_or_staging_change(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="ops snapshot"), kb)
    registry = SourceRegistry(
        sources={
            "team-docs": SourceDefinition(
                id="team-docs",
                confluence=ConfluenceSourceConfig(
                    base_url="https://example.atlassian.net/wiki",
                    space_key="ENG",
                    email="docs@example.com",
                    api_token_env="CONFLUENCE_API_TOKEN",
                    category="ops",
                ),
                sync=SourceSyncState(page_versions={"123": "1"}),
            )
        }
    )
    save_source_registry(registry, kb)

    first = generate_ops_report(kb)
    assert first.source_backlog[0].tracked_pages == 1
    save_staging_meta(
        StagingMeta(
            module_id="pending-module",
            status="changes-requested",
            reviews=[ReviewRecord(reviewer="alice", action="changes-requested", comment="Needs fixes")],
        ),
        kb / ".staging",
    )

    updated_registry = registry.model_copy(
        update={
            "sources": {
                "team-docs": registry.sources["team-docs"].model_copy(
                    update={
                        "sync": registry.sources["team-docs"].sync.model_copy(
                            update={"page_versions": {"123": "1", "456": "2"}}
                        )
                    }
                )
            }
        }
    )
    save_source_registry(updated_registry, kb)

    second = generate_ops_report(kb)
    assert second.source_backlog[0].tracked_pages == 2
    assert second.lifecycle_backlog.staging_status_counts["changes-requested"] == 1


def test_admin_dashboard_reuses_snapshot_and_invalidates_on_job_change(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="admin dashboard"), kb)
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

    first = build_admin_dashboard(kb)
    assert first["ingestion_jobs"] == []
    snapshot_path = kb / ".cache" / "views" / "admin_dashboard.snapshot.json"
    assert snapshot_path.exists()

    create_ingestion_job(kb, source_id="team-docs", trigger="manual")

    second = build_admin_dashboard(kb)
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))["payload"]
    assert len(second["ingestion_jobs"]) == 1
    assert len(payload["ingestion_jobs"]) == 1


def test_admin_dashboard_cached_snapshot_avoids_full_fingerprint_scan(tmp_path, monkeypatch):
    import knowledge_manager.materialized_views as materialized_views

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="admin dashboard fingerprint cache"), kb)
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

    first = build_admin_dashboard(kb)
    assert first["review_backlog"][0]["module_id"] == "review-me"

    def explode(*_args, **_kwargs):
        raise AssertionError("cached snapshot should not require a full fingerprint scan")

    monkeypatch.setattr(materialized_views, "_scan_materialized_fingerprint", explode)
    second = build_admin_dashboard(kb)

    assert second["review_backlog"][0]["module_id"] == "review-me"


def test_admin_dashboard_reuses_ops_report_and_staging_reads_within_single_build(tmp_path, monkeypatch):
    from knowledge_manager.schemas import Index, Module, ModuleContent, OpsReport, SourceBacklogEntry, StagingMeta
    from knowledge_manager.storage import save_index, save_staging_meta, save_to_staging

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="admin dashboard reuse"), kb)
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

    ops_calls = {"count": 0}
    staging_calls = {"count": 0}

    def fake_generate_ops_report(path, *args, **kwargs):
        assert path == kb
        ops_calls["count"] += 1
        return OpsReport(source_backlog=[SourceBacklogEntry(source_id="team-docs", tracked_pages=1)])

    def counted_list_staging_meta(path):
        assert path == kb / ".staging"
        staging_calls["count"] += 1
        return [StagingMeta(module_id="review-me", status="pending")]

    monkeypatch.setattr("knowledge_manager.admin_views.generate_ops_report", fake_generate_ops_report, raising=False)
    monkeypatch.setattr("knowledge_manager.admin_views.list_staging_meta", counted_list_staging_meta, raising=False)

    payload = build_admin_dashboard(kb)

    assert payload["stale_sources"][0]["source_id"] == "team-docs"
    assert payload["review_backlog"][0]["module_id"] == "review-me"
    assert ops_calls["count"] == 1
    assert staging_calls["count"] == 1
