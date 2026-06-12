from datetime import datetime, timezone

from knowledge_manager.confluence import ConfluencePage
from knowledge_manager.schemas import (
    ConfluenceSourceConfig,
    Module,
    ModuleContent,
    NotionSourceConfig,
    SourceDefinition,
    SourceDocumentRef,
    SourceRegistry,
    SourceSyncState,
)
from knowledge_manager.source_ingestion import (
    _registry_path,
    ingest_confluence_pages,
    load_source_registry,
    save_source_registry,
    upsert_source,
    update_source_sync,
)
from knowledge_manager.storage import load_from_staging, load_staging_meta, save_module


def _make_source(source_id: str = "team-docs") -> SourceDefinition:
    return SourceDefinition(
        id=source_id,
        confluence=ConfluenceSourceConfig(
            base_url="https://example.atlassian.net/wiki",
            space_key="ENG",
            email="docs@example.com",
            api_token_env="CONFLUENCE_API_TOKEN",
            root_page_id="12345",
            category="architecture",
            page_limit=10,
        ),
    )


def _make_page(version: str = "7") -> ConfluencePage:
    return ConfluencePage(
        page_id="12345",
        title="JWT Runbook",
        url="https://example.atlassian.net/wiki/spaces/ENG/pages/12345",
        version=version,
        body_text="Refresh tokens rotate on every successful refresh.",
        heading_path=["ENG", "JWT Runbook"],
        checksum="abc123",
    )


def _make_notion_source(source_id: str = "ops-notes") -> SourceDefinition:
    return SourceDefinition(
        id=source_id,
        type="notion",
        notion=NotionSourceConfig(
            api_token_env="NOTION_TOKEN",
            database_id="db-1",
            category="operations",
            page_limit=10,
        ),
    )


class FakeExtractor:
    async def extract(self, text: str, category: str, existing_categories: str = "") -> list[Module]:
        return [
            Module(
                id="jwt-playbook",
                category=category,
                title="JWT Playbook",
                summary="How we operate JWT auth in production.",
                content=ModuleContent(
                    overview="JWT auth in production uses short-lived access tokens.",
                    details="We use short-lived access tokens plus refresh rotation and Redis-backed revocation.",
                ),
            )
        ]


def test_source_registry_round_trip(tmp_path):
    kb_path = tmp_path / "kb"
    synced_at = datetime(2026, 6, 11, 14, 30, tzinfo=timezone.utc)
    registry = SourceRegistry(
        sources={
            "team-docs": _make_source().model_copy(
                update={"sync": SourceSyncState(last_cursor="cursor-1", last_synced_at=synced_at)}
            )
        }
    )

    save_source_registry(registry, kb_path)
    loaded = load_source_registry(kb_path)

    assert _registry_path(kb_path).exists()
    assert loaded == registry


def test_update_source_sync_merges_partial_state(tmp_path):
    kb_path = tmp_path / "kb"
    upsert_source(
        _make_source().model_copy(
            update={
                "sync": SourceSyncState(
                    last_cursor="cursor-1",
                    last_synced_at=datetime(2026, 6, 11, 14, 30, tzinfo=timezone.utc),
                    page_versions={"12345": "7"},
                )
            }
        ),
        kb_path,
    )

    update_source_sync("team-docs", SourceSyncState(last_error="rate limited"), kb_path)
    loaded = load_source_registry(kb_path)

    assert loaded.sources["team-docs"].sync.last_cursor == "cursor-1"
    assert loaded.sources["team-docs"].sync.page_versions == {"12345": "7"}
    assert loaded.sources["team-docs"].sync.last_error == "rate limited"


async def test_ingest_confluence_pages_stamps_provenance_and_marks_stale(tmp_path):
    kb_path = tmp_path / "kb"
    (kb_path / ".staging").mkdir(parents=True)
    upsert_source(_make_source(), kb_path)

    existing = Module(
        id="jwt-existing",
        category="architecture",
        title="JWT Existing",
        summary="Current JWT production guidance for auth.",
        content=ModuleContent(
            overview="Current JWT production guidance overview.",
            details="Current JWT production guidance details that are long enough.",
        ),
    )
    existing.metadata.source = "team-docs"
    existing.metadata.source_documents.append(
        SourceDocumentRef(
            source_type="confluence",
            source_id="team-docs",
            external_id="12345",
            title="JWT Runbook",
            url="https://example.atlassian.net/wiki/spaces/ENG/pages/12345",
            version="6",
            checksum="old",
        )
    )
    save_module(existing, kb_path)

    summary = await ingest_confluence_pages(_make_source(), [_make_page("7")], kb_path, FakeExtractor())
    staged = load_from_staging("jwt-playbook", kb_path / ".staging")

    assert summary.pages_seen == 1
    assert summary.modules_staged == 1
    assert summary.modules_marked_stale == 1
    assert staged is not None
    assert staged.metadata.source_documents[0].external_id == "12345"
    assert staged.metadata.source_spans[0].heading_path == ["ENG", "JWT Runbook"]
    meta = load_staging_meta("jwt-playbook", kb_path / ".staging")
    assert meta is not None
    assert meta.submitted_by == "source:team-docs"
    loaded = load_source_registry(kb_path)
    assert loaded.sources["team-docs"].sync.page_versions["12345"] == "7"


async def test_ingest_notion_pages_stamps_notion_source_type(tmp_path):
    from knowledge_manager.notion import NotionPage

    kb_path = tmp_path / "kb"
    (kb_path / ".staging").mkdir(parents=True)
    upsert_source(_make_notion_source(), kb_path)

    summary = await ingest_confluence_pages(
        _make_notion_source(),
        [
            NotionPage(
                page_id="page-1",
                title="Ops Runbook",
                url="https://notion.so/page-1",
                version="2026-06-12T08:00:00.000Z",
                body_text="Escalations route through the primary on-call.",
                heading_path=["Notion", "Ops Runbook"],
                checksum="xyz123",
            )
        ],
        kb_path,
        FakeExtractor(),
    )

    staged = load_from_staging("jwt-playbook", kb_path / ".staging")
    assert summary.pages_seen == 1
    assert staged is not None
    assert staged.category == "operations"
    assert staged.metadata.source_documents[0].source_type == "notion"
