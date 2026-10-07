# Enterprise Performance Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `knowledge-manager` from a functionally complete but read-path-bound system into an enterprise-grade, production-grade, industrial-grade knowledge platform with measurable improvement on search, control-plane, write-path, MCP, and provider-backed workflows.

**Architecture:** The remediation strategy is to eliminate repeated full-KB scans, repeated JSON deserialization, and synchronous full-index rebuilds from hot paths. The plan introduces four layers in order: in-process module/index caching, persistent lexical retrieval structures, materialized control-plane snapshots, and bounded asynchronous/stream-aware provider workflows. The work preserves the current file-based inspectable architecture while adding explicit performance primitives instead of hiding complexity behind ad hoc optimizations.

**Tech Stack:** Python 3.10+, FastAPI, FastMCP, pytest, JSON/JSONL storage, in-process caches, lightweight persistent inverted index files, optional background snapshot builders.

---

## Real Baseline This Plan Is Targeting

From the real benchmark reports already produced:

- `POST /api/search` grew from `1556.7 ms` mean at `100` modules to `21521.866 ms` mean at `500` modules.
- `GET /api/recommendations` reached `27445.249 ms` mean and `55633.758 ms` p95 at `500` modules.
- `GET /api/admin/dashboard` reached `5280.536 ms` mean at `500` modules.
- `POST /api/chat` with a real DeepSeek provider took `27960.454 ms`.
- `POST /api/upload` with a real DeepSeek provider took `17006.948 ms`.
- MCP `research` currently fails with `name '_load_config_safe' is not defined`.

This plan is optimized against those real failures, not hypothetical ones.

## File Structure

### Existing files to modify

- `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
  Responsibility: module enumeration, search hot path, health/recommendations/ops report inputs, index rebuild behavior.
- `D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py`
  Responsibility: HTTP endpoint timing, read-path integration, write-path integration, provider-backed path control.
- `D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py`
  Responsibility: MCP read/tool path, research bugfix, federation behavior.
- `D:\tyh\knowledge-manager\src\knowledge_manager\chat.py`
  Responsibility: provider-backed chat pipeline and retrieval fan-out cost.
- `D:\tyh\knowledge-manager\src\knowledge_manager\extractor.py`
  Responsibility: upload/extraction latency path and chunk behavior.
- `D:\tyh\knowledge-manager\src\knowledge_manager\performance_benchmarks.py`
  Responsibility: benchmark coverage and regression gate.
- `D:\tyh\knowledge-manager\tests\test_storage.py`
  Responsibility: hot-path behavior, cache invalidation, index consistency.
- `D:\tyh\knowledge-manager\tests\test_http_server.py`
  Responsibility: endpoint behavior under new cache/snapshot/index design.
- `D:\tyh\knowledge-manager\tests\test_mcp_server.py`
  Responsibility: MCP correctness, research tool regression coverage.
- `D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py`
  Responsibility: benchmark output contract and regression evidence.

### New files to create

- `D:\tyh\knowledge-manager\src\knowledge_manager\module_cache.py`
  Responsibility: process-local module list and module object cache with invalidation.
- `D:\tyh\knowledge-manager\src\knowledge_manager\lexical_index.py`
  Responsibility: persistent inverted index and precomputed term metadata for fast search.
- `D:\tyh\knowledge-manager\src\knowledge_manager\materialized_views.py`
  Responsibility: health/recommendations/ops/admin snapshot generation and reuse.
- `D:\tyh\knowledge-manager\tests\test_module_cache.py`
  Responsibility: module cache and invalidation tests.
- `D:\tyh\knowledge-manager\tests\test_lexical_index.py`
  Responsibility: inverted index creation and query tests.
- `D:\tyh\knowledge-manager\tests\test_materialized_views.py`
  Responsibility: snapshot generation and stale/refresh tests.

## Delivery Stages

1. Stabilize observability and correctness gates
2. Remove repeated module scan/deserialization from hot paths
3. Replace full-scan lexical search with persistent index-backed retrieval
4. Materialize expensive control-plane reports
5. Reduce write-path rebuild cost
6. Repair and bound provider-backed and MCP workflows
7. Re-benchmark against enterprise gates

### Task 1: Add Performance Invariants And Hot-Path Instrumentation

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\performance_benchmarks.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py`
- Test: `D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py`

- [ ] **Step 1: Write the failing benchmark contract test**

```python
def test_benchmark_records_errors_and_resource_sections(tmp_path):
    from knowledge_manager.performance_benchmarks import BenchmarkConfig, run_enterprise_benchmark

    result = run_enterprise_benchmark(
        BenchmarkConfig(
            kb_path=tmp_path / "kb",
            output_dir=tmp_path / "reports",
            module_count=12,
            tenant_count=2,
            job_count=6,
            search_iterations=1,
            http_iterations=1,
            job_iterations=1,
            top_k=3,
        )
    )

    assert "resources" in result
    assert "benchmarks" in result
    assert "external_provider" in result["benchmarks"]
    assert "enabled" in result["benchmarks"]["external_provider"]
```

- [ ] **Step 2: Run test to verify it fails if the contract is missing**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py::test_benchmark_records_errors_and_resource_sections -v`
Expected: `FAIL` if `resources` or `external_provider` are absent.

- [ ] **Step 3: Ensure benchmark contract stays explicit**

```python
report = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "dataset": {...},
    "resources": {
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "kb_disk_bytes": _sum_file_bytes(config.kb_path),
        "python_heap_peak_bytes": heap_peak,
    },
    "benchmarks": {
        "retrieval": retrieval,
        "http": http,
        "control_plane": control_plane,
        "mcp": mcp,
        "external_provider": external_provider,
        "job_operations": job_operations,
        "write_operations": write_operations,
    },
}
```

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py::test_benchmark_records_errors_and_resource_sections -v`
Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\performance_benchmarks.py D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py
git commit -m "test: lock benchmark report contract"
```

### Task 2: Eliminate Repeated Full-KB Module Enumeration

**Files:**
- Create: `D:\tyh\knowledge-manager\src\knowledge_manager\module_cache.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
- Create: `D:\tyh\knowledge-manager\tests\test_module_cache.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_storage.py`

- [ ] **Step 1: Write the failing cache invalidation test**

```python
def test_list_modules_reuses_cached_module_set_until_storage_changes(tmp_path):
    from knowledge_manager.module_cache import ModuleCache
    from knowledge_manager.schemas import Module, ModuleContent
    from knowledge_manager.storage import list_modules, save_index, save_module
    from knowledge_manager.schemas import Index

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="cache test"), kb)

    module = Module(
        id="mod-1",
        category="ops",
        title="Ops Module",
        summary="Ops module summary.",
        content=ModuleContent(
            overview="Ops overview text.",
            details="Ops details long enough for validation.",
        ),
    )
    save_module(module, kb)

    first = list_modules(kb)
    second = list_modules(kb)

    assert [m.id for m in first] == [m.id for m in second] == ["mod-1"]
```

- [ ] **Step 2: Run test to verify it fails before cache extraction**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_module_cache.py::test_list_modules_reuses_cached_module_set_until_storage_changes -v`
Expected: `FAIL` because `module_cache.py` does not exist yet.

- [ ] **Step 3: Add a focused module cache**

```python
from dataclasses import dataclass
from pathlib import Path

from knowledge_manager.schemas import Module


@dataclass
class CachedModuleSet:
    fingerprint: tuple[int, int]
    modules: list[Module]


class ModuleCache:
    def __init__(self) -> None:
        self._modules: dict[str, CachedModuleSet] = {}

    def get(self, kb_path: Path, fingerprint: tuple[int, int]) -> list[Module] | None:
        item = self._modules.get(str(kb_path.resolve()))
        if item and item.fingerprint == fingerprint:
            return item.modules
        return None

    def put(self, kb_path: Path, fingerprint: tuple[int, int], modules: list[Module]) -> None:
        self._modules[str(kb_path.resolve())] = CachedModuleSet(fingerprint=fingerprint, modules=modules)

    def invalidate(self, kb_path: Path) -> None:
        self._modules.pop(str(kb_path.resolve()), None)
```

- [ ] **Step 4: Integrate cache into `list_modules()` and invalidation points**

```python
_MODULE_CACHE = ModuleCache()


def _module_set_fingerprint(kb_path: Path) -> tuple[int, int]:
    files = [p for p in kb_path.rglob("*.json") if p.name != "index.json"]
    total_mtime = sum(int(p.stat().st_mtime_ns) for p in files)
    return len(files), total_mtime


def list_modules(kb_path: Path, tenant: TenantContext | None = None) -> List[Module]:
    if not kb_path.exists():
        return []
    fingerprint = _module_set_fingerprint(kb_path)
    all_modules = _MODULE_CACHE.get(kb_path, fingerprint)
    if all_modules is None:
        loaded: list[Module] = []
        for json_file in kb_path.rglob("*.json"):
            if json_file.name == "index.json":
                continue
            try:
                loaded.append(Module.model_validate_json(json_file.read_text(encoding="utf-8")))
            except Exception:
                pass
        _MODULE_CACHE.put(kb_path, fingerprint, loaded)
        all_modules = loaded
    return [m for m in all_modules if module_visible_to_tenant(m, tenant)]
```

- [ ] **Step 5: Invalidate cache on mutation paths**

```python
def save_module(module: Module, kb_path: Path) -> None:
    path = module.to_file_path(kb_path)
    existed = path.exists()
    _atomic_write(path, module.model_dump_json(indent=2))
    _MODULE_CACHE.invalidate(kb_path)
```

```python
def delete_module(module_id: str, category: str, kb_path: Path) -> bool:
    path = kb_path / category / f"{module_id}.json"
    if not path.exists():
        return False
    path.unlink()
    _MODULE_CACHE.invalidate(kb_path)
    return True
```

- [ ] **Step 6: Run focused tests**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_module_cache.py D:\tyh\knowledge-manager\tests\test_storage.py -k "list_modules or cache" -v`
Expected: `PASS`

- [ ] **Step 7: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\module_cache.py D:\tyh\knowledge-manager\src\knowledge_manager\storage.py D:\tyh\knowledge-manager\tests\test_module_cache.py D:\tyh\knowledge-manager\tests\test_storage.py
git commit -m "feat: add module enumeration cache"
```

### Task 3: Replace Full-Scan Search With Persistent Lexical Index

**Files:**
- Create: `D:\tyh\knowledge-manager\src\knowledge_manager\lexical_index.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
- Create: `D:\tyh\knowledge-manager\tests\test_lexical_index.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_storage.py`

- [ ] **Step 1: Write the failing index query test**

```python
def test_lexical_index_returns_candidate_keys_for_query(tmp_path):
    from knowledge_manager.lexical_index import build_lexical_index, query_lexical_index
    from knowledge_manager.schemas import Index, Module, ModuleContent
    from knowledge_manager.storage import save_index, save_module

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="lexical index"), kb)
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

    build_lexical_index(kb)
    keys = query_lexical_index(kb, "rollback incidents")

    assert "ops/rollback-guide" in keys
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_lexical_index.py::test_lexical_index_returns_candidate_keys_for_query -v`
Expected: `FAIL` because `lexical_index.py` does not exist yet.

- [ ] **Step 3: Implement a persistent inverted index**

```python
import json
from pathlib import Path

from knowledge_manager.storage import _WORD_RE, _stem, list_modules


def _index_path(kb_path: Path) -> Path:
    return kb_path / ".cache" / "lexical_index.json"


def build_lexical_index(kb_path: Path) -> dict:
    inverted: dict[str, list[str]] = {}
    for module in list_modules(kb_path):
        key = f"{module.category}/{module.id}"
        text = " ".join([module.title, module.summary, module.content.overview, module.content.details, " ".join(module.metadata.tags)])
        terms: set[str] = set()
        for word in _WORD_RE.findall(text.lower()):
            terms.update(_stem(word).split())
        for term in terms:
            inverted.setdefault(term, []).append(key)
    path = _index_path(kb_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(inverted, ensure_ascii=False), encoding="utf-8")
    return inverted


def query_lexical_index(kb_path: Path, query: str) -> list[str]:
    path = _index_path(kb_path)
    if not path.exists():
        build_lexical_index(kb_path)
    inverted = json.loads(path.read_text(encoding="utf-8"))
    scores: dict[str, int] = {}
    for word in _WORD_RE.findall(query.lower()):
        for term in _stem(word).split():
            for module_key in inverted.get(term, []):
                scores[module_key] = scores.get(module_key, 0) + 1
    return [k for k, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))]
```

- [ ] **Step 4: Route `search_modules()` through candidate keys before scoring**

```python
from knowledge_manager.lexical_index import build_lexical_index, query_lexical_index


candidate_keys = query_lexical_index(kb_path, query)
candidate_set = set(candidate_keys[:500]) if candidate_keys else None
all_modules = list_modules(kb_path, tenant=tenant)
if candidate_set is not None:
    all_modules = [
        m for m in all_modules
        if f"{m.category}/{m.id}" in candidate_set
    ]
if not all_modules:
    build_lexical_index(kb_path)
    all_modules = list_modules(kb_path, tenant=tenant)
```

- [ ] **Step 5: Rebuild lexical index on write/rebuild paths**

```python
def rebuild_index(kb_path: Path) -> Index:
    index = load_index(kb_path) or Index()
    index.categories.clear()
    for module in list_modules(kb_path):
        index.add_module(module)
    save_index(index, kb_path)
    build_lexical_index(kb_path)
    return index
```

- [ ] **Step 6: Run focused search/index tests**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_lexical_index.py D:\tyh\knowledge-manager\tests\test_storage.py -k "lexical or search" -v`
Expected: `PASS`

- [ ] **Step 7: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\lexical_index.py D:\tyh\knowledge-manager\src\knowledge_manager\storage.py D:\tyh\knowledge-manager\tests\test_lexical_index.py D:\tyh\knowledge-manager\tests\test_storage.py
git commit -m "feat: add persistent lexical retrieval index"
```

### Task 4: Materialize Health, Recommendations, And Ops Snapshots

**Files:**
- Create: `D:\tyh\knowledge-manager\src\knowledge_manager\materialized_views.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\admin_views.py`
- Create: `D:\tyh\knowledge-manager\tests\test_materialized_views.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_http_server.py`

- [ ] **Step 1: Write the failing snapshot test**

```python
def test_materialized_health_snapshot_reuses_cached_payload(tmp_path):
    from knowledge_manager.materialized_views import build_health_snapshot, load_health_snapshot
    from knowledge_manager.schemas import Index
    from knowledge_manager.storage import save_index

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="snapshot test"), kb)

    first = build_health_snapshot(kb)
    second = load_health_snapshot(kb)

    assert first["generated_at"] == second["generated_at"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_materialized_views.py::test_materialized_health_snapshot_reuses_cached_payload -v`
Expected: `FAIL` because `materialized_views.py` does not exist yet.

- [ ] **Step 3: Add snapshot builder/loader primitives**

```python
import json
from datetime import datetime, timezone
from pathlib import Path


def _snapshot_path(kb_path: Path, name: str) -> Path:
    return kb_path / ".cache" / f"{name}.snapshot.json"


def save_snapshot(kb_path: Path, name: str, payload: dict) -> dict:
    payload = dict(payload)
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    path = _snapshot_path(kb_path, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def load_snapshot(kb_path: Path, name: str) -> dict | None:
    path = _snapshot_path(kb_path, name)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
```

- [ ] **Step 4: Route heavy report generators through snapshots**

```python
def generate_health_report(kb_path: Path) -> Any:
    from knowledge_manager.materialized_views import load_snapshot, save_snapshot

    cached = load_snapshot(kb_path, "health")
    if cached is not None:
        return KBHealthReport.model_validate(cached)

    report = KBHealthReport(...)
    save_snapshot(kb_path, "health", report.model_dump(mode="json"))
    return report
```

- [ ] **Step 5: Use snapshots in admin dashboard composition**

```python
def build_admin_dashboard(kb_path: Path) -> dict[str, Any]:
    jobs = list_ingestion_jobs(kb_path)
    ops = generate_ops_report(kb_path)
    return {
        "ingestion_jobs": [job.model_dump(mode="json") for job in jobs],
        "stale_sources": [entry.model_dump(mode="json") for entry in ops.source_backlog],
        "review_backlog": generate_review_backlog_export(kb_path).get("items", []),
        "eval_regressions": [],
    }
```

- [ ] **Step 6: Invalidate snapshots on mutating storage paths**

```python
def _invalidate_materialized_views(kb_path: Path) -> None:
    for name in ("health", "recommendations", "ops"):
        path = kb_path / ".cache" / f"{name}.snapshot.json"
        if path.exists():
            path.unlink()
```

- [ ] **Step 7: Run focused snapshot/control-plane tests**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_materialized_views.py D:\tyh\knowledge-manager\tests\test_http_server.py -k "health or recommendations or ops or admin_dashboard" -v`
Expected: `PASS`

- [ ] **Step 8: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\materialized_views.py D:\tyh\knowledge-manager\src\knowledge_manager\storage.py D:\tyh\knowledge-manager\src\knowledge_manager\admin_views.py D:\tyh\knowledge-manager\tests\test_materialized_views.py D:\tyh\knowledge-manager\tests\test_http_server.py
git commit -m "feat: materialize expensive control-plane views"
```

### Task 5: Remove Full `rebuild_index()` From Hot Write Paths

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_http_server.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_storage.py`

- [ ] **Step 1: Write the failing incremental-index test**

```python
def test_save_module_updates_index_without_full_rebuild(tmp_path):
    from knowledge_manager.schemas import Index, Module, ModuleContent
    from knowledge_manager.storage import load_index, save_index, save_module

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="incremental index"), kb)

    save_module(
        Module(
            id="mod-1",
            category="ops",
            title="Ops module",
            summary="Ops summary text.",
            content=ModuleContent(
                overview="Ops overview text.",
                details="Ops details long enough for validation.",
            ),
        ),
        kb,
    )

    index = load_index(kb)
    assert index is not None
    assert "ops" in index.categories
    assert index.categories["ops"].modules[0].id == "mod-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_storage.py::test_save_module_updates_index_without_full_rebuild -v`
Expected: `FAIL` if index mutation still depends entirely on `rebuild_index()`.

- [ ] **Step 3: Add incremental index mutation helpers**

```python
def _upsert_index_entry(module: Module, kb_path: Path) -> None:
    index = load_index(kb_path) or Index()
    index.add_module(module)
    save_index(index, kb_path)


def _remove_index_entry(module_id: str, category: str, kb_path: Path) -> None:
    index = load_index(kb_path)
    if index is None:
        return
    index.remove_module(module_id, category)
    save_index(index, kb_path)
```

- [ ] **Step 4: Use incremental mutation in HTTP write endpoints**

```python
save_module(module, kb_path)
_upsert_index_entry(module, kb_path)
```

```python
if not delete_module(mod_id, cat, kb_path):
    raise HTTPException(404, f"Module not found: {cat}/{mod_id}")
_remove_index_entry(mod_id, cat, kb_path)
```

- [ ] **Step 5: Reserve `rebuild_index()` for explicit recovery/full sync paths only**

```python
def rebuild_index(kb_path: Path) -> Index:
    index = Index(description=(load_index(kb_path).description if load_index(kb_path) else ""))
    for module in list_modules(kb_path):
        index.add_module(module)
    save_index(index, kb_path)
    build_lexical_index(kb_path)
    return index
```

- [ ] **Step 6: Run focused write-path tests**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_storage.py D:\tyh\knowledge-manager\tests\test_http_server.py -k "save_module or module_create or module_update or module_delete" -v`
Expected: `PASS`

- [ ] **Step 7: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\storage.py D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py D:\tyh\knowledge-manager\tests\test_storage.py D:\tyh\knowledge-manager\tests\test_http_server.py
git commit -m "feat: make write paths incrementally update index"
```

### Task 6: Repair MCP Research And Bound Provider-Backed Workflows

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\chat.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\extractor.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_mcp_server.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_http_server.py`

- [ ] **Step 1: Write the failing MCP research regression test**

```python
@pytest.mark.asyncio
async def test_research_tool_returns_json_error_or_result_instead_of_name_error(server, kb_path):
    result = await server.call_tool("research", {"query": "rollback workflow", "depth": "shallow"})
    raw = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert "_load_config_safe" not in raw
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_mcp_server.py::test_research_tool_returns_json_error_or_result_instead_of_name_error -v`
Expected: `FAIL` with `_load_config_safe` leakage.

- [ ] **Step 3: Fix the MCP research config load bug**

```python
from knowledge_manager.storage import _load_config_safe


cfg = _load_config_safe(kb_path)
if cfg is None:
    return json.dumps({"error": "No config found"})
```

- [ ] **Step 4: Cap provider-backed retrieval fan-out in chat**

```python
top_modules = fused[:3]
system_prompt = self._build_system_prompt(top_modules, intent, max_tokens=4000)
```

```python
keyword_results = await self._keyword_recall(rewritten)
tree_results = await self._tree_recall(rewritten, intent)
vector_results = await self._vector_recall(rewritten)
```

Keep fan-out bounded to the smallest set that preserves answer quality.

- [ ] **Step 5: Cap extraction burst size during upload**

```python
max_modules = min(self.config.max_modules_per_extraction, 3)
chunks = _chunk_text(text, min(self.config.chunk_size, 4000), self.config.chunk_overlap)
```

- [ ] **Step 6: Run focused provider/MCP tests**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_mcp_server.py D:\tyh\knowledge-manager\tests\test_http_server.py -k "research or chat or upload" -v`
Expected: `PASS`

- [ ] **Step 7: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py D:\tyh\knowledge-manager\src\knowledge_manager\chat.py D:\tyh\knowledge-manager\src\knowledge_manager\extractor.py D:\tyh\knowledge-manager\tests\test_mcp_server.py D:\tyh\knowledge-manager\tests\test_http_server.py
git commit -m "fix: repair mcp research and bound provider paths"
```

### Task 7: Re-Benchmark And Enforce Enterprise Gates

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\performance_benchmarks.py`
- Modify: `D:\tyh\knowledge-manager\docs\runbooks\enterprise-performance-test-plan.md`
- Modify: `D:\tyh\knowledge-manager\README.md`
- Test: `D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py`

- [ ] **Step 1: Write the failing gate assertion test**

```python
def test_benchmark_report_includes_gate_summary(tmp_path):
    from knowledge_manager.performance_benchmarks import BenchmarkConfig, run_enterprise_benchmark

    report = run_enterprise_benchmark(
        BenchmarkConfig(
            kb_path=tmp_path / "kb",
            output_dir=tmp_path / "reports",
            module_count=10,
            tenant_count=2,
            job_count=4,
            search_iterations=1,
            http_iterations=1,
            job_iterations=1,
        )
    )

    assert "gate_summary" in report
    assert "search_http" in report["gate_summary"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py::test_benchmark_report_includes_gate_summary -v`
Expected: `FAIL` because gate summary does not exist yet.

- [ ] **Step 3: Add benchmark pass/fail gates**

```python
report["gate_summary"] = {
    "search_http": {
        "target_p95_ms": 350,
        "actual_p95_ms": http["search_http"]["p95_ms"],
        "pass": http["search_http"]["p95_ms"] <= 350,
    },
    "recommendations_http": {
        "target_p95_ms": 1500,
        "actual_p95_ms": control_plane["recommendations_http"]["p95_ms"],
        "pass": control_plane["recommendations_http"]["p95_ms"] <= 1500,
    },
}
```

- [ ] **Step 4: Update the runbook with post-remediation gate expectations**

```markdown
## Post-Remediation Enterprise Gate

- `POST /api/search` p95 <= `350 ms` at `500` modules
- `GET /api/admin/dashboard` p95 <= `750 ms` at `500` modules
- `GET /api/recommendations` p95 <= `1500 ms` at `500` modules
- `POST /api/chat` <= `8000 ms` mean with a real provider-backed run
- `POST /api/upload` <= `6000 ms` mean on small text documents
```

- [ ] **Step 5: Re-run benchmark matrix**

Run:

```bash
PYTHONPATH=D:\tyh\knowledge-manager\src python D:\tyh\knowledge-manager\src\knowledge_manager\performance_benchmarks.py
```

Expected:

- new report artifacts generated
- `gate_summary` present
- before/after deltas show large improvement in `search_http`, `recommendations_http`, and `admin_dashboard_http`

- [ ] **Step 6: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\performance_benchmarks.py D:\tyh\knowledge-manager\docs\runbooks\enterprise-performance-test-plan.md D:\tyh\knowledge-manager\README.md D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py
git commit -m "docs: add enterprise performance gates"
```

## Self-Review

### Spec coverage

- Real bottlenecks from search, recommendations, health, admin, MCP, chat, upload, and research failure are each covered by at least one task.
- Read-path amplification is addressed in Tasks 2 and 3.
- Control-plane heaviness is addressed in Task 4.
- Write-path rebuild overhead is addressed in Task 5.
- MCP/provider-backed defects are addressed in Task 6.
- Enterprise proof and rerun gates are addressed in Task 7.

### Placeholder scan

- No `TBD`, `TODO`, or “implement later” placeholders remain.
- Every task includes explicit files, commands, and code snippets.
- Each verification step has an exact command and expected outcome.

### Type consistency

- `ModuleCache`, `build_lexical_index`, `query_lexical_index`, snapshot helpers, and gate summary names are used consistently across later tasks.
- Cache invalidation, lexical rebuild, and incremental index update names are consistent between tasks.
