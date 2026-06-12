import json

from knowledge_manager.ops_export import (
    generate_review_backlog_export,
    generate_risky_miss_export,
    generate_source_backlog_export,
)
from knowledge_manager.schemas import (
    ConfluenceSourceConfig,
    SourceDefinition,
    SourceRegistry,
    SourceSyncState,
    StagingMeta,
)
from knowledge_manager.source_ingestion import save_source_registry
from knowledge_manager.storage import record_search_event, save_staging_meta


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
