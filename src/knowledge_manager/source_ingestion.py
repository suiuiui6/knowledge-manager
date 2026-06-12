from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Protocol
from uuid import uuid4

from knowledge_manager.confluence import ConfluencePage
from knowledge_manager.notion import NotionPage
from knowledge_manager.schemas import (
    Module,
    SourceDefinition,
    SourceDocumentRef,
    SourceRegistry,
    SourceSpan,
    SourceSyncState,
)
from knowledge_manager.storage import (
    _atomic_write,
    mark_source_documents_changed,
    list_modules,
    save_staging_meta,
    save_to_staging,
)
from knowledge_manager.schemas import StagingMeta


class IngestionPage(Protocol):
    page_id: str
    title: str
    url: str
    version: str
    body_text: str
    heading_path: list[str]
    checksum: str


@dataclass
class IngestionSummary:
    source_id: str
    pages_seen: int = 0
    modules_staged: int = 0
    modules_marked_stale: int = 0


def _registry_path(kb_path: Path) -> Path:
    return kb_path / ".sources" / "registry.json"


def load_source_registry(kb_path: Path) -> SourceRegistry:
    path = _registry_path(kb_path)
    if not path.exists():
        return SourceRegistry()
    return SourceRegistry.model_validate_json(path.read_text(encoding="utf-8"))


def save_source_registry(registry: SourceRegistry, kb_path: Path) -> None:
    validated = SourceRegistry.model_validate(registry.model_dump(mode="python"))
    _atomic_write(_registry_path(kb_path), validated.model_dump_json(indent=2))


def upsert_source(source: SourceDefinition, kb_path: Path) -> None:
    registry = load_source_registry(kb_path)
    registry.sources[source.id] = source.model_copy(update={"id": source.id})
    save_source_registry(registry, kb_path)


def update_source_sync(source_id: str, sync: SourceSyncState, kb_path: Path) -> None:
    registry = load_source_registry(kb_path)
    source = registry.sources[source_id]
    existing = source.sync
    merged = existing.model_copy(
        update={
            "last_cursor": sync.last_cursor or existing.last_cursor,
            "last_synced_at": sync.last_synced_at or existing.last_synced_at,
            "last_error": sync.last_error,
            "page_versions": existing.page_versions | sync.page_versions,
        }
    )
    registry.sources[source_id] = source.model_copy(update={"sync": merged})
    save_source_registry(registry, kb_path)


def record_source_sync_error(source_id: str, error: str, kb_path: Path) -> None:
    registry = load_source_registry(kb_path)
    source = registry.sources[source_id]
    merged = source.sync.model_copy(
        update={
            "last_error": error,
            "last_synced_at": datetime.now(timezone.utc),
        }
    )
    registry.sources[source_id] = source.model_copy(update={"sync": merged})
    save_source_registry(registry, kb_path)


def _source_category(source: SourceDefinition) -> str:
    if source.type == "confluence" and source.confluence is not None:
        return source.confluence.category
    if source.type == "notion" and source.notion is not None:
        return source.notion.category
    return "general"


def _stamp_module(module: Module, source: SourceDefinition, page: IngestionPage, run_id: str) -> Module:
    excerpt = page.body_text[:200]
    return module.model_copy(
        update={
            "metadata": module.metadata.model_copy(
                update={
                    "source": source.id,
                    "source_documents": [
                        SourceDocumentRef(
                            source_type=source.type,
                            source_id=source.id,
                            external_id=page.page_id,
                            title=page.title,
                            url=page.url,
                            version=page.version,
                            checksum=page.checksum,
                        )
                    ],
                    "source_spans": [
                        SourceSpan(
                            external_id=page.page_id,
                            heading_path=page.heading_path,
                            excerpt=excerpt,
                            char_start=0,
                            char_end=len(excerpt),
                        )
                    ],
                    "extraction_run_id": run_id,
                    "derived_from": [page.page_id],
                    "stale_due_to_source_change": False,
                }
            )
        }
    )


def mark_modules_stale(source_id: str, page_versions: dict[str, str], kb_path: Path) -> int:
    scoped_versions: dict[str, str] = {}
    for module in list_modules(kb_path):
        for doc in module.metadata.source_documents:
            if doc.source_id == source_id and doc.external_id in page_versions:
                scoped_versions[doc.external_id] = page_versions[doc.external_id]
    return len(mark_source_documents_changed(scoped_versions, kb_path))


async def ingest_confluence_pages(
    source: SourceDefinition,
    pages: Iterable[ConfluencePage | NotionPage],
    kb_path: Path,
    extractor,
    next_cursor: str = "",
) -> IngestionSummary:
    run_id = f"{source.id}-{uuid4().hex[:12]}"
    staging_path = kb_path / ".staging"
    summary = IngestionSummary(source_id=source.id)
    page_versions: dict[str, str] = {}

    for page in pages:
        summary.pages_seen += 1
        modules = await extractor.extract(page.body_text, _source_category(source))
        page_versions[page.page_id] = page.version
        for module in modules:
            stamped = _stamp_module(module, source, page, run_id)
            save_to_staging(stamped, staging_path)
            save_staging_meta(
                StagingMeta(module_id=stamped.id, submitted_by=f"source:{source.id}"),
                staging_path,
            )
            summary.modules_staged += 1

    summary.modules_marked_stale = mark_modules_stale(source.id, page_versions, kb_path)
    update_source_sync(
        source.id,
        SourceSyncState(
            last_cursor=next_cursor,
            last_synced_at=datetime.now(timezone.utc),
            last_error="",
            page_versions=page_versions,
        ),
        kb_path,
    )
    return summary
