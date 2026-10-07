# V1 Enterprise Ingestion, Provenance, and Eval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first migration-worthy V1 slice for `knowledge-manager`: one flagship enterprise source connector, provenance-aware staged modules, and a narrow benchmark runner that can compare required-module retrieval against a baseline workflow.

**Architecture:** Keep the existing flat `src/knowledge_manager/*.py` layout. Add a small source-ingestion orchestration layer that pulls normalized Confluence pages, runs them through the existing `Extractor`, stamps provenance fields onto staged modules, and persists sync state in `.sources/registry.json`. Add a minimal eval runner that scores whether `search_modules()` returns required modules inside a configurable `top_k`, without introducing a second retrieval path.

**Tech Stack:** Python, Pydantic, Click, httpx, pytest, unittest.mock/AsyncMock, existing `Extractor`, existing storage helpers, existing CLI test runner (`CliRunner`)

---

## Scope decision

The approved spec spans V1, V2, and V3. That is too broad for a single implementation plan. This plan intentionally covers **V1 only**:

1. one flagship connector (`Confluence`)
2. module provenance fields and stale-source invalidation
3. a task-level eval harness

V2 (routing policy / operations console / lifecycle workflow) and V3 (auth/audit / dual views / hybrid fallback) should each get their own plan after V1 ships.

## File structure

### Existing files to modify

- `knowledge-manager/src/knowledge_manager/schemas.py`
  - Extend module metadata with provenance fields.
  - Add source-registry models used by the ingestion pipeline.
- `knowledge-manager/src/knowledge_manager/cli.py`
  - Add `source` and `eval` command groups.
  - Wire CLI entrypoints to the new ingestion and benchmark modules.
- `knowledge-manager/tests/test_cli.py`
  - Add CLI coverage for `source add-confluence`, `source pull`, `source status`, and `eval run`.
- `knowledge-manager/tests/test_schemas.py`
  - Add schema coverage for new provenance and source-registry models.

### New files to create

- `knowledge-manager/src/knowledge_manager/confluence.py`
  - Read-only Confluence client that normalizes API responses into local `ConfluencePage` objects.
- `knowledge-manager/src/knowledge_manager/source_ingestion.py`
  - Source registry persistence, sync-state updates, provenance stamping, and stale invalidation.
- `knowledge-manager/src/knowledge_manager/eval_runner.py`
  - Eval case models and a runner that executes `search_modules()` against JSON test cases.
- `knowledge-manager/tests/test_confluence.py`
  - Unit tests for response normalization and error handling in the Confluence client.
- `knowledge-manager/tests/test_source_ingestion.py`
  - Unit tests for registry persistence, ingestion summaries, provenance stamping, and stale marking.
- `knowledge-manager/tests/test_eval_runner.py`
  - Unit tests for benchmark scoring and eval CLI output.

### Data files created at runtime

- `<kb>/.sources/registry.json`
  - Stores source definitions plus sync state. No secrets; only env-var names.
- `<kb>/.staging/*.json` + `<kb>/.staging/*.meta.json`
  - Existing staging flow remains the publication gate.

---

### Task 1: Add provenance models to module metadata

**Files:**
- Modify: `knowledge-manager/src/knowledge_manager/schemas.py`
- Test: `knowledge-manager/tests/test_schemas.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to knowledge-manager/tests/test_schemas.py

from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata, SourceDocumentRef, SourceSpan


def test_module_metadata_provenance_defaults():
    metadata = ModuleMetadata()
    assert metadata.source_documents == []
    assert metadata.source_spans == []
    assert metadata.extraction_run_id == ""
    assert metadata.reviewed_by == ""
    assert metadata.reviewed_at is None
    assert metadata.stale_due_to_source_change is False
    assert metadata.supersedes == ""
    assert metadata.derived_from == ""


def test_module_round_trip_with_provenance():
    module = Module(
        id="jwt-playbook",
        category="auth",
        title="JWT Playbook",
        summary="How we operate JWT auth in production.",
        content=ModuleContent(
            overview="JWT auth in production uses short-lived access tokens.",
            details="We use short-lived access tokens plus refresh rotation and Redis-backed revocation.",
        ),
        metadata=ModuleMetadata(
            source_documents=[
                SourceDocumentRef(
                    source_type="confluence",
                    source_id="team-wiki",
                    external_id="12345",
                    title="JWT Runbook",
                    version="7",
                    url="https://wiki.example/pages/12345",
                    checksum="abc123",
                )
            ],
            source_spans=[
                SourceSpan(
                    external_id="12345",
                    heading_path=["Authentication", "JWT"],
                    excerpt="Refresh tokens rotate on every successful refresh.",
                    char_start=120,
                    char_end=176,
                )
            ],
            extraction_run_id="run-1",
            reviewed_by="alice",
            stale_due_to_source_change=True,
        ),
    )

    restored = Module.model_validate_json(module.model_dump_json())
    assert restored.metadata.source_documents[0].external_id == "12345"
    assert restored.metadata.source_spans[0].heading_path == ["Authentication", "JWT"]
    assert restored.metadata.reviewed_by == "alice"
    assert restored.metadata.stale_due_to_source_change is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest knowledge-manager/tests/test_schemas.py::test_module_metadata_provenance_defaults knowledge-manager/tests/test_schemas.py::test_module_round_trip_with_provenance -v`
Expected: FAIL because `SourceDocumentRef`, `SourceSpan`, and the new metadata fields do not exist yet.

- [ ] **Step 3: Add the provenance models and metadata fields**

```python
# Insert near ModuleContent in knowledge-manager/src/knowledge_manager/schemas.py

class SourceDocumentRef(BaseModel):
    source_type: Literal["confluence"] = "confluence"
    source_id: str
    external_id: str
    title: str
    url: str = ""
    version: str = ""
    checksum: str = ""
    fetched_at: datetime = Field(default_factory=utc_now)


class SourceSpan(BaseModel):
    external_id: str
    heading_path: list[str] = Field(default_factory=list)
    excerpt: str = ""
    char_start: Optional[int] = None
    char_end: Optional[int] = None


class ModuleMetadata(BaseModel):
    tags: List[str] = Field(default_factory=list)
    related_modules: List[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"
    source: str = Field(default="")
    expires_at: Optional[datetime] = None
    review_interval_days: Optional[int] = None
    status: Literal["draft", "reviewed", "published", "deprecated", "archived"] = "published"
    source_documents: List[SourceDocumentRef] = Field(default_factory=list)
    source_spans: List[SourceSpan] = Field(default_factory=list)
    extraction_run_id: str = ""
    reviewed_by: str = ""
    reviewed_at: Optional[datetime] = None
    stale_due_to_source_change: bool = False
    supersedes: str = ""
    derived_from: str = ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest knowledge-manager/tests/test_schemas.py::test_module_metadata_provenance_defaults knowledge-manager/tests/test_schemas.py::test_module_round_trip_with_provenance -v`
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add knowledge-manager/src/knowledge_manager/schemas.py knowledge-manager/tests/test_schemas.py
git commit -m "feat: add provenance metadata to modules"
```

---

### Task 2: Persist source definitions and sync state

**Files:**
- Modify: `knowledge-manager/src/knowledge_manager/schemas.py`
- Create: `knowledge-manager/src/knowledge_manager/source_ingestion.py`
- Test: `knowledge-manager/tests/test_source_ingestion.py`

- [ ] **Step 1: Write the failing tests**

```python
# Create knowledge-manager/tests/test_source_ingestion.py

from knowledge_manager.schemas import ConfluenceSourceConfig, SourceDefinition, SourceRegistry, SourceSyncState
from knowledge_manager.source_ingestion import load_source_registry, save_source_registry


def test_source_registry_round_trip(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()

    registry = SourceRegistry(
        sources={
            "team-wiki": SourceDefinition(
                id="team-wiki",
                type="confluence",
                confluence=ConfluenceSourceConfig(
                    base_url="https://wiki.example",
                    space_key="ENG",
                    email="bot@example.com",
                    api_token_env="CONFLUENCE_TOKEN",
                    category="architecture",
                ),
                sync=SourceSyncState(last_cursor="cursor-1"),
            )
        }
    )

    save_source_registry(registry, kb)
    restored = load_source_registry(kb)

    assert "team-wiki" in restored.sources
    assert restored.sources["team-wiki"].confluence.space_key == "ENG"
    assert restored.sources["team-wiki"].sync.last_cursor == "cursor-1"


def test_load_source_registry_defaults_when_missing(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()

    restored = load_source_registry(kb)

    assert restored.sources == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest knowledge-manager/tests/test_source_ingestion.py::test_source_registry_round_trip knowledge-manager/tests/test_source_ingestion.py::test_load_source_registry_defaults_when_missing -v`
Expected: FAIL because the registry models and helper module do not exist.

- [ ] **Step 3: Add source-registry schemas and persistence helpers**

```python
# Append to knowledge-manager/src/knowledge_manager/schemas.py

class ConfluenceSourceConfig(BaseModel):
    base_url: str
    space_key: str
    email: str
    api_token_env: str
    root_page_id: str = ""
    category: str = "general"
    page_limit: int = 25


class SourceSyncState(BaseModel):
    last_cursor: str = ""
    last_synced_at: Optional[datetime] = None
    last_error: str = ""
    page_versions: Dict[str, str] = Field(default_factory=dict)


class SourceDefinition(BaseModel):
    id: str
    type: Literal["confluence"] = "confluence"
    enabled: bool = True
    confluence: ConfluenceSourceConfig
    sync: SourceSyncState = Field(default_factory=SourceSyncState)


class SourceRegistry(BaseModel):
    sources: Dict[str, SourceDefinition] = Field(default_factory=dict)
```

```python
# Create knowledge-manager/src/knowledge_manager/source_ingestion.py

from pathlib import Path

from knowledge_manager.schemas import SourceDefinition, SourceRegistry, SourceSyncState
from knowledge_manager.storage import _atomic_write


def _registry_path(kb_path: Path) -> Path:
    return kb_path / ".sources" / "registry.json"


def load_source_registry(kb_path: Path) -> SourceRegistry:
    path = _registry_path(kb_path)
    if not path.exists():
        return SourceRegistry()
    return SourceRegistry.model_validate_json(path.read_text(encoding="utf-8"))


def save_source_registry(registry: SourceRegistry, kb_path: Path) -> None:
    path = _registry_path(kb_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, registry.model_dump_json(indent=2))


def upsert_source(source: SourceDefinition, kb_path: Path) -> None:
    registry = load_source_registry(kb_path)
    registry.sources[source.id] = source
    save_source_registry(registry, kb_path)


def update_source_sync(source_id: str, sync: SourceSyncState, kb_path: Path) -> None:
    registry = load_source_registry(kb_path)
    registry.sources[source_id].sync = sync
    save_source_registry(registry, kb_path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest knowledge-manager/tests/test_source_ingestion.py::test_source_registry_round_trip knowledge-manager/tests/test_source_ingestion.py::test_load_source_registry_defaults_when_missing -v`
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add knowledge-manager/src/knowledge_manager/schemas.py knowledge-manager/src/knowledge_manager/source_ingestion.py knowledge-manager/tests/test_source_ingestion.py
git commit -m "feat: persist enterprise source registry"
```

---

### Task 3: Implement a read-only Confluence connector

**Files:**
- Create: `knowledge-manager/src/knowledge_manager/confluence.py`
- Test: `knowledge-manager/tests/test_confluence.py`

- [ ] **Step 1: Write the failing tests**

```python
# Create knowledge-manager/tests/test_confluence.py

import pytest
from unittest.mock import AsyncMock, patch

from knowledge_manager.confluence import ConfluenceClient


@pytest.mark.asyncio
async def test_confluence_client_normalizes_pages():
    payload = {
        "results": [
            {
                "id": "12345",
                "title": "JWT Runbook",
                "version": {"number": 7},
                "body": {"storage": {"value": "<p>Refresh tokens rotate on each use.</p>"}},
                "_links": {"webui": "/spaces/ENG/pages/12345"},
            }
        ]
    }

    response = AsyncMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None

    client_ctx = AsyncMock()
    client_ctx.__aenter__.return_value.get.return_value = response

    with patch("knowledge_manager.confluence.httpx.AsyncClient", return_value=client_ctx):
        client = ConfluenceClient("https://wiki.example", "bot@example.com", "token")
        pages = await client.list_pages("ENG", limit=10)

    assert len(pages) == 1
    assert pages[0].id == "12345"
    assert pages[0].version == "7"
    assert "Refresh tokens rotate" in pages[0].body


@pytest.mark.asyncio
async def test_confluence_client_raises_for_http_errors():
    response = AsyncMock()
    response.raise_for_status.side_effect = RuntimeError("boom")

    client_ctx = AsyncMock()
    client_ctx.__aenter__.return_value.get.return_value = response

    with patch("knowledge_manager.confluence.httpx.AsyncClient", return_value=client_ctx):
        client = ConfluenceClient("https://wiki.example", "bot@example.com", "token")
        with pytest.raises(RuntimeError, match="boom"):
            await client.list_pages("ENG")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest knowledge-manager/tests/test_confluence.py -v`
Expected: FAIL because `knowledge_manager.confluence` does not exist.

- [ ] **Step 3: Implement the connector**

```python
# Create knowledge-manager/src/knowledge_manager/confluence.py

import re
from dataclasses import dataclass

import httpx


@dataclass
class ConfluencePage:
    id: str
    title: str
    version: str
    body: str
    url: str = ""


def _strip_html(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value)
    value = re.sub(r"</p>", "\n", value)
    value = re.sub(r"<[^>]+>", "", value)
    return value.strip()


class ConfluenceClient:
    def __init__(self, base_url: str, email: str, api_token: str):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.api_token = api_token

    async def list_pages(self, space_key: str, limit: int = 25) -> list[ConfluencePage]:
        async with httpx.AsyncClient(auth=(self.email, self.api_token), timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/wiki/api/v2/pages",
                params={"spaceKey": space_key, "limit": limit, "body-format": "storage"},
            )
            response.raise_for_status()
            payload = response.json()

        pages: list[ConfluencePage] = []
        for item in payload.get("results", []):
            raw_body = item.get("body", {}).get("storage", {}).get("value", "")
            webui = item.get("_links", {}).get("webui", "")
            url = webui if webui.startswith("http") else f"{self.base_url}{webui}"
            pages.append(
                ConfluencePage(
                    id=str(item["id"]),
                    title=item.get("title", ""),
                    version=str(item.get("version", {}).get("number", "")),
                    body=_strip_html(raw_body),
                    url=url,
                )
            )
        return pages
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest knowledge-manager/tests/test_confluence.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add knowledge-manager/src/knowledge_manager/confluence.py knowledge-manager/tests/test_confluence.py
git commit -m "feat: add confluence source connector"
```

---

### Task 4: Stage modules from Confluence pages with provenance and stale invalidation

**Files:**
- Modify: `knowledge-manager/src/knowledge_manager/source_ingestion.py`
- Test: `knowledge-manager/tests/test_source_ingestion.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to knowledge-manager/tests/test_source_ingestion.py

import pytest
from unittest.mock import AsyncMock

from knowledge_manager.confluence import ConfluencePage
from knowledge_manager.schemas import (
    ConfluenceSourceConfig,
    Module,
    ModuleContent,
    ModuleMetadata,
    SourceDefinition,
    SourceDocumentRef,
    SourceRegistry,
)
from knowledge_manager.source_ingestion import ingest_source, mark_modules_stale_for_document, save_source_registry
from knowledge_manager.storage import load_from_staging, load_module, rebuild_index, save_module


@pytest.mark.asyncio
async def test_ingest_source_stages_modules_with_provenance(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / ".staging").mkdir()

    registry = SourceRegistry(
        sources={
            "team-wiki": SourceDefinition(
                id="team-wiki",
                confluence=ConfluenceSourceConfig(
                    base_url="https://wiki.example",
                    space_key="ENG",
                    email="bot@example.com",
                    api_token_env="CONFLUENCE_TOKEN",
                    category="auth",
                ),
            )
        }
    )
    save_source_registry(registry, kb)

    connector = AsyncMock()
    connector.list_pages.return_value = [
        ConfluencePage(
            id="12345",
            title="JWT Runbook",
            version="7",
            body="Refresh tokens rotate on each use.",
            url="https://wiki.example/pages/12345",
        )
    ]

    extractor = AsyncMock()
    extractor.extract.return_value = [
        Module(
            id="jwt-runbook",
            category="auth",
            title="JWT Runbook",
            summary="How we run JWT auth in production.",
            content=ModuleContent(
                overview="JWT auth in production uses short-lived access tokens.",
                details="Refresh tokens rotate on each successful refresh and revocation is checked centrally.",
            ),
            metadata=ModuleMetadata(),
        )
    ]

    summary = await ingest_source("team-wiki", kb, connector, extractor)
    staged = load_from_staging("jwt-runbook", kb / ".staging")

    assert summary.pages_fetched == 1
    assert summary.modules_staged == 1
    assert staged is not None
    assert staged.metadata.source_documents[0].external_id == "12345"
    assert staged.metadata.extraction_run_id != ""
    assert staged.metadata.stale_due_to_source_change is False


def test_mark_modules_stale_for_document_sets_flag(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()

    module = Module(
        id="jwt-runbook",
        category="auth",
        title="JWT Runbook",
        summary="How we run JWT auth in production.",
        content=ModuleContent(
            overview="JWT auth in production uses short-lived access tokens.",
            details="Refresh tokens rotate on each successful refresh and revocation is checked centrally.",
        ),
        metadata=ModuleMetadata(source_documents=[]),
    )
    module.metadata.source_documents.append(
        SourceDocumentRef(
            source_type="confluence",
            source_id="team-wiki",
            external_id="12345",
            title="JWT Runbook",
            version="6",
            url="https://wiki.example/pages/12345",
            checksum="old",
        )
    )
    save_module(module, kb)
    rebuild_index(kb)

    changed = mark_modules_stale_for_document("team-wiki", "12345", kb)
    stale_module = load_module("jwt-runbook", "auth", kb)

    assert changed == 1
    assert stale_module is not None
    assert stale_module.metadata.stale_due_to_source_change is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest knowledge-manager/tests/test_source_ingestion.py::test_ingest_source_stages_modules_with_provenance knowledge-manager/tests/test_source_ingestion.py::test_mark_modules_stale_for_document_sets_flag -v`
Expected: FAIL because `ingest_source` and `mark_modules_stale_for_document` do not exist.

- [ ] **Step 3: Implement ingestion orchestration and stale marking**

```python
# Expand knowledge-manager/src/knowledge_manager/source_ingestion.py

import uuid
from dataclasses import dataclass
from pathlib import Path

from knowledge_manager.schemas import SourceDocumentRef, SourceRegistry, SourceSpan, StagingMeta, utc_now
from knowledge_manager.storage import list_modules, save_module, save_staging_meta, save_to_staging


@dataclass
class IngestionSummary:
    source_id: str
    pages_fetched: int = 0
    modules_staged: int = 0
    stale_marked: int = 0


def mark_modules_stale_for_document(source_id: str, external_id: str, kb_path: Path) -> int:
    changed = 0
    for module in list_modules(kb_path):
        if not any(doc.source_id == source_id and doc.external_id == external_id for doc in module.metadata.source_documents):
            continue
        module.metadata.stale_due_to_source_change = True
        module.updated_at = utc_now()
        save_module(module, kb_path)
        changed += 1
    return changed


async def ingest_source(source_id: str, kb_path: Path, connector, extractor) -> IngestionSummary:
    registry = load_source_registry(kb_path)
    source = registry.sources[source_id]
    pages = await connector.list_pages(source.confluence.space_key, limit=source.confluence.page_limit)

    run_id = str(uuid.uuid4())
    summary = IngestionSummary(source_id=source_id, pages_fetched=len(pages))
    staging = kb_path / ".staging"
    staging.mkdir(exist_ok=True)

    for page in pages:
        previous_version = source.sync.page_versions.get(page.id, "")
        if previous_version and previous_version != page.version:
            summary.stale_marked += mark_modules_stale_for_document(source_id, page.id, kb_path)

        modules = await extractor.extract(page.body, source.confluence.category)
        checksum = str(abs(hash(page.body)))

        for module in modules:
            module.metadata.source = f"confluence:{source_id}:{page.id}"
            module.metadata.source_documents = [
                SourceDocumentRef(
                    source_type="confluence",
                    source_id=source_id,
                    external_id=page.id,
                    title=page.title,
                    url=page.url,
                    version=page.version,
                    checksum=checksum,
                )
            ]
            module.metadata.source_spans = [
                SourceSpan(
                    external_id=page.id,
                    heading_path=[page.title],
                    excerpt=page.body[:240],
                    char_start=0,
                    char_end=min(len(page.body), 240),
                )
            ]
            module.metadata.extraction_run_id = run_id
            module.metadata.stale_due_to_source_change = False
            save_to_staging(module, staging)
            save_staging_meta(StagingMeta(module_id=module.id, submitted_by=f"source:{source_id}"), staging)
            summary.modules_staged += 1

        source.sync.page_versions[page.id] = page.version

    source.sync.last_synced_at = utc_now()
    source.sync.last_error = ""
    save_source_registry(registry, kb_path)
    return summary
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest knowledge-manager/tests/test_source_ingestion.py::test_ingest_source_stages_modules_with_provenance knowledge-manager/tests/test_source_ingestion.py::test_mark_modules_stale_for_document_sets_flag -v`
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add knowledge-manager/src/knowledge_manager/source_ingestion.py knowledge-manager/tests/test_source_ingestion.py
git commit -m "feat: stage source-ingested modules with provenance"
```

---

### Task 5: Add `source` CLI commands for Confluence registration and pulls

**Files:**
- Modify: `knowledge-manager/src/knowledge_manager/cli.py`
- Modify: `knowledge-manager/tests/test_cli.py`

- [ ] **Step 1: Write the failing CLI tests**

```python
# Append to knowledge-manager/tests/test_cli.py

from unittest.mock import AsyncMock, patch

from knowledge_manager.schemas import ConfluenceSourceConfig, SourceDefinition
from knowledge_manager.source_ingestion import IngestionSummary, load_source_registry, upsert_source


def test_cli_source_add_confluence(cli_runner, initialized_kb):
    result = cli_runner.invoke(
        cli,
        [
            "--kb-path", str(initialized_kb),
            "source", "add-confluence", "team-wiki",
            "--base-url", "https://wiki.example",
            "--space-key", "ENG",
            "--email", "bot@example.com",
            "--api-token-env", "CONFLUENCE_TOKEN",
            "--category", "architecture",
        ],
    )

    registry = load_source_registry(initialized_kb)
    assert result.exit_code == 0
    assert "team-wiki" in registry.sources
    assert registry.sources["team-wiki"].confluence.space_key == "ENG"


def test_cli_source_pull_runs_ingestion(cli_runner, initialized_kb, monkeypatch):
    upsert_source(
        SourceDefinition(
            id="team-wiki",
            confluence=ConfluenceSourceConfig(
                base_url="https://wiki.example",
                space_key="ENG",
                email="bot@example.com",
                api_token_env="CONFLUENCE_TOKEN",
                category="architecture",
            ),
        ),
        initialized_kb,
    )
    monkeypatch.setenv("CONFLUENCE_TOKEN", "secret")

    with patch("knowledge_manager.cli.create_client") as mock_create_client, \
         patch("knowledge_manager.confluence.ConfluenceClient") as mock_confluence_client, \
         patch("knowledge_manager.source_ingestion.ingest_source", new=AsyncMock(return_value=IngestionSummary(source_id="team-wiki", pages_fetched=2, modules_staged=3, stale_marked=1))):
        mock_create_client.return_value = AsyncMock()
        result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "source", "pull", "team-wiki"])

    assert result.exit_code == 0
    assert "Fetched 2 pages" in result.output
    assert "staged 3 modules" in result.output.lower()


def test_cli_source_status(cli_runner, initialized_kb):
    upsert_source(
        SourceDefinition(
            id="team-wiki",
            confluence=ConfluenceSourceConfig(
                base_url="https://wiki.example",
                space_key="ENG",
                email="bot@example.com",
                api_token_env="CONFLUENCE_TOKEN",
                category="architecture",
            ),
        ),
        initialized_kb,
    )

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "source", "status"])
    assert result.exit_code == 0
    assert "team-wiki" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest knowledge-manager/tests/test_cli.py::test_cli_source_add_confluence knowledge-manager/tests/test_cli.py::test_cli_source_pull_runs_ingestion knowledge-manager/tests/test_cli.py::test_cli_source_status -v`
Expected: FAIL because the `source` command group and its imports do not exist.

- [ ] **Step 3: Add the CLI group and commands**

```python
# Add to knowledge-manager/src/knowledge_manager/cli.py near other command groups

@cli.group()
def source() -> None:
    """Manage external enterprise knowledge sources."""


@source.command("add-confluence")
@click.argument("source_id")
@click.option("--base-url", required=True)
@click.option("--space-key", required=True)
@click.option("--email", required=True)
@click.option("--api-token-env", required=True)
@click.option("--category", default="general")
@click.pass_context
def source_add_confluence(ctx: click.Context, source_id: str, base_url: str, space_key: str, email: str, api_token_env: str, category: str) -> None:
    from knowledge_manager.schemas import ConfluenceSourceConfig, SourceDefinition
    from knowledge_manager.source_ingestion import upsert_source

    kb = ctx.obj["kb_path"]
    _require_kb(kb)
    upsert_source(
        SourceDefinition(
            id=source_id,
            confluence=ConfluenceSourceConfig(
                base_url=base_url,
                space_key=space_key,
                email=email,
                api_token_env=api_token_env,
                category=category,
            ),
        ),
        kb,
    )
    click.echo(f"Added confluence source {source_id}")


@source.command("pull")
@click.argument("source_id")
@click.pass_context
def source_pull(ctx: click.Context, source_id: str) -> None:
    from knowledge_manager.confluence import ConfluenceClient
    from knowledge_manager.source_ingestion import ingest_source, load_source_registry

    kb = ctx.obj["kb_path"]
    _require_kb(kb)

    registry = load_source_registry(kb)
    if source_id not in registry.sources:
        click.echo(f"Error: unknown source {source_id}", err=True)
        raise click.Abort()

    source_def = registry.sources[source_id]
    token = os.getenv(source_def.confluence.api_token_env, "")
    if not token:
        click.echo(f"Error: env var {source_def.confluence.api_token_env} is not set", err=True)
        raise click.Abort()

    cfg = _load_config(kb)
    provider_name, provider_cfg = cfg.get_default_provider()
    llm_client = create_client(provider_name, provider_cfg)
    extractor = Extractor(llm_client, cfg.extraction)
    connector = ConfluenceClient(source_def.confluence.base_url, source_def.confluence.email, token)
    summary = asyncio.run(ingest_source(source_id, kb, connector, extractor))
    click.echo(
        f"Fetched {summary.pages_fetched} pages; staged {summary.modules_staged} modules; marked {summary.stale_marked} stale"
    )


@source.command("status")
@click.pass_context
def source_status(ctx: click.Context) -> None:
    from knowledge_manager.source_ingestion import load_source_registry

    kb = ctx.obj["kb_path"]
    _require_kb(kb)
    registry = load_source_registry(kb)
    if not registry.sources:
        click.echo("No sources configured.")
        return
    for source_id, source_def in registry.sources.items():
        synced = source_def.sync.last_synced_at.isoformat() if source_def.sync.last_synced_at else "never"
        click.echo(f"{source_id}\t{source_def.type}\t{source_def.confluence.space_key}\t{synced}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest knowledge-manager/tests/test_cli.py::test_cli_source_add_confluence knowledge-manager/tests/test_cli.py::test_cli_source_pull_runs_ingestion knowledge-manager/tests/test_cli.py::test_cli_source_status -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add knowledge-manager/src/knowledge_manager/cli.py knowledge-manager/tests/test_cli.py
git commit -m "feat: add source CLI for confluence ingestion"
```

---

### Task 6: Add a narrow task-level eval runner and CLI

**Files:**
- Create: `knowledge-manager/src/knowledge_manager/eval_runner.py`
- Modify: `knowledge-manager/src/knowledge_manager/cli.py`
- Create: `knowledge-manager/tests/test_eval_runner.py`

- [ ] **Step 1: Write the failing tests**

```python
# Create knowledge-manager/tests/test_eval_runner.py

import json
from click.testing import CliRunner

from knowledge_manager.cli import cli
from knowledge_manager.eval_runner import run_eval_suite
from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata
from knowledge_manager.storage import rebuild_index, save_module


def test_run_eval_suite_scores_required_modules(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()

    save_module(
        Module(
            id="jwt-runbook",
            category="auth",
            title="JWT Runbook",
            summary="How we run JWT auth in production.",
            content=ModuleContent(
                overview="JWT auth in production uses short-lived access tokens.",
                details="Refresh tokens rotate on each successful refresh and revocation is checked centrally.",
            ),
            metadata=ModuleMetadata(tags=["jwt", "auth"]),
        ),
        kb,
    )
    rebuild_index(kb)

    cases_path = tmp_path / "eval-cases.json"
    cases_path.write_text(json.dumps({
        "cases": [
            {
                "id": "jwt-hit",
                "query": "jwt auth production",
                "required_modules": ["auth/jwt-runbook"],
                "top_k": 3,
            }
        ]
    }))

    summary = run_eval_suite(cases_path, kb)

    assert summary.total_cases == 1
    assert summary.passed_cases == 1
    assert summary.hit_rate == 100.0


def test_cli_eval_run_outputs_summary(tmp_path):
    runner = CliRunner()
    kb = tmp_path / "kb"
    runner.invoke(cli, ["init", str(kb)])

    save_module(
        Module(
            id="jwt-runbook",
            category="auth",
            title="JWT Runbook",
            summary="How we run JWT auth in production.",
            content=ModuleContent(
                overview="JWT auth in production uses short-lived access tokens.",
                details="Refresh tokens rotate on each successful refresh and revocation is checked centrally.",
            ),
            metadata=ModuleMetadata(tags=["jwt", "auth"]),
        ),
        kb,
    )
    rebuild_index(kb)

    cases_path = tmp_path / "eval-cases.json"
    cases_path.write_text(json.dumps({
        "cases": [
            {
                "id": "jwt-hit",
                "query": "jwt auth production",
                "required_modules": ["auth/jwt-runbook"],
                "top_k": 3,
            }
        ]
    }))

    result = runner.invoke(cli, ["--kb-path", str(kb), "eval", "run", str(cases_path)])
    assert result.exit_code == 0
    assert "Hit rate: 100.0%" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest knowledge-manager/tests/test_eval_runner.py -v`
Expected: FAIL because `eval_runner.py` and the `eval` command group do not exist.

- [ ] **Step 3: Implement the eval models, runner, and CLI command**

```python
# Create knowledge-manager/src/knowledge_manager/eval_runner.py

import json
from pathlib import Path

from pydantic import BaseModel, Field

from knowledge_manager.storage import search_modules


class EvalCase(BaseModel):
    id: str
    query: str
    required_modules: list[str] = Field(default_factory=list)
    category: str = ""
    top_k: int = 5


class EvalCaseResult(BaseModel):
    id: str
    returned_modules: list[str] = Field(default_factory=list)
    missing_modules: list[str] = Field(default_factory=list)
    passed: bool = False


class EvalSummary(BaseModel):
    total_cases: int = 0
    passed_cases: int = 0
    hit_rate: float = 0.0
    results: list[EvalCaseResult] = Field(default_factory=list)


def run_eval_suite(cases_path: Path, kb_path: Path) -> EvalSummary:
    payload = json.loads(cases_path.read_text(encoding="utf-8"))
    cases = [EvalCase.model_validate(item) for item in payload.get("cases", [])]

    results: list[EvalCaseResult] = []
    passed = 0
    for case in cases:
        found = search_modules(case.query, kb_path, category=case.category or None, limit=case.top_k)
        module_keys = [f"{item.module.category}/{item.module.id}" for item in found]
        missing = [key for key in case.required_modules if key not in module_keys]
        case_result = EvalCaseResult(
            id=case.id,
            returned_modules=module_keys,
            missing_modules=missing,
            passed=len(missing) == 0,
        )
        if case_result.passed:
            passed += 1
        results.append(case_result)

    total = len(cases)
    hit_rate = round((passed / total) * 100, 1) if total else 0.0
    return EvalSummary(total_cases=total, passed_cases=passed, hit_rate=hit_rate, results=results)
```

```python
# Add to knowledge-manager/src/knowledge_manager/cli.py

@cli.group()
def eval() -> None:
    """Run retrieval benchmarks for a knowledge base."""


@eval.command("run")
@click.argument("cases_path", type=click.Path(path_type=Path))
@click.pass_context
def eval_run(ctx: click.Context, cases_path: Path) -> None:
    from knowledge_manager.eval_runner import run_eval_suite

    kb = ctx.obj["kb_path"]
    _require_kb(kb)
    summary = run_eval_suite(cases_path, kb)
    click.echo(f"Cases: {summary.total_cases}")
    click.echo(f"Passed: {summary.passed_cases}")
    click.echo(f"Hit rate: {summary.hit_rate}%")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest knowledge-manager/tests/test_eval_runner.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add knowledge-manager/src/knowledge_manager/eval_runner.py knowledge-manager/src/knowledge_manager/cli.py knowledge-manager/tests/test_eval_runner.py
git commit -m "feat: add task-level retrieval eval runner"
```

---

### Task 7: Run the focused V1 verification sweep

**Files:**
- Modify: none
- Test: `knowledge-manager/tests/test_schemas.py`, `knowledge-manager/tests/test_source_ingestion.py`, `knowledge-manager/tests/test_confluence.py`, `knowledge-manager/tests/test_cli.py`, `knowledge-manager/tests/test_eval_runner.py`

- [ ] **Step 1: Run the focused test suite**

Run:

```bash
pytest knowledge-manager/tests/test_schemas.py knowledge-manager/tests/test_source_ingestion.py knowledge-manager/tests/test_confluence.py knowledge-manager/tests/test_cli.py knowledge-manager/tests/test_eval_runner.py -v
```

Expected: PASS for the new provenance, source-ingestion, connector, CLI, and eval coverage.

- [ ] **Step 2: Run one CLI smoke flow end-to-end**

Run:

```bash
python -m knowledge_manager.cli --kb-path knowledge-manager/examples/sample_knowledge_base source status
```

Expected: exits 0 and prints either configured sources or `No sources configured.`

- [ ] **Step 3: Review the runtime artifacts produced by a temp-kb test run**

Check that the following files are created during tests:

```text
<tmp-kb>/.sources/registry.json
<tmp-kb>/.staging/<module>.json
<tmp-kb>/.staging/<module>.meta.json
```

Expected: registry file contains no raw secret token; only env-var names are persisted.

- [ ] **Step 4: Commit the final verification pass**

```bash
git add knowledge-manager/src/knowledge_manager/schemas.py knowledge-manager/src/knowledge_manager/source_ingestion.py knowledge-manager/src/knowledge_manager/confluence.py knowledge-manager/src/knowledge_manager/eval_runner.py knowledge-manager/src/knowledge_manager/cli.py knowledge-manager/tests/test_schemas.py knowledge-manager/tests/test_source_ingestion.py knowledge-manager/tests/test_confluence.py knowledge-manager/tests/test_eval_runner.py knowledge-manager/tests/test_cli.py
git commit -m "feat: ship v1 enterprise ingestion slice"
```

---

## Self-review checklist

### Spec coverage

- **Flagship enterprise connector** → Task 3 + Task 5 (`ConfluenceClient`, `source add-confluence`, `source pull`)
- **Bulk import / sync-state persistence** → Task 2 + Task 4 (`SourceRegistry`, `SourceSyncState`, `ingest_source`)
- **Source → module provenance mapping** → Task 1 + Task 4 (`source_documents`, `source_spans`, `extraction_run_id`)
- **Source-change invalidation** → Task 4 (`mark_modules_stale_for_document`)
- **Basic task-level benchmark** → Task 6 (`run_eval_suite`, `eval run`)

### Deliberate non-goals for this plan

These remain out of scope for this V1 plan and should not be slipped in during implementation:

- route-policy enforcement
- operations console
- lifecycle SLA UI
- signed OIDC validation
- hybrid vector fallback routing

### Placeholder scan

This plan intentionally avoids `TODO`, `TBD`, and "implement later" placeholders. Every code-changing step includes concrete code to add or replace.
