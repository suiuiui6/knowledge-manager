# Production Readiness Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `knowledge-manager` from its current准生产级 state to a real production-grade, industrial-grade single-node enterprise deployment baseline with passing core latency gates, non-blocking ingestion workflows, startup/readiness protection, and repeatable release evidence.

**Architecture:** Keep the current file-based, inspectable architecture and build only what the codebase now needs: precomputed search projections for the still-slow retrieval path, pre-aggregated recommendation state for the remaining control-plane hotspot, durable background execution for upload/source ingestion, explicit readiness/metrics/integrity endpoints, and a production release harness that proves the system meets gates instead of merely looking feature-complete. This plan does not introduce distributed infrastructure or a database rewrite because the current repo is not at that boundary yet; it focuses on making the existing architecture production-worthy first.

**Tech Stack:** Python 3.10+, FastAPI, FastMCP, pytest, JSON/JSONL storage, existing ingestion job model, file-backed caches/materialized views, optional provider-backed LLM clients.

---

## Real Current State This Plan Must Respect

From the latest real remediated benchmark run already produced in `test-results/perf-run-20260612-remediated/matrix-summary.json`:

- `module_crud_http` already passes all configured mean/p95 gates from `xs` through `m`.
- `admin_dashboard_http` passes at `xs` and `s`, but still fails at `m` with mean `922.465 ms`.
- `recommendations_http` improved sharply but still fails at `s` (`1533.545 ms`) and `m` (`4297.832 ms`).
- `search_http` and `mcp_search_modules` are still the main blockers:
  - `xs`: about `1508 ms` / `1528 ms`
  - `s`: about `3802 ms` / `3792 ms`
  - `m`: about `8238 ms` / `8237 ms`
- `/api/upload` is still synchronous in `http_server.py`, even though provider burst size was reduced.
- There is still no service-level readiness endpoint, startup validation contract, Prometheus-style metrics endpoint, or integrity/repair workflow that would support real production rollout.

## What “Production-Grade” Means For This Repo

For the current architecture, production-grade means all of the following are true at the same time:

- Search, MCP search, recommendations, admin dashboard, and write paths pass the benchmark gates already encoded in `performance_benchmarks.py`.
- Upload and source ingestion no longer block HTTP requests on provider work.
- Startup fails fast on invalid runtime config and exposes a readiness surface distinct from knowledge-quality health.
- Operators can inspect metrics, integrity status, repair indexes/projections, and recover from on-disk drift without manual JSON surgery.
- Release evidence includes deterministic tests, benchmark gates, and a documented rollback checklist.

This plan deliberately does **not** claim “group-grade” or “multi-cluster” readiness. It targets a strong, production-worthy single-node enterprise deployment.

## File Structure

### Existing files to extend

- `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
  Responsibility: module persistence, retrieval path, report generation, mutation invalidation.
- `D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py`
  Responsibility: HTTP API behavior, upload behavior, readiness/metrics endpoints.
- `D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py`
  Responsibility: MCP search and tool surfaces that currently inherit retrieval bottlenecks.
- `D:\tyh\knowledge-manager\src\knowledge_manager\ingestion_jobs.py`
  Responsibility: durable job state model, checkpointing, job lifecycle.
- `D:\tyh\knowledge-manager\src\knowledge_manager\source_ingestion.py`
  Responsibility: source sync orchestration and staging workflow.
- `D:\tyh\knowledge-manager\src\knowledge_manager\extractor.py`
  Responsibility: provider-backed extraction workload.
- `D:\tyh\knowledge-manager\src\knowledge_manager\materialized_views.py`
  Responsibility: current control-plane snapshot layer.
- `D:\tyh\knowledge-manager\src\knowledge_manager\admin_views.py`
  Responsibility: admin dashboard aggregation.
- `D:\tyh\knowledge-manager\src\knowledge_manager\performance_benchmarks.py`
  Responsibility: enterprise benchmark matrix and gate summary.
- `D:\tyh\knowledge-manager\src\knowledge_manager\cli.py`
  Responsibility: operator commands, repair entrypoints, production diagnostics.
- `D:\tyh\knowledge-manager\tests\test_storage.py`
- `D:\tyh\knowledge-manager\tests\test_http_server.py`
- `D:\tyh\knowledge-manager\tests\test_mcp_server.py`
- `D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py`
- `D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py`

### New files to create

- `D:\tyh\knowledge-manager\src\knowledge_manager\search_projection.py`
  Responsibility: precomputed search documents, term stats, and candidate metadata so the query path stops reparsing/scoring the whole KB.
- `D:\tyh\knowledge-manager\src\knowledge_manager\recommendation_index.py`
  Responsibility: precomputed module-tag adjacency and archive/enrichment/review candidate inputs for recommendations.
- `D:\tyh\knowledge-manager\src\knowledge_manager\job_worker.py`
  Responsibility: local background worker loop for upload extraction and source sync jobs.
- `D:\tyh\knowledge-manager\src\knowledge_manager\runtime_checks.py`
  Responsibility: startup validation, readiness evaluation, metrics snapshot helpers, integrity checks.
- `D:\tyh\knowledge-manager\tests\test_search_projection.py`
  Responsibility: projection build/incremental update/query path coverage.
- `D:\tyh\knowledge-manager\tests\test_recommendation_index.py`
  Responsibility: recommendation preaggregation and invalidation coverage.
- `D:\tyh\knowledge-manager\tests\test_runtime_checks.py`
  Responsibility: startup validation, readiness, metrics, and integrity endpoint coverage.
- `D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md`
  Responsibility: rollout steps, rollback triggers, recovery commands, and gate evidence checklist.

## Delivery Stages

1. Make retrieval pass production gates
2. Eliminate the last slow control-plane hotspot
3. Move long provider work off the request path
4. Add production readiness, metrics, and integrity controls
5. Lock release with full benchmark and operational evidence

### Task 1: Replace Full-KB Search Scoring With A Production Search Projection

**Files:**
- Create: `D:\tyh\knowledge-manager\src\knowledge_manager\search_projection.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
- Create: `D:\tyh\knowledge-manager\tests\test_search_projection.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_storage.py`

- [ ] **Step 1: Write the failing projection and search-path tests**

```python
from knowledge_manager.schemas import Index, Module, ModuleContent
from knowledge_manager.storage import save_index, save_module, search_modules


def test_search_projection_updates_on_save_without_full_scan(tmp_path, monkeypatch):
    from knowledge_manager.search_projection import build_search_projection, load_search_projection

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="projection test"), kb)
    save_module(
        Module(
            id="rollback-guide",
            category="ops",
            title="Rollback Guide",
            summary="Rollback summary.",
            content=ModuleContent(
                overview="Rollback safely during incidents.",
                details="Detailed rollback workflow and incident handling.",
            ),
        ),
        kb,
    )
    build_search_projection(kb)

    def explode(*_args, **_kwargs):
        raise AssertionError("full projection rebuild should not run on save")

    monkeypatch.setattr("knowledge_manager.search_projection.build_search_projection", explode)
    save_module(
        Module(
            id="tenant-runbook",
            category="ops",
            title="Tenant Isolation Runbook",
            summary="Tenant isolation summary.",
            content=ModuleContent(
                overview="Contain tenant blast radius quickly.",
                details="Detailed isolation steps for multi-tenant incidents.",
            ),
        ),
        kb,
    )

    projection = load_search_projection(kb)
    assert "ops/tenant-runbook" in projection["documents"]


def test_search_modules_uses_projection_candidates_before_scoring(tmp_path, monkeypatch):
    from knowledge_manager.search_projection import build_search_projection

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="projection candidates"), kb)
    save_module(
        Module(
            id="rollback-guide",
            category="ops",
            title="Rollback Guide",
            summary="Rollback summary.",
            content=ModuleContent(
                overview="Rollback safely during incidents.",
                details="Detailed rollback workflow and incident handling.",
            ),
        ),
        kb,
    )
    build_search_projection(kb)

    calls = {"count": 0}

    def tracked_list_modules(*args, **kwargs):
        calls["count"] += 1
        return []

    monkeypatch.setattr("knowledge_manager.storage.list_modules", tracked_list_modules)
    results = search_modules("rollback incidents", kb)

    assert results[0].module.id == "rollback-guide"
    assert calls["count"] == 0
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_search_projection.py -v`

Expected: `FAIL` because `search_projection.py` does not exist and `search_modules()` still depends on full module traversal.

- [ ] **Step 3: Implement a persistent search projection with per-module scoring inputs**

```python
import json
from pathlib import Path
from typing import Any


def _projection_path(kb_path: Path) -> Path:
    return kb_path / ".cache" / "search_projection.json"


def build_search_projection(kb_path: Path) -> dict[str, Any]:
    from knowledge_manager.storage import _module_full_text, _WORD_RE, _stem, list_modules

    documents: dict[str, dict[str, Any]] = {}
    inverted: dict[str, list[str]] = {}
    for module in list_modules(kb_path):
        key = f"{module.category}/{module.id}"
        full_text = _module_full_text(module)
        stems: list[str] = []
        for word in _WORD_RE.findall(full_text.lower()):
            stems.extend(_stem(word).split())
        documents[key] = {
            "title": module.title,
            "summary": module.summary,
            "category": module.category,
            "status": module.metadata.status,
            "confidence": module.metadata.confidence,
            "tenant_id": module.metadata.tenant_id,
            "stems": stems,
            "tags": list(module.metadata.tags),
            "related_modules": list(module.metadata.related_modules),
        }
        for stem in sorted(set(stems)):
            inverted.setdefault(stem, []).append(key)
    payload = {"documents": documents, "inverted": inverted}
    path = _projection_path(kb_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload
```

- [ ] **Step 4: Route `search_modules()` and MCP search through projection-backed candidates**

```python
def search_modules(...):
    from knowledge_manager.search_projection import load_search_projection, query_search_projection

    projection = load_search_projection(kb_path)
    if projection is None:
        projection = build_search_projection(kb_path)
    candidate_keys = query_search_projection(projection, query, tenant=tenant, category=category)
    if not candidate_keys:
        return []
    candidate_modules = [
        load_module(module_id, module_category, kb_path)
        for module_category, module_id in (key.split("/", 1) for key in candidate_keys[:120])
    ]
```

- [ ] **Step 5: Add incremental update/delete helpers and wire them to mutation paths**

```python
def update_search_projection_for_module(kb_path: Path, module: Module) -> None:
    payload = load_search_projection(kb_path) or {"documents": {}, "inverted": {}}
    remove_search_projection_for_module(kb_path, module.category, module.id, payload=payload)
    ...


def remove_search_projection_for_module(kb_path: Path, category: str, module_id: str, payload: dict | None = None) -> None:
    ...
```

```python
def save_module(module: Module, kb_path: Path) -> None:
    ...
    update_search_projection_for_module(kb_path, module)


def delete_module(module_id: str, category: str, kb_path: Path) -> bool:
    ...
    remove_search_projection_for_module(kb_path, category, module_id)
```

- [ ] **Step 6: Run focused retrieval regressions**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_search_projection.py D:\tyh\knowledge-manager\tests\test_storage.py D:\tyh\knowledge-manager\tests\test_mcp_server.py -k "projection or search_modules" -v`

Expected: all projection and search regressions `PASS`.

- [ ] **Step 7: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\search_projection.py D:\tyh\knowledge-manager\src\knowledge_manager\storage.py D:\tyh\knowledge-manager\tests\test_search_projection.py D:\tyh\knowledge-manager\tests\test_storage.py D:\tyh\knowledge-manager\tests\test_mcp_server.py
git commit -m "feat: add production search projection"
```

### Task 2: Precompute Recommendation Inputs So `recommendations_http` Passes At `s` And `m`

**Files:**
- Create: `D:\tyh\knowledge-manager\src\knowledge_manager\recommendation_index.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\materialized_views.py`
- Create: `D:\tyh\knowledge-manager\tests\test_recommendation_index.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_storage.py`

- [ ] **Step 1: Write the failing recommendation-index tests**

```python
from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata
from knowledge_manager.storage import generate_recommendations, rebuild_index, save_index, save_module


def test_recommendation_index_builds_link_candidates_from_shared_tags(tmp_path):
    from knowledge_manager.recommendation_index import build_recommendation_index, load_recommendation_index

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="recommendation index"), kb)
    save_module(
        Module(
            id="a",
            category="ops",
            title="A",
            summary="A summary",
            content=ModuleContent(overview="A overview", details="A details long enough for validation."),
            metadata=ModuleMetadata(tags=["incident", "rollback"]),
        ),
        kb,
    )
    save_module(
        Module(
            id="b",
            category="ops",
            title="B",
            summary="B summary",
            content=ModuleContent(overview="B overview", details="B details long enough for validation."),
            metadata=ModuleMetadata(tags=["incident", "rollback"]),
        ),
        kb,
    )
    build_recommendation_index(kb)

    payload = load_recommendation_index(kb)
    assert payload["shared_tag_pairs"][0]["module_a"] == "ops/a"


def test_generate_recommendations_uses_precomputed_pairs(tmp_path, monkeypatch):
    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="recommendation runtime"), kb)
    ...
    rebuild_index(kb)
    generate_recommendations(kb)

    monkeypatch.setattr("knowledge_manager.storage.compute_module_health", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("recomputed health unexpectedly")))
    cached = generate_recommendations(kb)
    assert cached.suggested_links
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_recommendation_index.py -v`

Expected: `FAIL` because `recommendation_index.py` does not exist and recommendations still rebuild pairwise state inline.

- [ ] **Step 3: Implement a recommendation preaggregation file**

```python
def build_recommendation_index(kb_path: Path) -> dict[str, Any]:
    from knowledge_manager.storage import list_modules

    tag_buckets: dict[str, list[str]] = {}
    module_meta: dict[str, dict[str, Any]] = {}
    for module in list_modules(kb_path):
        key = f"{module.category}/{module.id}"
        module_meta[key] = {
            "status": module.metadata.status,
            "review_interval_days": module.metadata.review_interval_days,
            "tags": list(module.metadata.tags),
        }
        for tag in module.metadata.tags:
            tag_buckets.setdefault(tag, []).append(key)
    shared_tag_pairs = _derive_pairs(tag_buckets)
    return _write_recommendation_index(kb_path, {"module_meta": module_meta, "shared_tag_pairs": shared_tag_pairs})
```

- [ ] **Step 4: Feed `generate_recommendations()` from the recommendation index plus materialized views**

```python
def _generate_recommendations_uncached(kb_path: Path) -> Any:
    from knowledge_manager.recommendation_index import build_recommendation_index, load_recommendation_index

    rec_index = load_recommendation_index(kb_path) or build_recommendation_index(kb_path)
    ...
    for pair in rec_index["shared_tag_pairs"]:
        suggested_links.append(...)
```

- [ ] **Step 5: Add incremental update and invalidation**

```python
def save_module(module: Module, kb_path: Path) -> None:
    ...
    update_recommendation_index_for_module(kb_path, module)
    invalidate_materialized_views(kb_path, ["recommendations", "ops", "admin_dashboard"])
```

- [ ] **Step 6: Run focused recommendation/control-plane tests**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_recommendation_index.py D:\tyh\knowledge-manager\tests\test_materialized_views.py D:\tyh\knowledge-manager\tests\test_storage.py -k "recommendation or recommendations_http or admin_dashboard" -v`

Expected: all recommendation and control-plane tests `PASS`.

- [ ] **Step 7: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\recommendation_index.py D:\tyh\knowledge-manager\src\knowledge_manager\storage.py D:\tyh\knowledge-manager\src\knowledge_manager\materialized_views.py D:\tyh\knowledge-manager\tests\test_recommendation_index.py D:\tyh\knowledge-manager\tests\test_materialized_views.py D:\tyh\knowledge-manager\tests\test_storage.py
git commit -m "feat: precompute recommendation inputs"
```

### Task 3: Move Upload And Source Sync To A Real Local Background Worker

**Files:**
- Create: `D:\tyh\knowledge-manager\src\knowledge_manager\job_worker.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\ingestion_jobs.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\source_ingestion.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_http_server.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py`

- [ ] **Step 1: Write the failing async-worker tests**

```python
from fastapi.testclient import TestClient


def test_upload_endpoint_returns_accepted_job_id_and_does_not_extract_inline(tmp_path, monkeypatch):
    from knowledge_manager.http_server import create_app

    started = {"job_id": ""}

    def fake_start_upload_job(kb_path, filename, payload, category, mode):
        started["job_id"] = "job-upload-1"
        return "job-upload-1"

    monkeypatch.setattr("knowledge_manager.http_server._start_upload_job", fake_start_upload_job)
    client = TestClient(create_app(tmp_path))
    response = client.post("/api/upload", files={"file": ("demo.md", b"# title", "text/markdown")})

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert response.json()["job_id"] == "job-upload-1"


def test_job_worker_executes_upload_job_and_marks_completed(tmp_path):
    from knowledge_manager.ingestion_jobs import create_ingestion_job, load_ingestion_job
    from knowledge_manager.job_worker import run_single_job

    kb = tmp_path / "kb"
    kb.mkdir()
    job = create_ingestion_job(kb, source_id="upload", trigger="http-upload")
    run_single_job(kb, job.job_id, payload={"kind": "upload", "filename": "demo.md", "bytes_b64": "IyB0aXRsZQ=="})

    finished = load_ingestion_job(kb, job.job_id)
    assert finished.status == "completed"
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_http_server.py D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py -k "accepted_job_id or job_worker" -v`

Expected: `FAIL` because `/api/upload` still extracts inline and no worker exists.

- [ ] **Step 3: Extend the job model for payload kind and processing stage**

```python
class IngestionJob(BaseModel):
    job_id: str
    source_id: str
    trigger: str
    payload_kind: str = ""
    payload_path: str = ""
    stage: str = "queued"
    ...
```

- [ ] **Step 4: Implement a local worker seam**

```python
def run_single_job(kb_path: Path, job_id: str, payload: dict[str, Any] | None = None) -> IngestionJob:
    job = claim_ingestion_job(kb_path, job_id, worker_id="local-worker")
    if payload and payload["kind"] == "upload":
        return _run_upload_job(kb_path, job, payload)
    if payload and payload["kind"] == "source-sync":
        return _run_source_sync_job(kb_path, job, payload)
    return fail_ingestion_job(kb_path, job_id, "unknown job payload")
```

- [ ] **Step 5: Convert `/api/upload` to accept-and-process**

```python
def _start_upload_job(kb_path: Path, filename: str, payload: bytes, category: str, mode: str) -> str:
    tmp_dir = kb_path / ".tmp" / "uploads"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    payload_path = tmp_dir / filename
    payload_path.write_bytes(payload)
    job = create_ingestion_job(kb_path, source_id="upload", trigger="http-upload")
    update_job_payload(kb_path, job.job_id, payload_kind="upload", payload_path=str(payload_path))
    run_single_job(kb_path, job.job_id, payload={"kind": "upload", "path": str(payload_path), "category": category, "mode": mode})
    return job.job_id
```

```python
@app.post("/api/upload")
async def api_upload(...):
    job_id = _start_upload_job(kb_path, filename, content, category, mode)
    return {"status": "accepted", "job_id": job_id}
```

- [ ] **Step 6: Run focused job/upload tests**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_http_server.py D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py -k "upload or job_worker or source_sync" -v`

Expected: upload and worker tests `PASS`.

- [ ] **Step 7: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\job_worker.py D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py D:\tyh\knowledge-manager\src\knowledge_manager\ingestion_jobs.py D:\tyh\knowledge-manager\src\knowledge_manager\source_ingestion.py D:\tyh\knowledge-manager\tests\test_http_server.py D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py
git commit -m "feat: move upload and source sync to local worker jobs"
```

### Task 4: Add Startup Validation, Readiness, Metrics, And Integrity Checks

**Files:**
- Create: `D:\tyh\knowledge-manager\src\knowledge_manager\runtime_checks.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\cli.py`
- Create: `D:\tyh\knowledge-manager\tests\test_runtime_checks.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_http_server.py`

- [ ] **Step 1: Write the failing readiness and integrity tests**

```python
from fastapi.testclient import TestClient


def test_ready_endpoint_reports_config_error_when_default_provider_missing(tmp_path):
    from knowledge_manager.http_server import create_app

    (tmp_path / "config.json").write_text('{"llm_providers": {}}', encoding="utf-8")
    client = TestClient(create_app(tmp_path))
    response = client.get("/api/ready")

    assert response.status_code == 503
    assert "default provider" in response.json()["reasons"][0].lower()


def test_integrity_check_reports_missing_index_entry(tmp_path):
    from knowledge_manager.runtime_checks import run_integrity_check
    from knowledge_manager.schemas import Module, ModuleContent
    from knowledge_manager.storage import save_module

    kb = tmp_path / "kb"
    kb.mkdir()
    save_module(
        Module(
            id="orphan",
            category="ops",
            title="Orphan",
            summary="Orphan summary.",
            content=ModuleContent(overview="Overview", details="Details long enough for validation."),
        ),
        kb,
    )

    report = run_integrity_check(kb)
    assert report["issues"]
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_runtime_checks.py -v`

Expected: `FAIL` because readiness/integrity helpers do not exist.

- [ ] **Step 3: Implement startup validation and readiness evaluation**

```python
def evaluate_readiness(kb_path: Path) -> dict[str, Any]:
    from knowledge_manager.storage import load_index, _load_config_safe

    reasons: list[str] = []
    cfg = _load_config_safe(kb_path)
    if cfg is None:
        reasons.append("config missing or invalid")
    elif not cfg.llm_providers:
        reasons.append("default provider not configured")
    index = load_index(kb_path)
    if index is None:
        reasons.append("index missing")
    return {"ready": not reasons, "reasons": reasons}
```

- [ ] **Step 4: Expose `/api/ready`, `/api/metrics`, and CLI integrity commands**

```python
@app.get("/api/ready")
def api_ready():
    state = evaluate_readiness(kb_path)
    return JSONResponse(status_code=200 if state["ready"] else 503, content=state)


@app.get("/api/metrics")
def api_metrics():
    snapshot = collect_runtime_metrics(kb_path)
    return PlainTextResponse(snapshot, media_type="text/plain")
```

```python
@app.command("integrity-check")
def integrity_check_cmd(kb_path: str):
    report = run_integrity_check(Path(kb_path))
    print(json.dumps(report, ensure_ascii=False, indent=2))
```

- [ ] **Step 5: Run readiness/integrity tests**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_runtime_checks.py D:\tyh\knowledge-manager\tests\test_http_server.py -k "ready or integrity or metrics" -v`

Expected: readiness, metrics, and integrity tests `PASS`.

- [ ] **Step 6: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\runtime_checks.py D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py D:\tyh\knowledge-manager\src\knowledge_manager\cli.py D:\tyh\knowledge-manager\tests\test_runtime_checks.py D:\tyh\knowledge-manager\tests\test_http_server.py
git commit -m "feat: add production readiness and integrity checks"
```

### Task 5: Add Production Release Evidence, Soak Gates, And Rollback Runbook

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\performance_benchmarks.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py`
- Create: `D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md`
- Modify: `D:\tyh\knowledge-manager\docs\runbooks\enterprise-performance-test-plan.md`

- [ ] **Step 1: Write the failing production gate test**

```python
from knowledge_manager.performance_benchmarks import BenchmarkConfig, run_enterprise_benchmark


def test_benchmark_report_includes_production_release_verdict(tmp_path):
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

    assert "release_verdict" in result
    assert "required_gates" in result["release_verdict"]
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py::test_benchmark_report_includes_production_release_verdict -v`

Expected: `FAIL` because release verdict is not yet part of the benchmark output.

- [ ] **Step 3: Add a production release verdict layer**

```python
def _evaluate_release_verdict(report: dict[str, Any]) -> dict[str, Any]:
    required = ["search_http", "recommendations_http", "admin_dashboard_http", "module_crud_http", "mcp_search_modules"]
    gate_summary = report.get("gate_summary", {})
    failed = [name for name in required if gate_summary.get(name, {}).get("status") != "pass"]
    return {
        "required_gates": required,
        "failed_gates": failed,
        "ready_for_production": len(failed) == 0,
    }
```

- [ ] **Step 4: Publish the rollout and rollback checklist**

```markdown
# Production Release Checklist

## Pre-Release Evidence
- full targeted pytest suite green
- remediated benchmark matrix generated
- all required benchmark gates pass
- `/api/ready` returns 200
- integrity check returns zero blocking issues

## Rollback Triggers
- any required gate flips from pass to fail
- upload jobs accumulate in failed state for 3 consecutive production runs
- cross-tenant leakage bug
- integrity check reports missing module/index drift after rollout
```

- [ ] **Step 5: Run the benchmark contract suite and the full remediated matrix**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py -v`

Run:

```powershell
$env:PYTHONPATH='D:\tyh\knowledge-manager\src'
@'
from pathlib import Path
from knowledge_manager.performance_benchmarks import BenchmarkConfig, run_enterprise_benchmark

root = Path(r"D:\tyh\knowledge-manager\test-results\perf-run-production-gate")
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

Expected: benchmark tests `PASS`, and the produced matrix shows `release_verdict.ready_for_production == true` before the system is declared production-grade.

- [ ] **Step 6: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\performance_benchmarks.py D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md D:\tyh\knowledge-manager\docs\runbooks\enterprise-performance-test-plan.md
git commit -m "docs: add production release evidence and rollback checklist"
```

## Completion Criteria

- `search_http`, `mcp_search_modules`, `recommendations_http`, `admin_dashboard_http`, and `module_crud_http` all pass the production gates at `m` scale.
- `/api/upload` no longer performs extraction inline and returns an accepted job response.
- Source sync work has an executable local background worker seam instead of only synchronous operator-driven execution.
- The service exposes readiness and metrics endpoints distinct from knowledge-quality health.
- Operators can run an integrity check and a repair-oriented release checklist before rollout.
- Benchmark output contains both `gate_summary` and `release_verdict`, and a fresh remediated benchmark run proves the system is ready before it is called production-grade.
