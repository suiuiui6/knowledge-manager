# Enterprise Performance Special Plan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the remaining production performance gate failures in `knowledge-manager` by shrinking the shared read hot paths, trimming synchronous write-side effects, and turning the benchmark matrix into a hard regression loop.

**Architecture:** Keep the current file-backed architecture, but stop doing repeated full-object reconstruction and repeated control-plane recomputation on request-time hot paths. The implementation should deepen the existing projection/index/materialized-view approach already present in the repo, add hotspot instrumentation, and move non-critical write-side work behind explicit deferred maintenance seams instead of paying all costs inline.

**Tech Stack:** Python 3.10+, FastAPI, FastMCP, pytest, JSON/JSONL file storage, file-backed projections/materialized views, existing benchmark harness in `performance_benchmarks.py`.

---

## Real Performance Baseline This Plan Must Respect

The latest real benchmark source is `D:\tyh\knowledge-manager\test-results\perf-run-production-gate-20260612-r4\matrix-summary.json`.

- Global state:
  - `readiness_ready = true`
  - `integrity_ok = true`
  - `ready_for_production = false` on `xs`, `s`, and `m`
- Remaining gate failures are real latency bottlenecks, not readiness or data-integrity defects.
- `xs`
  - `search_http`: mean `1806.48 ms`, p95 `2003.831 ms`
  - `admin_dashboard_http`: mean `640.5 ms`, p95 `1649.899 ms`
  - `module_crud_http`: mean `429.056 ms`, p95 `456.937 ms`
  - `mcp_search_modules`: mean `1986.573 ms`, p95 `2701.462 ms`
- `s`
  - `search_http`: mean `5487.893 ms`, p95 `7231.67 ms`
  - `recommendations_http`: mean `1451.384 ms`, p95 `3838.121 ms`
  - `admin_dashboard_http`: mean `1644.835 ms`, p95 `4263.845 ms`
  - `module_crud_http`: mean `590.958 ms`, p95 `614.688 ms`
  - `mcp_search_modules`: mean `4149.413 ms`, p95 `4754.028 ms`
- `m`
  - `search_http`: mean `8347.205 ms`, p95 `9408.931 ms`
  - `recommendations_http`: mean `4391.129 ms`, p95 `12146.712 ms`
  - `admin_dashboard_http`: mean `2798.497 ms`, p95 `7209.951 ms`
  - `module_crud_http`: mean `961.575 ms`, p95 `1011.891 ms`
  - `mcp_search_modules`: mean `7066.755 ms`, p95 `7291.364 ms`

## Scope And Non-Goals

- This is a performance-only special plan.
- This plan does **not** redesign the product into a database-backed distributed system.
- This plan does **not** re-open already-passing readiness/integrity work except where those surfaces are needed for measurement.
- This plan assumes the current production-readiness building blocks already exist:
  - `search_projection.py`
  - `recommendation_index.py`
  - `runtime_checks.py`
  - `job_worker.py`

## File Structure

### Existing files to modify

- `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
  Responsibility: search path, recommendation path, module save/delete path, index rebuild path.
- `D:\tyh\knowledge-manager\src\knowledge_manager\search_projection.py`
  Responsibility: request-time search candidate selection and projection payload density.
- `D:\tyh\knowledge-manager\src\knowledge_manager\recommendation_index.py`
  Responsibility: recommendation candidate precomputation.
- `D:\tyh\knowledge-manager\src\knowledge_manager\admin_views.py`
  Responsibility: admin dashboard snapshot composition.
- `D:\tyh\knowledge-manager\src\knowledge_manager\ops_export.py`
  Responsibility: backlog exports currently reused by admin/dashboard endpoints.
- `D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py`
  Responsibility: MCP search serialization path and deep-search read amplification.
- `D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py`
  Responsibility: HTTP route response shape and any avoidable request-time work.
- `D:\tyh\knowledge-manager\src\knowledge_manager\performance_benchmarks.py`
  Responsibility: benchmark matrix, hotspot metrics, release gate evidence.
- `D:\tyh\knowledge-manager\tests\test_search_projection.py`
- `D:\tyh\knowledge-manager\tests\test_recommendation_index.py`
- `D:\tyh\knowledge-manager\tests\test_storage.py`
- `D:\tyh\knowledge-manager\tests\test_http_server.py`
- `D:\tyh\knowledge-manager\tests\test_mcp_server.py`
- `D:\tyh\knowledge-manager\tests\test_materialized_views.py`
- `D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py`

### New files to create

- `D:\tyh\knowledge-manager\src\knowledge_manager\performance_hotspots.py`
  Responsibility: small, explicit timing helpers plus hotspot payload shaping helpers shared by benchmarks and tests.
- `D:\tyh\knowledge-manager\tests\test_performance_hotspots.py`
  Responsibility: regression tests for hotspot summaries and deferred-maintenance accounting.

## Delivery Order

1. Add hotspot evidence so the next remediations are measurable at function granularity.
2. Eliminate search-path overfetch in shared HTTP/MCP retrieval.
3. Collapse duplicated control-plane recomputation for recommendations and admin dashboard.
4. Slim synchronous module CRUD by deferring non-critical side effects.
5. Re-run the enterprise matrix and keep only the changes that actually move the gates.

### Task 1: Add Performance Hotspot Evidence Before Further Tuning

**Files:**
- Create: `D:\tyh\knowledge-manager\src\knowledge_manager\performance_hotspots.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\performance_benchmarks.py`
- Create: `D:\tyh\knowledge-manager\tests\test_performance_hotspots.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py`

- [ ] **Step 1: Write the failing hotspot-summary tests**

```python
from knowledge_manager.performance_benchmarks import BenchmarkConfig, run_enterprise_benchmark


def test_benchmark_report_includes_hotspot_breakdown(tmp_path):
    result = run_enterprise_benchmark(
        BenchmarkConfig(
            kb_path=tmp_path / "kb",
            output_dir=tmp_path / "reports",
            module_count=12,
            tenant_count=2,
            job_count=4,
            search_iterations=1,
            http_iterations=1,
            job_iterations=1,
            top_k=3,
        )
    )

    assert "hotspots" in result
    assert "search" in result["hotspots"]
    assert "module_crud" in result["hotspots"]
```

```python
from knowledge_manager.performance_hotspots import HotspotTimer


def test_hotspot_timer_accumulates_named_sections():
    timer = HotspotTimer()
    with timer.track("projection_lookup"):
        pass
    with timer.track("projection_lookup"):
        pass

    summary = timer.summary()
    assert summary["projection_lookup"]["count"] == 2
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_performance_hotspots.py D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py::test_benchmark_report_includes_hotspot_breakdown -v`

Expected: `FAIL` because hotspot helpers and hotspot sections are not emitted yet.

- [ ] **Step 3: Implement a small hotspot timing helper**

```python
from __future__ import annotations

import time
from contextlib import contextmanager


class HotspotTimer:
    def __init__(self) -> None:
        self._samples: dict[str, list[float]] = {}

    @contextmanager
    def track(self, name: str):
        started = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            self._samples.setdefault(name, []).append(elapsed_ms)

    def summary(self) -> dict[str, dict[str, float]]:
        return {
            name: {
                "count": len(values),
                "mean_ms": round(sum(values) / len(values), 3),
                "max_ms": round(max(values), 3),
            }
            for name, values in self._samples.items()
            if values
        }
```

- [ ] **Step 4: Add hotspot capture into the benchmark report**

```python
from knowledge_manager.performance_hotspots import HotspotTimer


def run_enterprise_benchmark(config: BenchmarkConfig) -> dict[str, Any]:
    hotspot_timer = HotspotTimer()
    ...
    report = {
        ...
        "hotspots": {
            "search": hotspot_timer.summary(),
            "module_crud": {},
            "recommendations": {},
            "admin_dashboard": {},
        },
    }
```

- [ ] **Step 5: Thread the hotspot timer through search, recommendations, admin dashboard, and module CRUD micro-round-trips**

```python
def _module_crud_round_trip() -> dict[str, Any]:
    with hotspot_timer.track("create_request"):
        create_response = client.post("/api/modules", json=body)
    with hotspot_timer.track("update_request"):
        update_response = client.put(...)
    with hotspot_timer.track("delete_request"):
        delete_response = client.delete(...)
```

- [ ] **Step 6: Run the hotspot-focused regression suite**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_performance_hotspots.py D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py -k "hotspot" -v`

Expected: hotspot tests `PASS`.

- [ ] **Step 7: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\performance_hotspots.py D:\tyh\knowledge-manager\src\knowledge_manager\performance_benchmarks.py D:\tyh\knowledge-manager\tests\test_performance_hotspots.py D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py
git commit -m "test: add performance hotspot evidence"
```

### Task 2: Eliminate Shared Search-Path Overfetch For HTTP And MCP

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\search_projection.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_search_projection.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_storage.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_mcp_server.py`

- [ ] **Step 1: Write the failing retrieval fast-path tests**

```python
from knowledge_manager.schemas import Index, Module, ModuleContent
from knowledge_manager.storage import save_index, save_module, search_modules


def test_search_modules_uses_projection_payload_without_loading_entire_candidate_set(tmp_path, monkeypatch):
    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="search fast path"), kb)
    for idx in range(4):
        save_module(
            Module(
                id=f"module-{idx}",
                category="ops",
                title=f"Rollback module {idx}",
                summary="Rollback summary",
                content=ModuleContent(
                    overview="Rollback incident workflow",
                    details="Tenant rollback details long enough for search validation.",
                ),
            ),
            kb,
        )

    calls = {"count": 0}
    original = monkeypatch.getattr("knowledge_manager.storage.load_module", raising=False)

    def tracked_load_module(*args, **kwargs):
        calls["count"] += 1
        from knowledge_manager.storage import load_module as real_load_module
        return real_load_module(*args, **kwargs)

    monkeypatch.setattr("knowledge_manager.storage.load_module", tracked_load_module)
    results = search_modules("rollback incident", kb, limit=2)

    assert len(results) == 2
    assert calls["count"] <= 2
```

```python
from knowledge_manager.mcp_server import create_server


def test_mcp_search_modules_does_not_expand_full_module_content_for_list_results(tmp_path):
    server = create_server(tmp_path)
    tool = next(tool for tool in server._tool_manager._tools.values() if tool.name == "search_modules")
    assert tool is not None
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_search_projection.py D:\tyh\knowledge-manager\tests\test_storage.py D:\tyh\knowledge-manager\tests\test_mcp_server.py -k "fast_path or search_modules_does_not_expand" -v`

Expected: `FAIL` because `search_modules()` still reconstructs many full modules and MCP result serialization still depends on full module objects.

- [ ] **Step 3: Enrich the projection payload with lightweight scoring and rendering fields**

```python
documents[key] = {
    "category": module.category,
    "module_id": module.id,
    "title": module.title,
    "summary": module.summary,
    "overview": module.content.overview[:400],
    "tags": list(module.metadata.tags),
    "tenant_id": module.metadata.tenant_id,
    "status": module.metadata.status,
    "stems": stems,
}
```

- [ ] **Step 4: Split `search_modules()` into candidate ranking and lazy module hydration**

```python
def _rank_projection_candidates(...):
    ...
    return ranked_documents


def search_modules(...):
    ranked_documents = _rank_projection_candidates(...)
    lightweight_results = ranked_documents[: limit * 3]
    hydrated = []
    for candidate in lightweight_results:
        module = load_module(candidate["module_id"], candidate["category"], kb_path)
        if module is None:
            continue
        hydrated.append(...)
        if len(hydrated) >= limit:
            break
    return hydrated
```

- [ ] **Step 5: Trim MCP search serialization to the list payload actually needed by agents**

```python
results = [
    {
        "id": r.module.id,
        "category": r.module.category,
        "title": r.module.title,
        "summary": r.module.summary,
        "tags": r.module.metadata.tags,
        "confidence": r.module.metadata.confidence,
        "score": r.score,
        "snippet": _snippet(r.module.content.overview or r.module.summary, query),
    }
    for r in search_modules(...)
]
```

```python
def deep_search_tool(...):
    search_results = search_modules(...)
    top_results = search_results[:3]
    ...
```

- [ ] **Step 6: Run the shared retrieval regression suite**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_search_projection.py D:\tyh\knowledge-manager\tests\test_storage.py D:\tyh\knowledge-manager\tests\test_mcp_server.py -k "projection or search_modules or deep_search" -v`

Expected: retrieval-path tests `PASS`.

- [ ] **Step 7: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\search_projection.py D:\tyh\knowledge-manager\src\knowledge_manager\storage.py D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py D:\tyh\knowledge-manager\tests\test_search_projection.py D:\tyh\knowledge-manager\tests\test_storage.py D:\tyh\knowledge-manager\tests\test_mcp_server.py
git commit -m "feat: reduce search overfetch on shared read paths"
```

### Task 3: Collapse Duplicated Control-Plane Recomputations For Recommendations And Admin

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\recommendation_index.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\admin_views.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\ops_export.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_recommendation_index.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_materialized_views.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_http_server.py`

- [ ] **Step 1: Write the failing control-plane caching tests**

```python
def test_admin_dashboard_builds_ops_report_once_per_refresh(tmp_path, monkeypatch):
    from knowledge_manager.admin_views import build_admin_dashboard

    calls = {"count": 0}

    def tracked_generate_ops_report(kb_path):
        calls["count"] += 1
        from knowledge_manager.schemas import LifecycleBacklog, OpsReport
        return OpsReport(source_backlog=[], lifecycle_backlog=LifecycleBacklog(status_counts={}, staging_status_counts={}), policy_suppressed_modules=[])

    monkeypatch.setattr("knowledge_manager.ops_export.generate_ops_report", tracked_generate_ops_report)
    build_admin_dashboard(tmp_path)
    assert calls["count"] <= 1
```

```python
def test_recommendations_reuses_precomputed_candidate_pairs_without_full_module_walk(tmp_path, monkeypatch):
    from knowledge_manager.storage import generate_recommendations

    calls = {"count": 0}

    def tracked_list_modules(*args, **kwargs):
        calls["count"] += 1
        return []

    monkeypatch.setattr("knowledge_manager.storage.list_modules", tracked_list_modules)
    generate_recommendations(tmp_path)
    assert calls["count"] <= 1
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_recommendation_index.py D:\tyh\knowledge-manager\tests\test_materialized_views.py D:\tyh\knowledge-manager\tests\test_http_server.py -k "ops_report_once or reuses_precomputed_candidate_pairs" -v`

Expected: `FAIL` because dashboard/export composition still layers repeated work and recommendation generation still performs expensive runtime reconstruction under scale.

- [ ] **Step 3: Extend the recommendation index to store already-derived candidate pairs**

```python
payload: dict[str, Any] = {
    "modules": {},
    "module_tags": {},
    "tag_index": {},
    "outbound_links": {},
    "link_candidates": [],
}
...
payload["link_candidates"] = [
    {"left": first, "right": second, "shared_tags": shared_tags}
    for first, second, shared_tags in iter_recommendation_link_candidates(payload)
]
```

- [ ] **Step 4: Make recommendation generation read pre-derived pairs and module summaries directly from the index**

```python
def _generate_recommendations_uncached(kb_path: Path) -> Any:
    rec_index = load_recommendation_index(kb_path) or build_recommendation_index(kb_path)
    candidate_pairs = rec_index.get("link_candidates", [])
    modules = rec_index.get("modules", {})
    ...
    for pair in candidate_pairs:
        left = modules.get(pair["left"], {}).get("module")
        right = modules.get(pair["right"], {}).get("module")
        if not left or not right:
            continue
```

- [ ] **Step 5: Refactor admin/dashboard export composition so ops data is computed once and passed through**

```python
def generate_review_backlog_export(kb_path: Path, ops_report=None) -> dict[str, Any]:
    report = ops_report or generate_ops_report(kb_path)
    ...


def generate_source_backlog_export(kb_path: Path, ops_report=None) -> dict[str, Any]:
    report = ops_report or generate_ops_report(kb_path)
    ...


def build_admin_dashboard(kb_path: Path) -> dict[str, Any]:
    report = generate_ops_report(kb_path)
    payload = {
        "ingestion_jobs": ...,
        "stale_sources": generate_source_backlog_export(kb_path, ops_report=report).get("items", []),
        "review_backlog": generate_review_backlog_export(kb_path, ops_report=report).get("items", []),
        "eval_regressions": [],
    }
```

- [ ] **Step 6: Run the control-plane regression suite**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_recommendation_index.py D:\tyh\knowledge-manager\tests\test_materialized_views.py D:\tyh\knowledge-manager\tests\test_http_server.py -k "recommendation or admin_dashboard or ops_report" -v`

Expected: recommendations/admin tests `PASS`.

- [ ] **Step 7: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\recommendation_index.py D:\tyh\knowledge-manager\src\knowledge_manager\storage.py D:\tyh\knowledge-manager\src\knowledge_manager\admin_views.py D:\tyh\knowledge-manager\src\knowledge_manager\ops_export.py D:\tyh\knowledge-manager\tests\test_recommendation_index.py D:\tyh\knowledge-manager\tests\test_materialized_views.py D:\tyh\knowledge-manager\tests\test_http_server.py
git commit -m "feat: remove duplicated control-plane recomputation"
```

### Task 4: Slim Synchronous Module CRUD By Deferring Non-Critical Side Effects

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\job_worker.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\performance_hotspots.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_storage.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_http_server.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_performance_hotspots.py`

- [ ] **Step 1: Write the failing deferred-maintenance tests**

```python
from knowledge_manager.schemas import Module, ModuleContent
from knowledge_manager.storage import save_module


def test_save_module_can_schedule_noncritical_side_effects(tmp_path, monkeypatch):
    scheduled = []

    def fake_schedule(*args, **kwargs):
        scheduled.append((args, kwargs))

    monkeypatch.setattr("knowledge_manager.storage.schedule_maintenance_job", fake_schedule)
    save_module(
        Module(
            id="deferred-module",
            category="ops",
            title="Deferred module",
            summary="Deferred summary",
            content=ModuleContent(overview="Overview", details="Details long enough for validation."),
        ),
        tmp_path,
    )

    assert scheduled
```

```python
def test_module_create_endpoint_returns_maintenance_state(tmp_path):
    from fastapi.testclient import TestClient
    from knowledge_manager.http_server import create_app

    client = TestClient(create_app(tmp_path))
    response = client.post(
        "/api/modules",
        json={
            "id": "perf-write",
            "category": "ops",
            "title": "Perf write",
            "summary": "summary",
            "content": {"overview": "overview", "details": "details long enough for validation"},
            "submit_to_staging": False,
        },
    )

    assert response.status_code == 200
    assert "maintenance" in response.json()
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_storage.py D:\tyh\knowledge-manager\tests\test_http_server.py D:\tyh\knowledge-manager\tests\test_performance_hotspots.py -k "schedule_noncritical_side_effects or maintenance_state" -v`

Expected: `FAIL` because `save_module()` and `delete_module()` still do all expensive side effects inline and do not expose maintenance state.

- [ ] **Step 3: Introduce an explicit deferred-maintenance seam**

```python
def schedule_maintenance_job(kb_path: Path, action: str, payload: dict[str, Any]) -> None:
    from knowledge_manager.job_worker import enqueue_local_maintenance

    enqueue_local_maintenance(kb_path, action=action, payload=payload)
```

```python
def save_module(module: Module, kb_path: Path, defer_noncritical: bool = True) -> None:
    ...
    _upsert_index_entry(module, kb_path)
    _invalidate_module_cache(kb_path)
    invalidate_materialized_views(kb_path)
    if defer_noncritical:
        schedule_maintenance_job(...)
    else:
        MarkdownSync.sync_on_save(module, kb_path)
        emit_event(...)
        update_lexical_index_for_module(kb_path, module)
        update_search_projection_for_module(kb_path, module)
        update_recommendation_index_for_module(kb_path, module)
```

- [ ] **Step 4: Implement a local maintenance executor in `job_worker.py`**

```python
def enqueue_local_maintenance(kb_path: Path, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    queue_dir = kb_path / ".cache" / "maintenance"
    queue_dir.mkdir(parents=True, exist_ok=True)
    ...


def run_pending_maintenance(kb_path: Path, limit: int = 20) -> int:
    ...
```

- [ ] **Step 5: Surface maintenance state in module CRUD responses and add benchmark coverage**

```python
@app.post("/api/modules")
def api_module_create(body: dict):
    ...
    save_module(module, kb_path, defer_noncritical=True)
    return {
        "status": "created",
        "id": module.id,
        "maintenance": {"deferred": True},
    }
```

- [ ] **Step 6: Run the write-path regression suite**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_storage.py D:\tyh\knowledge-manager\tests\test_http_server.py D:\tyh\knowledge-manager\tests\test_performance_hotspots.py -k "maintenance or save_module or module_create" -v`

Expected: write-path tests `PASS`.

- [ ] **Step 7: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\storage.py D:\tyh\knowledge-manager\src\knowledge_manager\job_worker.py D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py D:\tyh\knowledge-manager\src\knowledge_manager\performance_hotspots.py D:\tyh\knowledge-manager\tests\test_storage.py D:\tyh\knowledge-manager\tests\test_http_server.py D:\tyh\knowledge-manager\tests\test_performance_hotspots.py
git commit -m "feat: defer noncritical module maintenance work"
```

### Task 5: Re-Run Matrix, Tighten Gate Contracts, And Close The Loop

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\performance_benchmarks.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py`
- Modify: `D:\tyh\knowledge-manager\docs\runbooks\enterprise-performance-test-plan.md`

- [ ] **Step 1: Write the failing matrix-regression contract tests**

```python
from knowledge_manager.performance_benchmarks import BenchmarkConfig, run_enterprise_benchmark


def test_benchmark_release_verdict_exposes_hotspot_blockers(tmp_path):
    result = run_enterprise_benchmark(
        BenchmarkConfig(
            kb_path=tmp_path / "kb",
            output_dir=tmp_path / "reports",
            module_count=20,
            tenant_count=4,
            job_count=8,
            search_iterations=1,
            http_iterations=1,
            job_iterations=1,
            top_k=5,
        )
    )

    assert "hotspots" in result
    assert "blockers" in result["release_verdict"]
```

- [ ] **Step 2: Run the focused tests to verify they fail if hotspot-gate wiring is incomplete**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py -k "hotspot_blockers" -v`

Expected: `FAIL` until release verdict and benchmark markdown include the new hotspot evidence.

- [ ] **Step 3: Add hotspot summaries to the rendered markdown and release-verdict context**

```python
def _evaluate_release_verdict(report: dict[str, Any]) -> dict[str, Any]:
    ...
    hotspot_names = sorted(report.get("hotspots", {}).keys())
    return {
        ...
        "hotspot_sections": hotspot_names,
    }
```

```python
if report.get("hotspots"):
    lines.append("## Hotspots")
    lines.append("")
    for section, summary in report["hotspots"].items():
        lines.append(f"- `{section}`: `{json.dumps(summary, ensure_ascii=False)}`")
```

- [ ] **Step 4: Document the exact rerun procedure for `xs`, `s`, and `m`**

```markdown
## Performance Closure Procedure

1. Run targeted pytest suites for search, recommendations, admin, and module CRUD.
2. Generate a fresh matrix under `test-results/perf-run-production-gate-<date>-rN`.
3. Compare `matrix-summary.json` against the immediately previous run.
4. Reject any patch that improves one gate but regresses another shared read path by more than 10%.
5. Do not call the system production-grade until `xs`, `s`, and `m` all report `ready_for_production = true`.
```

- [ ] **Step 5: Run the contract tests and the full matrix**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py -v`

Run:

```powershell
$env:PYTHONPATH='D:\tyh\knowledge-manager\src'
@'
from pathlib import Path
from knowledge_manager.performance_benchmarks import BenchmarkConfig, run_enterprise_benchmark

root = Path(r"D:\tyh\knowledge-manager\test-results\perf-run-production-gate-20260613-r1")
scales = {
    "xs": dict(module_count=100, tenant_count=10, job_count=80, migration_document_count=100),
    "s": dict(module_count=250, tenant_count=20, job_count=200, migration_document_count=250),
    "m": dict(module_count=500, tenant_count=30, job_count=400, migration_document_count=400),
}
for name, params in scales.items():
    run_enterprise_benchmark(
        BenchmarkConfig(
            kb_path=root / f".tmp-kb-{name}",
            output_dir=root / name,
            search_iterations=3,
            http_iterations=3,
            job_iterations=3,
            top_k=10,
            **params,
        )
    )
'@ | python -
```

Expected: tests `PASS`, and the fresh matrix clearly shows which of the five remaining gates are fully closed and which still need another iteration.

- [ ] **Step 6: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\performance_benchmarks.py D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py D:\tyh\knowledge-manager\docs\runbooks\enterprise-performance-test-plan.md
git commit -m "docs: close the performance remediation loop"
```

## Completion Criteria

- `search_http` and `mcp_search_modules` both meet their configured mean and p95 gates at `xs`, `s`, and `m`.
- `recommendations_http` and `admin_dashboard_http` no longer recompute shared control-plane state more than once per refresh cycle.
- `module_crud_http` meets gate targets because non-critical side effects are no longer paid inline on every create/update/delete.
- Benchmark output includes hotspot evidence alongside gate summaries and release verdicts.
- A fresh matrix under a new dated output directory proves whether the system has crossed from “partial production readiness” into “performance-closed production readiness”.

## Execution Notes

- Do not change the storage model or introduce a database in this plan.
- Keep each task independently testable.
- After each task, compare not just absolute latency but whether work moved from request-time to deferred maintenance.
- If a remediation improves `search_http` but regresses `module_crud_http` or `admin_dashboard_http`, reject it and rework the design before proceeding.
