# Production-Grade Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `knowledge-manager` from "production-shaped but not yet release-gated" to an evidence-backed single-node production-grade deployment by eliminating the current benchmark gate failures and codifying the final release path.

**Architecture:** Keep the current file-backed, git-native design. Do not add a database, Redis, or distributed queue. Instead, make the slow control-plane and retrieval paths read from precomputed JSON snapshots or projection indexes, keep tenant slicing cheap, and make the release verdict reject stale or incomplete evidence before `production_mode=true` cutover.

**Tech Stack:** Python 3.10+, FastAPI, FastMCP, Click, pytest, JSON/JSONL storage, materialized views, `search_projection`, `recommendation_index`, `performance_benchmarks`, `verify_production_readiness.py`.

---

## Why This Plan Exists

The current repository already contains most of the production-hardening work from the remediation plan:

- fail-closed auth and HTTP/MCP authorization scaffolding
- tenant-aware HTTP and MCP surfaces
- durable ingestion worker loop
- readiness, integrity, and release-verdict plumbing
- audit logging and rollout runbooks

But the current release evidence still fails the production gate:

- `xs` fails `admin_dashboard_http`
- `s` fails `search_http`, `recommendations_http`, `admin_dashboard_http`, `module_crud_http`, and `mcp_search_modules`
- `m` fails `search_http`, `recommendations_http`, `admin_dashboard_http`, and `mcp_search_modules`

That means the remaining work is no longer broad security remediation. It is now a focused "close the gate" plan:

1. make `admin_dashboard` stop rebuilding expensive aggregates on hot reads
2. make `recommendations` read from an index-shaped payload instead of rescanning modules
3. make `search_http` and `mcp_search_modules` stay on the projection path with much smaller candidate sets and cheaper serialization
4. make release evidence itself trustworthy and reproducible
5. ship explicit deployment artifacts for startup, restart, TLS termination, and worker supervision

## File Structure

### Existing files to extend

- `D:\tyh\knowledge-manager\src\knowledge_manager\admin_views.py`
  Responsibility: admin dashboard aggregation and tenant slicing.
- `D:\tyh\knowledge-manager\src\knowledge_manager\materialized_views.py`
  Responsibility: revision-based snapshot invalidation and persistence.
- `D:\tyh\knowledge-manager\src\knowledge_manager\recommendation_index.py`
  Responsibility: precomputed recommendation-friendly metadata.
- `D:\tyh\knowledge-manager\src\knowledge_manager\search_projection.py`
  Responsibility: precomputed search documents and inverted index.
- `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
  Responsibility: retrieval, recommendations, ops report generation, persistence.
- `D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py`
  Responsibility: MCP search/load/list tools and resource shaping.
- `D:\tyh\knowledge-manager\src\knowledge_manager\performance_benchmarks.py`
  Responsibility: benchmark execution, gate summaries, release verdicts.
- `D:\tyh\knowledge-manager\scripts\verify_production_readiness.py`
  Responsibility: one-command release verification.
- `D:\tyh\knowledge-manager\src\knowledge_manager\cli.py`
  Responsibility: operator-facing production gate command.
- `D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md`
- `D:\tyh\knowledge-manager\docs\runbooks\enterprise-performance-test-plan.md`
- `D:\tyh\knowledge-manager\tests\test_http_server.py`
- `D:\tyh\knowledge-manager\tests\test_mcp_server.py`
- `D:\tyh\knowledge-manager\tests\test_storage.py`
- `D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py`
- `D:\tyh\knowledge-manager\tests\test_recommendation_index.py`
- `D:\tyh\knowledge-manager\tests\test_search_projection.py`

### New files to create

- `D:\tyh\knowledge-manager\src\knowledge_manager\admin_snapshot.py`
  Responsibility: build and slice an index-backed admin dashboard snapshot.
- `D:\tyh\knowledge-manager\tests\test_admin_views.py`
  Responsibility: snapshot reuse and tenant-slice correctness for admin dashboard reads.
- `D:\tyh\knowledge-manager\deploy\systemd\knowledge-manager-api.service`
  Responsibility: API startup and restart policy under a real service manager.
- `D:\tyh\knowledge-manager\deploy\systemd\knowledge-manager-worker.service`
  Responsibility: durable worker supervision for upload/source-sync production deployments.

## Delivery Stages

1. `P0` Eliminate release-gate hot paths (`admin_dashboard_http`, `recommendations_http`, `search_http`, `mcp_search_modules`)
2. `P0` Make the release verdict reject stale evidence and publish a deterministic verification flow
3. `P1` Ship deployment artifacts and final cutover documentation

### Task 1: Snapshot The Admin Dashboard Hot Path

**Files:**
- Create: `D:\tyh\knowledge-manager\src\knowledge_manager\admin_snapshot.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\admin_views.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\materialized_views.py`
- Test: `D:\tyh\knowledge-manager\tests\test_admin_views.py`
- Test: `D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py`

- [ ] **Step 1: Write the failing snapshot-reuse tests**

```python
from knowledge_manager.admin_snapshot import build_admin_dashboard_snapshot
from knowledge_manager.schemas import Index
from knowledge_manager.storage import save_index


def test_admin_dashboard_global_reads_reuse_cached_snapshot(tmp_path, monkeypatch):
    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="admin snapshot"), kb)

    calls = {"count": 0}

    def count_build(*args, **kwargs):
        calls["count"] += 1
        return build_admin_dashboard_snapshot(*args, **kwargs)

    monkeypatch.setattr("knowledge_manager.admin_views.build_admin_dashboard_snapshot", count_build)

    from knowledge_manager.admin_views import build_admin_dashboard

    first = build_admin_dashboard(kb)
    second = build_admin_dashboard(kb)

    assert first == second
    assert calls["count"] == 1


def test_admin_dashboard_tenant_read_slices_cached_snapshot_without_rebuilding(tmp_path, monkeypatch):
    from knowledge_manager.admin_views import build_admin_dashboard
    from knowledge_manager.tenancy import TenantContext

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="tenant admin snapshot"), kb)

    snapshot = build_admin_dashboard(kb)
    assert snapshot["review_backlog"] is not None

    def explode(*_args, **_kwargs):
        raise AssertionError("tenant dashboard read must slice the cached snapshot instead of rebuilding it")

    monkeypatch.setattr("knowledge_manager.admin_views.build_admin_dashboard_snapshot", explode)

    payload = build_admin_dashboard(kb, tenant=TenantContext(tenant_id="tenant-001"))
    assert "ingestion_jobs" in payload
    assert "review_backlog" in payload
```

- [ ] **Step 2: Run the focused admin snapshot tests and verify they fail**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; $env:PYTEST_DEBUG_TEMPROOT='D:\tyh\knowledge-manager\tmp\pytest'; python -m pytest D:\tyh\knowledge-manager\tests\test_admin_views.py -q`

Expected: `FAIL` because `build_admin_dashboard()` still does work inline and tenant reads still depend on the expensive rebuild path.

- [ ] **Step 3: Add an explicit admin snapshot builder and tenant slicer**

```python
# D:\tyh\knowledge-manager\src\knowledge_manager\admin_snapshot.py
from __future__ import annotations

from pathlib import Path
from typing import Any

from knowledge_manager.ingestion_jobs import list_ingestion_jobs
from knowledge_manager.ops_export import generate_review_backlog_export, generate_source_backlog_export
from knowledge_manager.source_ingestion import load_source_registry
from knowledge_manager.storage import generate_ops_report, list_staging, list_staging_meta
from knowledge_manager.tenancy import TenantContext, module_visible_to_tenant


def build_admin_dashboard_snapshot(kb_path: Path) -> dict[str, Any]:
    jobs = [job.model_dump(mode="json") for job in list_ingestion_jobs(kb_path)]
    staging_meta = list_staging_meta(kb_path / ".staging")
    ops_report = generate_ops_report(kb_path, staging_meta=staging_meta)
    registry = load_source_registry(kb_path)

    return {
        "ingestion_jobs": jobs,
        "review_backlog": generate_review_backlog_export(
            kb_path,
            report=ops_report,
            staging_meta=staging_meta,
        ).get("items", []),
        "stale_sources": generate_source_backlog_export(
            kb_path,
            report=ops_report,
        ).get("items", []),
        "source_tenants": {
            source_id: source.tenant_id
            for source_id, source in registry.sources.items()
        },
        "staging_tenants": {
            module.id: module.metadata.tenant_id
            for module in list_staging(kb_path / ".staging")
        },
        "eval_regressions": [],
    }


def slice_admin_dashboard_snapshot(snapshot: dict[str, Any], tenant: TenantContext | None) -> dict[str, Any]:
    if tenant is None:
        return snapshot
    return {
        "ingestion_jobs": [
            job for job in snapshot["ingestion_jobs"]
            if (not job.get("tenant_id") and tenant.allow_global_reads) or job.get("tenant_id") == tenant.tenant_id
        ],
        "review_backlog": [
            item for item in snapshot["review_backlog"]
            if snapshot["staging_tenants"].get(item.get("module_id", ""), "") in ("", tenant.tenant_id)
        ],
        "stale_sources": [
            item for item in snapshot["stale_sources"]
            if snapshot["source_tenants"].get(item.get("source_id", ""), "") in ("", tenant.tenant_id)
        ],
        "eval_regressions": snapshot["eval_regressions"],
    }
```

```python
# D:\tyh\knowledge-manager\src\knowledge_manager\admin_views.py
from knowledge_manager.admin_snapshot import build_admin_dashboard_snapshot, slice_admin_dashboard_snapshot
from knowledge_manager.materialized_views import load_fresh_materialized_view, store_materialized_view


def build_admin_dashboard(kb_path: Path, tenant: TenantContext | None = None) -> dict[str, Any]:
    cached = load_fresh_materialized_view(kb_path, "admin_dashboard")
    if cached is None:
        cached = build_admin_dashboard_snapshot(kb_path)
        store_materialized_view(kb_path, "admin_dashboard", cached)
    return slice_admin_dashboard_snapshot(cached, tenant)
```

- [ ] **Step 4: Re-run snapshot tests plus the admin benchmark contract**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; $env:PYTEST_DEBUG_TEMPROOT='D:\tyh\knowledge-manager\tmp\pytest'; python -m pytest D:\tyh\knowledge-manager\tests\test_admin_views.py D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py -k "admin_dashboard" -q`

Expected: `PASS`; the cached snapshot is reused and the benchmark warm-up can prime the dashboard path deterministically.

- [ ] **Step 5: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\admin_snapshot.py D:\tyh\knowledge-manager\src\knowledge_manager\admin_views.py D:\tyh\knowledge-manager\tests\test_admin_views.py D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py
git commit -m "perf: snapshot admin dashboard hot path"
```

### Task 2: Move Recommendations To Index-Backed Reads

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\recommendation_index.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\tenant_views.py`
- Test: `D:\tyh\knowledge-manager\tests\test_recommendation_index.py`
- Test: `D:\tyh\knowledge-manager\tests\test_storage.py`

- [ ] **Step 1: Write the failing recommendation-index tests**

```python
from knowledge_manager.recommendation_index import build_recommendation_index
from knowledge_manager.schemas import Index, Module, ModuleContent
from knowledge_manager.storage import generate_recommendations, save_index, save_module


def test_recommendation_index_persists_precomputed_report_inputs(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="recommendation index"), kb)
    save_module(
        Module(
            id="ops-review",
            category="ops",
            title="Ops Review",
            summary="Ops review summary.",
            content=ModuleContent(overview="overview", details="details long enough for validation."),
        ),
        kb,
        defer_noncritical=False,
    )

    payload = build_recommendation_index(kb)

    assert "recommendation_inputs" in payload
    assert "ops/ops-review" in payload["recommendation_inputs"]


def test_generate_recommendations_uses_precomputed_inputs_without_full_module_scan(tmp_path, monkeypatch):
    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="recommendation report"), kb)

    payload = {
        "modules": {},
        "module_tags": {},
        "tag_index": {},
        "outbound_links": {},
        "link_candidates": [],
        "recommendation_inputs": {},
    }

    monkeypatch.setattr("knowledge_manager.storage.load_recommendation_index", lambda _kb: payload)
    monkeypatch.setattr("knowledge_manager.storage.list_modules", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("recommendations should not rescan all modules when the index is present")))

    report = generate_recommendations(kb)
    assert report.model_dump()["archive_candidates"] == []
```

- [ ] **Step 2: Run the focused recommendation tests and verify they fail**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; $env:PYTEST_DEBUG_TEMPROOT='D:\tyh\knowledge-manager\tmp\pytest'; python -m pytest D:\tyh\knowledge-manager\tests\test_recommendation_index.py D:\tyh\knowledge-manager\tests\test_storage.py -k "recommendation_index or generate_recommendations_uses_precomputed_inputs" -q`

Expected: `FAIL` because the current recommendation index only stores tags and links, while `generate_recommendations()` still rebuilds report inputs from full module scans.

- [ ] **Step 3: Extend the recommendation index with report-ready inputs**

```python
# D:\tyh\knowledge-manager\src\knowledge_manager\recommendation_index.py
def _recommendation_input(module) -> dict[str, Any]:
    return {
        "category": module.category,
        "module_id": module.id,
        "title": module.title,
        "status": module.metadata.status,
        "tenant_id": module.metadata.tenant_id,
        "workspace_id": module.metadata.workspace_id,
        "tags": sorted(set(module.metadata.tags)),
        "related_modules": sorted(set(module.metadata.related_modules)),
        "stale_due_to_source_change": module.metadata.stale_due_to_source_change,
        "review_interval_days": module.metadata.review_interval_days,
        "expires_at": module.metadata.expires_at.isoformat() if module.metadata.expires_at else None,
        "updated_at": module.updated_at.isoformat(),
        "content_lengths": {
            "overview": len(module.content.overview.strip()),
            "details": len(module.content.details.strip()),
            "examples": len(module.content.examples.strip()),
        },
    }


def _empty_payload() -> dict[str, Any]:
    return {
        "modules": {},
        "module_tags": {},
        "tag_index": {},
        "outbound_links": {},
        "link_candidates": [],
        "recommendation_inputs": {},
    }


def _apply_module(payload: dict[str, Any], module) -> None:
    key = _module_key(module.category, module.id)
    _remove_module(payload, module.category, module.id)
    payload["modules"][key] = {"module": module.model_dump(mode="json")}
    payload["recommendation_inputs"][key] = _recommendation_input(module)
```

```python
# D:\tyh\knowledge-manager\src\knowledge_manager\storage.py
def _generate_recommendations_from_index_payload(payload: dict[str, Any]) -> RecommendationReport:
    archive_candidates: list[Recommendation] = []
    enrichment_needed: list[Recommendation] = []
    suggested_links: list[Recommendation] = []
    review_reminders: list[Recommendation] = []

    for key, item in payload.get("recommendation_inputs", {}).items():
        if item["content_lengths"]["details"] < 80:
            enrichment_needed.append(
                Recommendation(
                    type=RecommendationType.ENRICHMENT,
                    module_id=item["module_id"],
                    category=item["category"],
                    title=item["title"],
                    score=0.9,
                    reason="details field is still too short for production retrieval quality",
                    detail={"module_key": key},
                )
            )

    for first, second, shared_tags in payload.get("link_candidates", []):
        if len(shared_tags) >= 2:
            suggested_links.append(
                Recommendation(
                    type=RecommendationType.LINK,
                    module_id=first,
                    category="",
                    title=f"{first} ↔ {second}",
                    score=min(1.0, len(shared_tags) / 5.0),
                    reason=f"Shared tags: {', '.join(shared_tags[:3])}",
                    detail={"module_a": first, "module_b": second, "shared_tags": shared_tags},
                )
            )

    return RecommendationReport(
        archive_candidates=archive_candidates[:10],
        enrichment_needed=sorted(enrichment_needed, key=lambda item: -item.score)[:10],
        suggested_links=sorted(suggested_links, key=lambda item: -item.score)[:10],
        review_reminders=review_reminders[:5],
    )


def generate_recommendations(kb_path: Path) -> Any:
    from knowledge_manager.schemas import RecommendationReport
    cached = load_fresh_materialized_view(kb_path, "recommendations")
    if cached is not None:
        return RecommendationReport.model_validate(cached)
    recommendation_payload = load_recommendation_index(kb_path)
    report = (
        _generate_recommendations_from_index_payload(recommendation_payload)
        if recommendation_payload and recommendation_payload.get("recommendation_inputs")
        else _generate_recommendations_uncached(kb_path)
    )
    return store_materialized_view(kb_path, "recommendations", report)
```

- [ ] **Step 4: Re-run recommendation tests and the control-plane benchmark contract**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; $env:PYTEST_DEBUG_TEMPROOT='D:\tyh\knowledge-manager\tmp\pytest'; python -m pytest D:\tyh\knowledge-manager\tests\test_recommendation_index.py D:\tyh\knowledge-manager\tests\test_storage.py D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py -k "recommendation or recommendations_http" -q`

Expected: `PASS`; the recommendation path no longer depends on rescanning every module when the recommendation index is fresh.

- [ ] **Step 5: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\recommendation_index.py D:\tyh\knowledge-manager\src\knowledge_manager\storage.py D:\tyh\knowledge-manager\tests\test_recommendation_index.py D:\tyh\knowledge-manager\tests\test_storage.py D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py
git commit -m "perf: serve recommendations from recommendation index"
```

### Task 3: Shrink Projection Candidates For HTTP And MCP Search

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\search_projection.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py`
- Test: `D:\tyh\knowledge-manager\tests\test_search_projection.py`
- Test: `D:\tyh\knowledge-manager\tests\test_storage.py`
- Test: `D:\tyh\knowledge-manager\tests\test_mcp_server.py`

- [ ] **Step 1: Write the failing projection-path tests**

```python
from knowledge_manager.search_projection import build_search_projection, query_search_projection
from knowledge_manager.schemas import Index, Module, ModuleContent
from knowledge_manager.storage import save_index, save_module


def test_query_search_projection_applies_candidate_limit(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="projection limit"), kb)
    for idx in range(40):
        save_module(
            Module(
                id=f"ops-{idx:02d}",
                category="ops",
                title=f"Rollback Incident {idx}",
                summary="tenant rollback incident summary",
                content=ModuleContent(overview="rollback tenant incident", details="rollback tenant incident details long enough for validation"),
            ),
            kb,
            defer_noncritical=False,
        )

    build_search_projection(kb)
    keys = query_search_projection(kb, "rollback tenant incident", limit=12)

    assert len(keys) == 12


def test_search_modules_projection_path_never_scores_more_than_candidate_cap(tmp_path, monkeypatch):
    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="candidate cap"), kb)
    build_search_projection(kb)

    scored = {"count": 0}

    def count_bm25(query, documents):
        scored["count"] = len(documents)
        return {}

    monkeypatch.setattr("knowledge_manager.storage._bm25_scores_for_documents", count_bm25)

    from knowledge_manager.storage import search_modules
    search_modules("rollback tenant incident", kb, limit=5)

    assert scored["count"] <= 64
```

- [ ] **Step 2: Run the focused search tests and verify they fail**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; $env:PYTEST_DEBUG_TEMPROOT='D:\tyh\knowledge-manager\tmp\pytest'; python -m pytest D:\tyh\knowledge-manager\tests\test_search_projection.py D:\tyh\knowledge-manager\tests\test_storage.py D:\tyh\knowledge-manager\tests\test_mcp_server.py -k "candidate_limit or candidate_cap or mcp_search_modules" -q`

Expected: `FAIL` because `query_search_projection()` does not cap early and the HTTP/MCP search path still scores too many documents for larger scales.

- [ ] **Step 3: Cap projection candidates before BM25 and keep MCP serialization compact**

```python
# D:\tyh\knowledge-manager\src\knowledge_manager\search_projection.py
def query_search_projection(kb_path: Path, query: str, limit: int | None = None) -> list[str]:
    from knowledge_manager.storage import _WORD_RE, _stem

    payload = load_search_projection_readonly(kb_path)
    if payload is None:
        payload = build_search_projection(kb_path)

    scores: dict[str, int] = {}
    for word in _WORD_RE.findall(query.lower()):
        for stem in _stem(word).split():
            for key in payload["inverted"].get(stem, []):
                scores[key] = scores.get(key, 0) + 1
    ranked = [key for key, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))]
    return ranked[:limit] if limit else ranked
```

```python
# D:\tyh\knowledge-manager\src\knowledge_manager\storage.py
if raw_query_terms and all(len(term) >= 5 or _CJK_RE.search(term) for term in raw_query_terms):
    try:
        from knowledge_manager.search_projection import (
            build_search_projection,
            load_search_projection_readonly,
            projection_document_complete,
            query_search_projection,
        )

        candidate_cap = max(limit * 8, 64)
        candidate_keys = query_search_projection(kb_path, query, limit=candidate_cap)
        if candidate_keys:
            candidate_set = set(candidate_keys)
            projection_payload = load_search_projection_readonly(kb_path)
            if projection_payload is None:
                projection_payload = build_search_projection(kb_path)
            projection_documents = projection_payload.get("documents", {})
            if any(
                (document := projection_documents.get(key)) is None or not projection_document_complete(document)
                for key in candidate_set
            ):
                projection_payload = build_search_projection(kb_path)
                projection_documents = projection_payload.get("documents", {})
            use_projection = bool(projection_documents)
    except Exception:
        candidate_set = None
        projection_documents = {}
```

```python
# D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py
@mcp.tool(name="search_modules")
def search_modules_tool(...):
    ...
    return json.dumps(results, separators=(",", ":"))
```

- [ ] **Step 4: Re-run projection, storage, MCP, and benchmark tests**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; $env:PYTEST_DEBUG_TEMPROOT='D:\tyh\knowledge-manager\tmp\pytest'; python -m pytest D:\tyh\knowledge-manager\tests\test_search_projection.py D:\tyh\knowledge-manager\tests\test_storage.py D:\tyh\knowledge-manager\tests\test_mcp_server.py D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py -k "projection or search_http or mcp_search_modules" -q`

Expected: `PASS`; the search path now scores a much smaller bounded candidate set and the MCP JSON path stays compact.

- [ ] **Step 5: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\search_projection.py D:\tyh\knowledge-manager\src\knowledge_manager\storage.py D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py D:\tyh\knowledge-manager\tests\test_search_projection.py D:\tyh\knowledge-manager\tests\test_storage.py D:\tyh\knowledge-manager\tests\test_mcp_server.py D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py
git commit -m "perf: cap projection candidates for search and mcp"
```

### Task 4: Reject Stale Release Evidence And Publish Deterministic Gate Commands

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\performance_benchmarks.py`
- Modify: `D:\tyh\knowledge-manager\scripts\verify_production_readiness.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\cli.py`
- Modify: `D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md`
- Modify: `D:\tyh\knowledge-manager\docs\runbooks\enterprise-performance-test-plan.md`
- Test: `D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py`
- Test: `D:\tyh\knowledge-manager\tests\test_cli.py`

- [ ] **Step 1: Write the failing stale-evidence tests**

```python
import json
from datetime import datetime, timedelta, timezone

from knowledge_manager.performance_benchmarks import build_production_readiness_verdict


def test_build_production_readiness_verdict_rejects_stale_matrix_summary(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    summary = tmp_path / "matrix-summary.json"
    summary.write_text(
        json.dumps(
            {
                "generated_at": (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat(),
                "xs": {"release_verdict": {"ready_for_production": True}},
                "s": {"release_verdict": {"ready_for_production": True}},
                "m": {"release_verdict": {"ready_for_production": True}},
            }
        ),
        encoding="utf-8",
    )

    verdict = build_production_readiness_verdict(kb, summary, required_scales=["xs", "s", "m"], max_matrix_age_hours=24)

    assert verdict["ready_for_production"] is False
    assert "performance:matrix_summary_stale" in verdict["blockers"]
```

- [ ] **Step 2: Run the focused release-verdict tests and verify they fail**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; $env:PYTEST_DEBUG_TEMPROOT='D:\tyh\knowledge-manager\tmp\pytest'; python -m pytest D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py D:\tyh\knowledge-manager\tests\test_cli.py -k "stale_matrix_summary or verify_production_readiness" -q`

Expected: `FAIL` because the current release verdict checks scale status but not evidence freshness.

- [ ] **Step 3: Add matrix-age validation to the production verdict**

```python
# D:\tyh\knowledge-manager\src\knowledge_manager\performance_benchmarks.py
def build_production_readiness_verdict(
    kb_path: Path,
    matrix_summary_path: Path,
    required_scales: list[str] | None = None,
    max_matrix_age_hours: int = 24,
) -> dict[str, Any]:
    from datetime import datetime, timezone, timedelta
    from knowledge_manager.runtime_checks import evaluate_readiness, run_integrity_check
    from knowledge_manager.storage import _load_config_safe

    cfg = _load_config_safe(kb_path)
    resolved_scales = required_scales or (cfg.security.required_perf_scales if cfg else ["xs", "s", "m"])
    matrix_payload = json.loads(matrix_summary_path.read_text(encoding="utf-8"))
    matrix_verdict = evaluate_matrix_summary(matrix_summary_path, resolved_scales)
    readiness = evaluate_readiness(kb_path)
    integrity = run_integrity_check(kb_path)

    blockers: list[str] = []
    generated_at = matrix_payload.get("generated_at", "")
    if generated_at:
        generated = datetime.fromisoformat(generated_at)
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        if generated < datetime.now(timezone.utc) - timedelta(hours=max_matrix_age_hours):
            blockers.append("performance:matrix_summary_stale")

    if not matrix_verdict["ready_for_production"]:
        blockers.extend(f"performance:scale:{scale}" for scale in matrix_verdict["failed_scales"])
    if not readiness["ready"]:
        blockers.extend(f"readiness:{reason}" for reason in readiness["reasons"])
    if not integrity["ok"]:
        blockers.extend(f"integrity:{issue['kind']}" for issue in integrity["issues"])

    return {
        "ready_for_production": not blockers,
        "readiness": readiness,
        "integrity": integrity,
        "performance": matrix_verdict,
        "blockers": blockers,
    }
```

```python
# D:\tyh\knowledge-manager\scripts\verify_production_readiness.py
parser.add_argument("--max-matrix-age-hours", type=int, default=24)
...
verdict = build_production_readiness_verdict(
    Path(args.kb_path),
    Path(args.matrix_summary),
    max_matrix_age_hours=args.max_matrix_age_hours,
)
```

- [ ] **Step 4: Update runbooks to use deterministic pytest temp roots and fresh gate evidence**

```markdown
## Deterministic Local Gate Run

Use pytest's default `tmp_path` behavior unless you need an explicit root for a CI agent. If you must override the temp root, set `PYTEST_DEBUG_TEMPROOT` to a dedicated directory for that run instead of reusing a shared `--basetemp` path.

```powershell
$env:PYTHONPATH='D:\tyh\knowledge-manager\src'
$env:PYTEST_DEBUG_TEMPROOT='D:\tyh\knowledge-manager\tmp\pytest'
python -m pytest tests/test_performance_benchmarks.py tests/test_http_server.py tests/test_mcp_server.py -q
python scripts/verify_production_readiness.py --kb-path D:\tyh\knowledge-manager\kb --matrix-summary <fresh-matrix-summary.json> --max-matrix-age-hours 24
```
```

- [ ] **Step 5: Re-run release-verdict tests and verify the runbooks mention fresh evidence**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; $env:PYTEST_DEBUG_TEMPROOT='D:\tyh\knowledge-manager\tmp\pytest'; python -m pytest D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py D:\tyh\knowledge-manager\tests\test_cli.py -k "matrix_summary or verify_production_readiness" -q`

Run: `Select-String -Path D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md,D:\tyh\knowledge-manager\docs\runbooks\enterprise-performance-test-plan.md -Pattern "PYTEST_DEBUG_TEMPROOT","max-matrix-age-hours","fresh"`

Expected: `PASS`; stale summaries are now rejected and both runbooks describe one reproducible gate flow.

- [ ] **Step 6: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\performance_benchmarks.py D:\tyh\knowledge-manager\scripts\verify_production_readiness.py D:\tyh\knowledge-manager\src\knowledge_manager\cli.py D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md D:\tyh\knowledge-manager\docs\runbooks\enterprise-performance-test-plan.md D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py D:\tyh\knowledge-manager\tests\test_cli.py
git commit -m "ops: reject stale release evidence"
```

### Task 5: Ship Real Deployment Artifacts For API And Worker

**Files:**
- Create: `D:\tyh\knowledge-manager\deploy\systemd\knowledge-manager-api.service`
- Create: `D:\tyh\knowledge-manager\deploy\systemd\knowledge-manager-worker.service`
- Modify: `D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md`
- Modify: `D:\tyh\knowledge-manager\README.md`

- [ ] **Step 1: Write the deployment artifacts**

```ini
# D:\tyh\knowledge-manager\deploy\systemd\knowledge-manager-api.service
[Unit]
Description=knowledge-manager API
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/knowledge-manager
Environment=PYTHONPATH=/opt/knowledge-manager/src
ExecStart=/opt/knowledge-manager/.venv/bin/uvicorn knowledge_manager.http_server:create_app --factory --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5
User=km
Group=km

[Install]
WantedBy=multi-user.target
```

```ini
# D:\tyh\knowledge-manager\deploy\systemd\knowledge-manager-worker.service
[Unit]
Description=knowledge-manager worker
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/knowledge-manager
Environment=PYTHONPATH=/opt/knowledge-manager/src
ExecStart=/opt/knowledge-manager/.venv/bin/km --kb /opt/knowledge-manager/kb worker run --poll-interval 1.0
Restart=always
RestartSec=5
User=km
Group=km

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Document the exact cutover sequence**

```markdown
## Single-Node Production Cutover

1. Put TLS termination in front of Uvicorn using Caddy, Nginx, Traefik, or the cloud provider's TLS layer.
2. Enable the API unit and confirm automatic startup and restart:
   - `sudo systemctl enable --now knowledge-manager-api`
   - `sudo systemctl status knowledge-manager-api`
3. If uploads or source sync are enabled, enable the worker unit:
   - `sudo systemctl enable --now knowledge-manager-worker`
   - `sudo systemctl status knowledge-manager-worker`
4. Run a fresh benchmark matrix and `verify_production_readiness.py`.
5. Only then set `production_mode=true`.
```

- [ ] **Step 3: Verify the deployment artifacts are referenced from docs**

Run: `Select-String -Path D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md,D:\tyh\knowledge-manager\README.md -Pattern "knowledge-manager-api.service","knowledge-manager-worker.service","systemctl","TLS"`

Expected: both docs mention the concrete service files and the external TLS/component responsibilities.

- [ ] **Step 4: Commit**

```bash
git add D:\tyh\knowledge-manager\deploy\systemd\knowledge-manager-api.service D:\tyh\knowledge-manager\deploy\systemd\knowledge-manager-worker.service D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md D:\tyh\knowledge-manager\README.md
git commit -m "docs: add production deployment artifacts"
```

## Coverage Check

- `admin_dashboard_http` gate: Task 1
- `recommendations_http` gate: Task 2
- `search_http` and `mcp_search_modules` gates: Task 3
- stale or non-reproducible release evidence: Task 4
- startup/restart/TLS/worker deployment path: Task 5

## Self-Review

### Spec coverage

- Remaining benchmark failures are directly mapped to Tasks 1-3.
- Reproducible release gating is covered in Task 4.
- Operational deployment requirements for startup, restart, and worker supervision are covered in Task 5.

### Placeholder scan

- No `TODO`, `TBD`, or "similar to above" placeholders remain.
- Each task contains exact file paths, exact commands, and explicit test code or deployment file content.

### Type consistency

- Snapshot functions use the same `kb_path: Path` and `tenant: TenantContext | None` conventions already used in the codebase.
- Release verdict wiring keeps the existing `build_production_readiness_verdict()` entry point and extends it with `max_matrix_age_hours`.

## Notes For Execution

- Use `tmp_path` / `tmp_path_factory` semantics by default; when an explicit temp root is needed for CI or a locked-down workstation, prefer `PYTEST_DEBUG_TEMPROOT` over a shared `--basetemp` directory.
- Keep the single-node architecture. This plan intentionally avoids introducing a database, message broker, or distributed queue.
- Do not claim "production-grade" again until a fresh matrix summary shows `ready_for_production=true` for all required scales `xs`, `s`, and `m`.

## External References

- FastAPI deployment concepts emphasize HTTPS termination outside the app process, startup supervision, and restart handling by an external component, which is why this plan ships explicit API/worker service artifacts and TLS-aware cutover docs: [FastAPI Deployments Concepts](https://fastapi.tiangolo.com/deployment/concepts/)
- pytest documents that `tmp_path` already provides per-test unique directories and that `--basetemp` clears its target blindly with no retention, which is why this plan switches the deterministic gate guidance to `PYTEST_DEBUG_TEMPROOT` rather than a shared `--basetemp`: [pytest tmp_path docs](https://docs.pytest.org/en/stable/how-to/tmp_path.html)
- OWASP logging guidance highlights consistent application logging and audit trails for additions, modifications, deletions, and operational/security events; the existing audit work stays part of the production gate assumptions in this closure plan: [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
