# Enterprise Measured Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert `knowledge-manager` from a feature-rich but partially read-path-bound system into a measured, enterprise-grade, production-grade, industrial-grade replacement candidate for classic RAG, pageindex, and llm-wiki.

**Architecture:** Build on the optimizations already started in `module_cache.py` and `lexical_index.py`, then remove the remaining high-amplification paths in descending business impact order: materialize expensive control-plane views, replace full write-time rebuilds with incremental index maintenance, repair broken MCP/provider paths, shift slow provider-backed ingestion into durable jobs, and close the loop with retrieval-quality proof plus repeatable benchmark gates. The implementation keeps the current inspectable file-based architecture, but adds explicit runtime contracts, snapshot files, and bounded async workflows so the system scales without becoming operationally opaque.

**Tech Stack:** Python 3.10+, FastAPI, FastMCP, pytest, JSON/JSONL storage, in-process caches, persistent lexical metadata, existing ingestion job framework, optional provider-backed LLM flows.

---

## Real Findings This Plan Responds To

From the real benchmark evidence already produced on 2026-06-12:

- `POST /api/search` rose from `1556.7 ms` mean at `100` modules to `21521.866 ms` mean at `500` modules.
- `GET /api/recommendations` reached `27445.249 ms` mean and `55633.758 ms` p95 at `500` modules.
- `GET /api/admin/dashboard` reached `5280.536 ms` mean at `500` modules.
- `POST /api/chat` with a real provider took `27960.454 ms`.
- `POST /api/upload` with a real provider took `17006.948 ms`.
- MCP `research` is functionally broken with `name '_load_config_safe' is not defined`.
- Federated search is acceptable relative to core search, so federation is not the first bottleneck.

## Enterprise Gates This Plan Must Hit

- `search_http` mean `<= 1500 ms` and p95 `<= 2500 ms` at `500` modules.
- `recommendations_http` mean `<= 1200 ms` and p95 `<= 2500 ms` at `500` modules.
- `admin_dashboard_http` mean `<= 800 ms` at `500` modules.
- `module_crud_http` mean `<= 400 ms` at `500` modules.
- `mcp_search_modules` mean `<= 1500 ms` at `500` modules.
- `POST /api/chat` first-byte or first-answer stage `<= 5000 ms` when provider is enabled and retrieval already has candidates.
- `POST /api/upload` synchronous request time `<= 1500 ms`; long extraction must continue as a job.
- MCP `research` must succeed or return a bounded, typed fallback error instead of throwing.

## File Structure

### Existing files to extend

- `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
  Responsibility: module mutation paths, search, health, recommendations, ops report, invalidation hooks.
- `D:\tyh\knowledge-manager\src\knowledge_manager\lexical_index.py`
  Responsibility: persistent lexical index and candidate lookup.
- `D:\tyh\knowledge-manager\src\knowledge_manager\admin_views.py`
  Responsibility: enterprise dashboard aggregation.
- `D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py`
  Responsibility: search, health, recommendations, ops, upload, chat endpoints.
- `D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py`
  Responsibility: MCP read paths, `research`, federated tool behavior.
- `D:\tyh\knowledge-manager\src\knowledge_manager\chat.py`
  Responsibility: provider-backed chat orchestration and retrieval fan-out.
- `D:\tyh\knowledge-manager\src\knowledge_manager\extractor.py`
  Responsibility: file extraction, chunking, provider-backed staging latency.
- `D:\tyh\knowledge-manager\src\knowledge_manager\ingestion_jobs.py`
  Responsibility: durable job lifecycle for ingestion and long-running extraction.
- `D:\tyh\knowledge-manager\src\knowledge_manager\source_ingestion.py`
  Responsibility: source pull orchestration and staging workflow.
- `D:\tyh\knowledge-manager\src\knowledge_manager\retrieval_eval.py`
  Responsibility: ranking metrics and retrieval quality evidence.
- `D:\tyh\knowledge-manager\src\knowledge_manager\vector_index.py`
  Responsibility: semantic fallback support for hybrid retrieval.
- `D:\tyh\knowledge-manager\src\knowledge_manager\performance_benchmarks.py`
  Responsibility: repeatable enterprise benchmark matrix and regression gate.
- `D:\tyh\knowledge-manager\src\knowledge_manager\tenancy.py`
  Responsibility: tenant-scoped visibility and isolation rules.
- `D:\tyh\knowledge-manager\src\knowledge_manager\rbac.py`
  Responsibility: policy inheritance and effective access checks.
- `D:\tyh\knowledge-manager\tests\test_storage.py`
- `D:\tyh\knowledge-manager\tests\test_http_server.py`
- `D:\tyh\knowledge-manager\tests\test_mcp_server.py`
- `D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py`
- `D:\tyh\knowledge-manager\tests\test_retrieval_eval.py`
- `D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py`
- `D:\tyh\knowledge-manager\tests\test_tenancy.py`

### New files to create

- `D:\tyh\knowledge-manager\src\knowledge_manager\materialized_views.py`
  Responsibility: snapshot build/load/store/invalidate logic for health, recommendations, ops, and admin views.
- `D:\tyh\knowledge-manager\tests\test_materialized_views.py`
  Responsibility: snapshot freshness, invalidation, and response contract coverage.
- `D:\tyh\knowledge-manager\docs\runbooks\enterprise-rollout-and-slo.md`
  Responsibility: SLOs, regression gates, rollback triggers, rollout checklist.

## Delivery Stages

1. Eliminate the remaining full-scan control-plane bottlenecks
2. Remove write-path rebuild amplification
3. Repair broken MCP/provider flows and bound latency
4. Convert long-running ingestion into durable background jobs
5. Prove retrieval quality and enterprise isolation
6. Lock performance with benchmark gates and rollout procedure

### Task 1: Materialize Health, Recommendations, Ops, And Dashboard Views

**Files:**
- Create: `D:\tyh\knowledge-manager\src\knowledge_manager\materialized_views.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\admin_views.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_storage.py`
- Create: `D:\tyh\knowledge-manager\tests\test_materialized_views.py`

- [ ] **Step 1: Write the failing snapshot freshness tests**

```python
def test_health_report_reuses_snapshot_until_module_changes(tmp_path):
    from knowledge_manager.materialized_views import load_materialized_view
    from knowledge_manager.storage import generate_health_report, save_index, save_module
    from knowledge_manager.schemas import Index, Module, ModuleContent

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="health snapshot"), kb)
    save_module(
        Module(
            id="ops-health",
            category="ops",
            title="Ops Health",
            summary="Ops health summary.",
            content=ModuleContent(overview="healthy", details="detailed healthy module"),
        ),
        kb,
    )

    first = generate_health_report(kb)
    second = generate_health_report(kb)
    snapshot = load_materialized_view(kb, "health")

    assert first == second
    assert snapshot is not None


def test_recommendations_snapshot_invalidates_after_save(tmp_path):
    from knowledge_manager.storage import generate_recommendations, save_index, save_module
    from knowledge_manager.schemas import Index, Module, ModuleContent

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="recommend snapshot"), kb)

    base = Module(
        id="incident-core",
        category="ops",
        title="Incident Core",
        summary="incident summary",
        content=ModuleContent(overview="rollback alert", details="incident response details"),
    )
    save_module(base, kb)
    before = generate_recommendations(kb)

    save_module(
        Module(
            id="incident-links",
            category="ops",
            title="Incident Links",
            summary="incident link summary",
            content=ModuleContent(overview="rollback alert", details="incident response companion"),
        ),
        kb,
    )
    after = generate_recommendations(kb)

    assert before != after
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_materialized_views.py -v`

Expected: `FAIL` because `materialized_views.py` does not exist and the reports are recomputed inline.

- [ ] **Step 3: Implement snapshot storage and freshness checks**

```python
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class MaterializedView:
    name: str
    fingerprint: tuple[int, int]
    generated_at: str
    payload: dict[str, Any]


def materialized_fingerprint(kb_path: Path) -> tuple[int, int]:
    files = [p for p in kb_path.rglob("*.json") if ".snapshot." not in p.name]
    return len(files), sum(int(p.stat().st_mtime_ns) for p in files)


def store_materialized_view(kb_path: Path, name: str, payload: dict[str, Any]) -> dict[str, Any]:
    view = MaterializedView(
        name=name,
        fingerprint=materialized_fingerprint(kb_path),
        generated_at=datetime.now(timezone.utc).isoformat(),
        payload=payload,
    )
    _view_path(kb_path, name).write_text(json.dumps(asdict(view), ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
```

- [ ] **Step 4: Route report builders through snapshot reuse and mutation invalidation**

```python
def generate_health_report(kb_path: Path) -> Any:
    cached = load_fresh_materialized_view(kb_path, "health")
    if cached is not None:
        return cached
    report = _generate_health_report_uncached(kb_path)
    return store_materialized_view(kb_path, "health", report)


def invalidate_materialized_views(kb_path: Path, names: list[str] | None = None) -> None:
    targets = names or ["health", "recommendations", "ops", "admin_dashboard"]
    for name in targets:
        path = _view_path(kb_path, name)
        if path.exists():
            path.unlink()
```

```python
def save_module(module: Module, kb_path: Path) -> None:
    ...
    invalidate_materialized_views(kb_path)


def delete_module(module_id: str, category: str, kb_path: Path) -> bool:
    ...
    invalidate_materialized_views(kb_path)
```

- [ ] **Step 5: Add dashboard snapshot coverage**

```python
def build_admin_dashboard(kb_path: Path) -> dict[str, Any]:
    cached = load_fresh_materialized_view(kb_path, "admin_dashboard")
    if cached is not None:
        return cached
    payload = {
        "ingestion_jobs": [job.model_dump(mode="json") for job in list_ingestion_jobs(kb_path)],
        "stale_sources": generate_source_backlog_export(kb_path).get("items", []),
        "review_backlog": generate_review_backlog_export(kb_path).get("items", []),
        "eval_regressions": [],
    }
    return store_materialized_view(kb_path, "admin_dashboard", payload)
```

- [ ] **Step 6: Run the focused tests to verify they pass**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_materialized_views.py D:\tyh\knowledge-manager\tests\test_storage.py -k "snapshot or health or recommendations or ops" -v`

Expected: snapshot-focused tests `PASS`.

- [ ] **Step 7: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\materialized_views.py D:\tyh\knowledge-manager\src\knowledge_manager\storage.py D:\tyh\knowledge-manager\src\knowledge_manager\admin_views.py D:\tyh\knowledge-manager\tests\test_materialized_views.py D:\tyh\knowledge-manager\tests\test_storage.py
git commit -m "feat: materialize expensive control-plane views"
```

### Task 2: Replace Full Lexical Rebuilds On Every Write With Incremental Index Maintenance

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\lexical_index.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_lexical_index.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_storage.py`

- [ ] **Step 1: Write the failing incremental update tests**

```python
def test_incremental_lexical_update_adds_only_changed_module(tmp_path):
    from knowledge_manager.lexical_index import build_lexical_index, load_lexical_index, update_lexical_index_for_module
    from knowledge_manager.schemas import Index, Module, ModuleContent
    from knowledge_manager.storage import save_index, save_module

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="incremental lexical"), kb)
    first = Module(
        id="rollback-guide",
        category="ops",
        title="Rollback Guide",
        summary="rollback summary",
        content=ModuleContent(overview="rollback safely", details="incident rollback details"),
    )
    save_module(first, kb)
    build_lexical_index(kb)

    second = Module(
        id="tenant-policy",
        category="policy",
        title="Tenant Policy",
        summary="tenant summary",
        content=ModuleContent(overview="tenant isolation", details="policy details"),
    )
    update_lexical_index_for_module(kb, second)
    index_data = load_lexical_index(kb)

    assert "policy/tenant-policy" in index_data["terms"]["tenant"]


def test_incremental_lexical_delete_removes_module_key(tmp_path):
    from knowledge_manager.lexical_index import build_lexical_index, delete_lexical_index_for_module, load_lexical_index
    ...
    assert "ops/rollback-guide" not in load_lexical_index(kb)["terms"].get("rollback", [])
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_lexical_index.py -k "incremental" -v`

Expected: `FAIL` because only full rebuild behavior exists.

- [ ] **Step 3: Extend the lexical index format with per-module term ownership**

```python
def build_lexical_index(kb_path: Path) -> dict[str, Any]:
    terms: dict[str, list[str]] = {}
    module_terms: dict[str, list[str]] = {}
    for module in list_modules(kb_path):
        module_key = f"{module.category}/{module.id}"
        tokens = sorted(_module_terms(module))
        module_terms[module_key] = tokens
        for token in tokens:
            terms.setdefault(token, []).append(module_key)
    payload = {"terms": terms, "module_terms": module_terms}
    _write_index_payload(kb_path, payload)
    return payload
```

- [ ] **Step 4: Add targeted add/update/delete helpers and call them from mutation paths**

```python
def update_lexical_index_for_module(kb_path: Path, module: Module) -> None:
    payload = load_lexical_index(kb_path) or {"terms": {}, "module_terms": {}}
    module_key = f"{module.category}/{module.id}"
    _remove_module_terms(payload, module_key)
    tokens = sorted(_module_terms(module))
    payload["module_terms"][module_key] = tokens
    for token in tokens:
        payload["terms"].setdefault(token, []).append(module_key)
    _write_index_payload(kb_path, payload)


def delete_lexical_index_for_module(kb_path: Path, module_key: str) -> None:
    payload = load_lexical_index(kb_path)
    if not payload:
        return
    _remove_module_terms(payload, module_key)
    _write_index_payload(kb_path, payload)
```

```python
def save_module(module: Module, kb_path: Path) -> None:
    ...
    update_lexical_index_for_module(kb_path, module)


def delete_module(module_id: str, category: str, kb_path: Path) -> bool:
    ...
    delete_lexical_index_for_module(kb_path, f"{category}/{module_id}")
```

- [ ] **Step 5: Run focused tests plus search regressions**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_lexical_index.py D:\tyh\knowledge-manager\tests\test_storage.py -k "incremental or lexical or search" -v`

Expected: incremental lexical tests and existing search tests `PASS`.

- [ ] **Step 6: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\lexical_index.py D:\tyh\knowledge-manager\src\knowledge_manager\storage.py D:\tyh\knowledge-manager\tests\test_lexical_index.py D:\tyh\knowledge-manager\tests\test_storage.py
git commit -m "feat: add incremental lexical index maintenance"
```

### Task 3: Repair MCP `research` And Bound Provider-Backed Latency Paths

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\chat.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\extractor.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_mcp_server.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_http_server.py`

- [ ] **Step 1: Write the failing MCP research regression and provider budget tests**

```python
def test_research_tool_returns_structured_result_instead_of_name_error(tmp_path):
    from knowledge_manager.mcp_server import create_server

    server = create_server(tmp_path)
    result = server.call_tool("research", {"query": "rollback governance", "depth": "shallow"})

    assert "temporary_answer" in str(result) or "error" in str(result)
    assert "_load_config_safe" not in str(result)


def test_chat_endpoint_returns_budgeted_timeout_payload(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from knowledge_manager.http_server import create_app

    monkeypatch.setattr("knowledge_manager.chat.run_chat", lambda *args, **kwargs: {"status": "deferred", "job_id": "chat-1"})
    client = TestClient(create_app(tmp_path))
    response = client.post("/api/chat", json={"query": "large question"})

    assert response.status_code == 200
    assert response.json()["status"] in {"ok", "deferred"}
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_mcp_server.py D:\tyh\knowledge-manager\tests\test_http_server.py -k "research or budgeted_timeout_payload" -v`

Expected: `FAIL` because `research` is broken and provider-path fallback contracts are incomplete.

- [ ] **Step 3: Repair config loading and return typed research failures**

```python
def _load_config_safe(kb_path: Path) -> Config:
    try:
        return load_config(kb_path)
    except Exception:
        return Config()


@mcp.tool(name="research")
def research_tool(query: str, depth: str = "shallow") -> str:
    cfg = _load_config_safe(kb_path)
    if not cfg.research.enabled:
        return json.dumps({"status": "disabled", "temporary_answer": "", "staged_modules": []}, ensure_ascii=False)
    ...
```

- [ ] **Step 4: Bound synchronous provider work in chat and upload**

```python
def run_chat(..., max_sync_seconds: float = 5.0) -> dict[str, Any]:
    started = time.perf_counter()
    candidates = search_modules(query, kb_path, limit=8)
    if time.perf_counter() - started > max_sync_seconds:
        return {"status": "deferred", "job_id": "", "results": [r.module.id for r in candidates]}
    ...
```

```python
@app.post("/api/upload")
def api_upload(...):
    job = create_ingestion_job(kb_path, source_id="upload", trigger="http-upload")
    enqueue_upload_extraction(job.job_id, ...)
    return {"status": "accepted", "job_id": job.job_id}
```

- [ ] **Step 5: Run the focused tests to verify they pass**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_mcp_server.py D:\tyh\knowledge-manager\tests\test_http_server.py -k "research or chat or upload" -v`

Expected: research regression and provider budget tests `PASS`.

- [ ] **Step 6: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py D:\tyh\knowledge-manager\src\knowledge_manager\chat.py D:\tyh\knowledge-manager\src\knowledge_manager\extractor.py D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py D:\tyh\knowledge-manager\tests\test_mcp_server.py D:\tyh\knowledge-manager\tests\test_http_server.py
git commit -m "fix: bound provider latency and repair mcp research"
```

### Task 4: Move Upload Extraction And Source Pull To Durable Background Jobs

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\ingestion_jobs.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\source_ingestion.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\cli.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_http_server.py`

- [ ] **Step 1: Write the failing upload-job lifecycle tests**

```python
def test_upload_job_records_extraction_progress_and_completion(tmp_path):
    from knowledge_manager.ingestion_jobs import create_ingestion_job, update_ingestion_checkpoint, complete_ingestion_job

    kb = tmp_path / "kb"
    kb.mkdir()
    job = create_ingestion_job(kb, source_id="upload", trigger="http-upload")
    update_ingestion_checkpoint(kb, job.job_id, cursor="chunk-3", pages_seen=0, modules_staged=2)
    done = complete_ingestion_job(kb, job.job_id, pages_seen=1, modules_staged=4)

    assert done.status == "completed"
    assert done.modules_staged == 4


def test_upload_endpoint_returns_accepted_job_id(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from knowledge_manager.http_server import create_app

    monkeypatch.setattr("knowledge_manager.http_server._start_upload_job", lambda *args, **kwargs: "job-123")
    client = TestClient(create_app(tmp_path))
    response = client.post("/api/upload", files={"file": ("demo.md", b"# title", "text/markdown")})

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert response.json()["job_id"] == "job-123"
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py D:\tyh\knowledge-manager\tests\test_http_server.py -k "upload_job or accepted_job_id" -v`

Expected: `FAIL` because upload currently performs heavy work inline.

- [ ] **Step 3: Extend the job model for extraction/source pull phases**

```python
class IngestionJob(BaseModel):
    job_id: str
    source_id: str
    trigger: str
    status: str = "queued"
    stage: str = "queued"
    cursor: str = ""
    pages_seen: int = 0
    modules_staged: int = 0
    error: str = ""
```

- [ ] **Step 4: Add non-blocking upload and resumable source-pull orchestration**

```python
def _start_upload_job(kb_path: Path, filename: str, payload: bytes) -> str:
    job = create_ingestion_job(kb_path, source_id="upload", trigger="http-upload")
    _run_upload_job_async(kb_path, job.job_id, filename, payload)
    return job.job_id
```

```python
def pull_source_as_job(kb_path: Path, source_id: str) -> IngestionJob:
    job = create_ingestion_job(kb_path, source_id=source_id, trigger="source-sync")
    claim_ingestion_job(kb_path, job.job_id, worker_id="source-pull")
    return job
```

- [ ] **Step 5: Run focused tests**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py D:\tyh\knowledge-manager\tests\test_http_server.py -k "upload or source_pull or ingestion_job" -v`

Expected: upload and job lifecycle tests `PASS`.

- [ ] **Step 6: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\ingestion_jobs.py D:\tyh\knowledge-manager\src\knowledge_manager\source_ingestion.py D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py D:\tyh\knowledge-manager\src\knowledge_manager\cli.py D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py D:\tyh\knowledge-manager\tests\test_http_server.py
git commit -m "feat: move upload and source pull to durable jobs"
```

### Task 5: Prove Retrieval Superiority With Hybrid Ranking And Measured Eval Gates

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\retrieval_eval.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\eval_runner.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\vector_index.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_retrieval_eval.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_storage.py`

- [ ] **Step 1: Write the failing hybrid-quality tests**

```python
def test_eval_summary_reports_mrr_ndcg_and_recall_budget():
    from knowledge_manager.retrieval_eval import score_ranked_case

    summary = score_ranked_case(
        required_modules=["ops/rollback-guide", "policy/tenant-policy"],
        found_modules=["ops/rollback-guide", "auth/jwt", "policy/tenant-policy"],
    )

    assert round(summary.mrr, 3) == 1.0
    assert summary.ndcg_at_k > 0.9
    assert round(summary.recall_at_k, 3) == 1.0


def test_hybrid_search_can_promote_vector_only_candidate_without_breaking_policy(tmp_path, monkeypatch):
    ...
    assert results[0].module.id == "legacy-acronym"
```

- [ ] **Step 2: Run the focused tests to verify they fail where behavior is missing**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_retrieval_eval.py D:\tyh\knowledge-manager\tests\test_storage.py -k "hybrid or mrr or ndcg or recall" -v`

Expected: `FAIL` if hybrid ranking or metrics export is incomplete.

- [ ] **Step 3: Extend ranking evidence and hybrid merge logic**

```python
class RankedCaseSummary(BaseModel):
    first_hit_rank: int | None = None
    mrr: float = 0.0
    ndcg_at_k: float = 0.0
    recall_at_k: float = 0.0
    matched_modules: list[str] = []
```

```python
def _merge_hybrid_results(...):
    ...
    merged[module_key] = SearchResult(module, "vector_fallback", [f"vector_support:{round(score, 3)}"])
    return _rank_search_results(merged)
```

- [ ] **Step 4: Export eval budgets from `eval_runner.py`**

```python
def evaluate_retrieval_budget(...) -> dict[str, Any]:
    return {
        "mrr_floor": 0.75,
        "ndcg_floor": 0.7,
        "recall_floor": 0.85,
        "actual": aggregate_summary.model_dump(),
        "pass": aggregate_summary.mrr >= 0.75 and aggregate_summary.ndcg_at_k >= 0.7,
    }
```

- [ ] **Step 5: Run focused tests**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_retrieval_eval.py D:\tyh\knowledge-manager\tests\test_storage.py -k "hybrid or retrieval_budget or mrr or ndcg" -v`

Expected: retrieval-quality tests `PASS`.

- [ ] **Step 6: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\retrieval_eval.py D:\tyh\knowledge-manager\src\knowledge_manager\eval_runner.py D:\tyh\knowledge-manager\src\knowledge_manager\storage.py D:\tyh\knowledge-manager\src\knowledge_manager\vector_index.py D:\tyh\knowledge-manager\tests\test_retrieval_eval.py D:\tyh\knowledge-manager\tests\test_storage.py
git commit -m "feat: add enterprise retrieval quality gates"
```

### Task 6: Close Enterprise Isolation And Access-Control Gaps

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\tenancy.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\rbac.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_tenancy.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_http_server.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_mcp_server.py`

- [ ] **Step 1: Write the failing tenant-boundary tests**

```python
def test_http_search_excludes_other_tenant_modules(tmp_path):
    ...
    assert all(item["tenant_id"] == "tenant-a" for item in response.json()["results"])


def test_mcp_load_module_rejects_cross_tenant_access(tmp_path):
    ...
    assert "forbidden" in str(result).lower()
```

- [ ] **Step 2: Run the focused tests to verify they fail where isolation is incomplete**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_tenancy.py D:\tyh\knowledge-manager\tests\test_http_server.py D:\tyh\knowledge-manager\tests\test_mcp_server.py -k "tenant or cross_tenant or forbidden" -v`

Expected: `FAIL` if any surface leaks cross-tenant visibility.

- [ ] **Step 3: Centralize effective access resolution**

```python
def can_access_module(module: Module, tenant: TenantContext | None, groups: list[str] | None = None) -> bool:
    if not module_visible_to_tenant(module, tenant):
        return False
    return evaluate_group_access(module, groups or [])
```

- [ ] **Step 4: Apply the same access contract to HTTP and MCP**

```python
results = [
    r for r in search_modules(query, kb_path, tenant=tenant_ctx, limit=limit)
    if can_access_module(r.module, tenant_ctx, groups)
]
```

```python
module = load_module(module_id, category, target_kb)
if module is None or not can_access_module(module, tenant_ctx, groups):
    return json.dumps({"error": "forbidden"}, ensure_ascii=False)
```

- [ ] **Step 5: Run focused tests**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_tenancy.py D:\tyh\knowledge-manager\tests\test_http_server.py D:\tyh\knowledge-manager\tests\test_mcp_server.py -k "tenant or forbidden or access" -v`

Expected: tenant isolation tests `PASS`.

- [ ] **Step 6: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\tenancy.py D:\tyh\knowledge-manager\src\knowledge_manager\rbac.py D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py D:\tyh\knowledge-manager\tests\test_tenancy.py D:\tyh\knowledge-manager\tests\test_http_server.py D:\tyh\knowledge-manager\tests\test_mcp_server.py
git commit -m "fix: enforce tenant-safe access across http and mcp"
```

### Task 7: Lock The System With Benchmark Gates, Soak Runs, And Rollout Runbooks

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\performance_benchmarks.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py`
- Create: `D:\tyh\knowledge-manager\docs\runbooks\enterprise-rollout-and-slo.md`

- [ ] **Step 1: Write the failing benchmark gate test**

```python
def test_benchmark_summary_exposes_enterprise_gate_verdict(tmp_path):
    from knowledge_manager.performance_benchmarks import BenchmarkConfig, run_enterprise_benchmark

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

    assert "gate_summary" in result
    assert "search_http" in result["gate_summary"]
```

- [ ] **Step 2: Run the focused test to verify it fails if gate summary is missing**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py::test_benchmark_summary_exposes_enterprise_gate_verdict -v`

Expected: `FAIL` if no explicit enterprise verdict is produced.

- [ ] **Step 3: Add gate evaluation to benchmark output**

```python
def _evaluate_gate_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "search_http": {"target_mean_ms": 1500, "actual_mean_ms": report["benchmarks"]["http"]["search_http"]["mean_ms"]},
        "recommendations_http": {"target_mean_ms": 1200, "actual_mean_ms": report["benchmarks"]["http"]["recommendations_http"]["mean_ms"]},
        "admin_dashboard_http": {"target_mean_ms": 800, "actual_mean_ms": report["benchmarks"]["http"]["admin_dashboard_http"]["mean_ms"]},
    }
```

- [ ] **Step 4: Publish the rollout and rollback runbook**

```markdown
# Enterprise Rollout And SLO Runbook

## SLOs
- Search mean <= 1500 ms at 500 modules
- Recommendations mean <= 1200 ms at 500 modules
- Upload request <= 1500 ms with async extraction

## Rollback Triggers
- Any gate regression above 20 percent on two consecutive runs
- MCP research runtime failure
- Cross-tenant access regression
```

- [ ] **Step 5: Run the benchmark contract tests and one real benchmark sweep**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py -v`

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m knowledge_manager.performance_benchmarks --kb-path D:\tyh\knowledge-manager\.tmp-perf-kb --output-dir D:\tyh\knowledge-manager\test-results\perf-run-20260612-remediated --scales xs,s,m`

Expected: test suite `PASS` and a new benchmark report with explicit pass/fail gates.

- [ ] **Step 6: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\performance_benchmarks.py D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py D:\tyh\knowledge-manager\docs\runbooks\enterprise-rollout-and-slo.md
git commit -m "docs: add enterprise benchmark gates and rollout runbook"
```

## Completion Criteria

- Control-plane endpoints read from materialized snapshots instead of recomputing full scans on every request.
- `save_module` and `delete_module` no longer trigger full lexical rebuilds in the hot path.
- MCP `research` no longer crashes at runtime.
- `/api/upload` becomes an accept-and-process workflow instead of a long blocking request.
- Retrieval quality is measured with ranking metrics, not only latency.
- Tenant and access boundaries are enforced consistently across HTTP and MCP.
- Benchmark output contains enterprise gate verdicts and a new remediated benchmark run proves improvement against the 2026-06-12 baseline.
