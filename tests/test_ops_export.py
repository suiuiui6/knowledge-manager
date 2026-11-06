import json

from knowledge_manager.ops_export import (
    generate_review_backlog_export,
    generate_risky_miss_export,
    generate_source_backlog_export,
)
from knowledge_manager.schemas import (
    ConfluenceSourceConfig,
    Module,
    ModuleContent,
    SourceDefinition,
    SourceRegistry,
    SourceSyncState,
    StagingMeta,
)
from knowledge_manager.source_ingestion import save_source_registry
from knowledge_manager.storage import load_search_events, record_search_event, save_module, save_staging_meta, search_modules


def test_generate_review_backlog_export_accepts_precomputed_inputs(tmp_path, monkeypatch):
    from knowledge_manager.schemas import LifecycleBacklog, OpsReport, SourceBacklogEntry, StagingMeta

    kb = tmp_path / "kb"
    kb.mkdir()

    monkeypatch.setattr(
        "knowledge_manager.ops_export.generate_ops_report",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("review export should reuse provided ops report")
        ),
    )
    monkeypatch.setattr(
        "knowledge_manager.ops_export.list_staging_meta",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("review export should reuse provided staging metadata")
        ),
    )

    export = generate_review_backlog_export(
        kb,
        report=OpsReport(
            source_backlog=[SourceBacklogEntry(source_id="team-docs", tracked_pages=1)],
            lifecycle_backlog=LifecycleBacklog(staging_status_counts={"pending": 1}),
        ),
        staging_meta=[StagingMeta(module_id="review-me", status="pending")],
    )

    assert export["total"] == 1
    assert export["items"][0]["module_id"] == "review-me"
    assert export["stale_sources"][0]["source_id"] == "team-docs"


def test_generate_review_backlog_export_includes_stale_sources(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "index.json").write_text('{"version":"1.0","categories":{},"graph":{},"stats":{"total_modules":0,"total_words":0,"categories":0},"updated_at":"2026-06-12T00:00:00Z"}', encoding="utf-8")
    save_source_registry(
        SourceRegistry(
            sources={
                "confluence-ops": SourceDefinition(
                    id="confluence-ops",
                    confluence=ConfluenceSourceConfig(
                        base_url="https://example.atlassian.net/wiki",
                        space_key="OPS",
                        email="ops@example.com",
                        api_token_env="CONFLUENCE_API_TOKEN",
                        category="ops",
                    ),
                    sync=SourceSyncState(page_versions={"123": "7"}),
                )
            }
        ),
        kb,
    )
    save_staging_meta(StagingMeta(module_id="review-me", status="pending"), kb / ".staging")

    export = generate_review_backlog_export(kb)

    assert export["total"] == 1
    assert export["items"][0]["module_id"] == "review-me"
    assert export["stale_sources"][0]["source_id"] == "confluence-ops"


def test_generate_risky_miss_export_collects_zero_result_queries(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    record_search_event("deploy rollback", [], kb)
    record_search_event("healthy query", ["ops/runbook"], kb)

    export = generate_risky_miss_export(kb)

    assert export["total"] == 1
    assert export["items"][0]["query_terms"]


def test_generate_risky_miss_export_ignores_vector_fallback_successes(tmp_path, monkeypatch):
    kb = tmp_path / "kb"
    kb.mkdir()
    save_module(
        Module(
            id="legacy-acronym",
            category="ops",
            title="Legacy Acronym Guide",
            summary="Legacy acronym reference for operations.",
            content=ModuleContent(
                overview="Legacy acronym overview.",
                details="Legacy acronym details with enough length for validation.",
            ),
        ),
        kb,
    )
    monkeypatch.setattr(
        "knowledge_manager.vector_index.VectorIndex.search",
        lambda self, query, top_k=20: [("ops/legacy-acronym", 0.91)],
    )

    results = search_modules("zzqv", kb, enable_vector_fallback=True)

    assert results
    assert len(load_search_events(kb)) == 1
    export = generate_risky_miss_export(kb)
    assert export["total"] == 0


def test_generate_source_backlog_export_returns_items(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    save_source_registry(
        SourceRegistry(
            sources={
                "confluence-ops": SourceDefinition(
                    id="confluence-ops",
                    confluence=ConfluenceSourceConfig(
                        base_url="https://example.atlassian.net/wiki",
                        space_key="OPS",
                        email="ops@example.com",
                        api_token_env="CONFLUENCE_API_TOKEN",
                        category="ops",
                    ),
                )
            }
        ),
        kb,
    )

    export = generate_source_backlog_export(kb)

    assert export["total"] == 1
    assert export["items"][0]["source_id"] == "confluence-ops"


def test_generate_source_backlog_export_accepts_precomputed_report(tmp_path, monkeypatch):
    from knowledge_manager.schemas import OpsReport, SourceBacklogEntry

    kb = tmp_path / "kb"
    kb.mkdir()
    monkeypatch.setattr(
        "knowledge_manager.ops_export.generate_ops_report",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("source export should reuse provided ops report")
        ),
    )

    export = generate_source_backlog_export(
        kb,
        report=OpsReport(source_backlog=[SourceBacklogEntry(source_id="team-docs", tracked_pages=1)]),
    )

    assert export["total"] == 1
    assert export["items"][0]["source_id"] == "team-docs"
