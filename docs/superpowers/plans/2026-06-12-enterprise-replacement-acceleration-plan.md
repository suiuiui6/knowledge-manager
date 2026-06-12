# Enterprise Replacement Acceleration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `knowledge-manager` from a production-grade knowledge operating system into a credible enterprise replacement for classic RAG, pageindex, and llm-wiki by closing the remaining migration blockers in retrieval quality, scale operations, trust boundaries, and user adoption workflows.

**Architecture:** Keep the existing git-native module model and enterprise control plane, but add four missing layers: retrieval quality instrumentation, ingestion job orchestration, enterprise tenancy and permission resolution, and migration-grade operator/product experience. The implementation should preserve inspectability and deterministic storage while introducing optional high-scale capabilities through isolated modules and explicit job/state records instead of collapsing into a monolithic service.

**Tech Stack:** Python 3.10+, pytest, FastAPI, existing CLI/HTTP/MCP surfaces, JSON/JSONL storage, optional async worker loops, optional vector index backends, existing auth/RBAC modules, existing enterprise ingestion and ops export framework.

---

## Why The Product Still Does Not Fully Beat RAG / pageindex / llm-wiki

### Already Ahead
- Governable module-based knowledge beats chunk-only retrieval for auditability and operational control.
- Provenance, stale-impact tracking, routing policy, eval gate, and control-plane exports are stronger than most lightweight RAG/wiki tools.
- HTTP + MCP + CLI parity is unusually strong for an inspectable local-first system.

### Remaining Migration Blockers
- Retrieval quality is not yet measured deeply enough to prove superiority in large real workloads.
- Source pull is synchronous/operator-driven rather than job-driven with queueing, resume, and throughput visibility.
- Permission enforcement is not yet end-to-end at enterprise depth for large multi-team deployments.
- Multi-tenant isolation, workspace federation governance, and enterprise policy inheritance are still thin.
- Migration tooling from incumbent systems is limited; operators still do too much manual work.
- Default product UX is still engineer-friendly rather than enterprise-admin-friendly.

## File Structure

### Existing files to extend
- `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
  Responsibility: retrieval telemetry, job persistence, tenant-aware module operations, governance reports.
- `D:\tyh\knowledge-manager\src\knowledge_manager\source_ingestion.py`
  Responsibility: asynchronous source pull orchestration, checkpoints, import pipelines, migration adapters.
- `D:\tyh\knowledge-manager\src\knowledge_manager\cli.py`
  Responsibility: operator job control, migration commands, eval workflows, tenant administration.
- `D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py`
  Responsibility: admin APIs, job APIs, migration APIs, permission-aware reads, admin dashboards.
- `D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py`
  Responsibility: retrieval explanations, tenant-safe access, migration-safe resource views.
- `D:\tyh\knowledge-manager\src\knowledge_manager\eval_runner.py`
  Responsibility: goldens, ranking diagnostics, regression budgets, offline retrieval benchmarking.
- `D:\tyh\knowledge-manager\src\knowledge_manager\vector_index.py`
  Responsibility: semantic recall plumbing, hybrid scoring, backend abstraction.
- `D:\tyh\knowledge-manager\src\knowledge_manager\auth.py`
  Responsibility: auth claim resolution and tenant-aware request identity.
- `D:\tyh\knowledge-manager\src\knowledge_manager\rbac.py`
  Responsibility: policy inheritance, tenant/category/module scopes, effective access resolution.
- `D:\tyh\knowledge-manager\README.md`
  Responsibility: positioning, migration claims, rollout guidance, operator commands.
- `D:\tyh\knowledge-manager\tests\test_storage.py`
  Responsibility: retrieval telemetry, tenant isolation, job persistence.
- `D:\tyh\knowledge-manager\tests\test_http_server.py`
  Responsibility: admin API, migration API, job API, permission surfaces.
- `D:\tyh\knowledge-manager\tests\test_mcp_server.py`
  Responsibility: governed retrieval explanations, tenant-safe resources.
- `D:\tyh\knowledge-manager\tests\test_cli.py`
  Responsibility: operator command coverage.
- `D:\tyh\knowledge-manager\tests\test_eval_runner.py`
  Responsibility: ranking diagnostics and regression budgets.
- `D:\tyh\knowledge-manager\tests\test_integration.py`
  Responsibility: end-to-end ingest/eval/ops/migration replacement gates.

### New files to create
- `D:\tyh\knowledge-manager\src\knowledge_manager\retrieval_eval.py`
  Responsibility: ranking diagnostics, hit-position analysis, nDCG/MRR/recall metrics, golden replay helpers.
- `D:\tyh\knowledge-manager\src\knowledge_manager\ingestion_jobs.py`
  Responsibility: append-only ingestion job model, retries, leases, checkpoints, orchestration state.
- `D:\tyh\knowledge-manager\src\knowledge_manager\migration.py`
  Responsibility: import/export adapters, incumbent metadata normalization, dry-run migration summaries.
- `D:\tyh\knowledge-manager\src\knowledge_manager\tenancy.py`
  Responsibility: tenant/workspace model, isolation rules, workspace inheritance helpers.
- `D:\tyh\knowledge-manager\src\knowledge_manager\admin_views.py`
  Responsibility: dashboard aggregation tailored to enterprise operators.
- `D:\tyh\knowledge-manager\tests\test_retrieval_eval.py`
  Responsibility: ranking diagnostics and hybrid scoring coverage.
- `D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py`
  Responsibility: job checkpoints, retry semantics, resume behavior.
- `D:\tyh\knowledge-manager\tests\test_migration.py`
  Responsibility: dry-run summaries, import normalization, rollback evidence.
- `D:\tyh\knowledge-manager\tests\test_tenancy.py`
  Responsibility: tenant isolation and inheritance rules.

## Delivery Stages

1. Retrieval proof and ranking superiority
2. Industrial ingestion and job orchestration
3. Enterprise tenancy and permission depth
4. Migration and operator adoption workflow
5. Replacement-grade release proof

### Task 1: Prove Retrieval Superiority With Real Ranking Diagnostics

**Files:**
- Create: `D:\tyh\knowledge-manager\src\knowledge_manager\retrieval_eval.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\eval_runner.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
- Create: `D:\tyh\knowledge-manager\tests\test_retrieval_eval.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_eval_runner.py`

- [ ] **Step 1: Write the failing ranking diagnostics test**

```python
from knowledge_manager.retrieval_eval import score_ranked_case


def test_score_ranked_case_reports_mrr_ndcg_and_hit_position():
    summary = score_ranked_case(
        required_modules=["ops/runbook", "policy/change-approval"],
        found_modules=["auth/jwt", "ops/runbook", "policy/change-approval"],
    )

    assert summary.first_hit_rank == 2
    assert round(summary.mrr, 3) == 0.5
    assert summary.ndcg_at_k > 0.6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_retrieval_eval.py::test_score_ranked_case_reports_mrr_ndcg_and_hit_position -v`
Expected: `FAIL` because `retrieval_eval.py` does not exist yet.

- [ ] **Step 3: Write minimal ranking diagnostic implementation**

```python
from pydantic import BaseModel


class RankedCaseSummary(BaseModel):
    first_hit_rank: int | None = None
    mrr: float = 0.0
    ndcg_at_k: float = 0.0
    recall_at_k: float = 0.0


def score_ranked_case(required_modules: list[str], found_modules: list[str]) -> RankedCaseSummary:
    hit_positions = [idx + 1 for idx, module_key in enumerate(found_modules) if module_key in required_modules]
    first_hit_rank = hit_positions[0] if hit_positions else None
    mrr = 1.0 / first_hit_rank if first_hit_rank else 0.0
    hits = [1 if module_key in required_modules else 0 for module_key in found_modules]
    dcg = sum(rel / math.log2(idx + 2) for idx, rel in enumerate(hits))
    ideal_hits = [1] * min(len(required_modules), len(found_modules))
    idcg = sum(rel / math.log2(idx + 2) for idx, rel in enumerate(ideal_hits))
    recall = len(set(required_modules) & set(found_modules)) / len(required_modules) if required_modules else 0.0
    return RankedCaseSummary(
        first_hit_rank=first_hit_rank,
        mrr=mrr,
        ndcg_at_k=(dcg / idcg) if idcg else 0.0,
        recall_at_k=recall,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_retrieval_eval.py::test_score_ranked_case_reports_mrr_ndcg_and_hit_position -v`
Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\retrieval_eval.py D:\tyh\knowledge-manager\src\knowledge_manager\eval_runner.py D:\tyh\knowledge-manager\src\knowledge_manager\storage.py D:\tyh\knowledge-manager\tests\test_retrieval_eval.py D:\tyh\knowledge-manager\tests\test_eval_runner.py
git commit -m "feat: add retrieval ranking diagnostics"
```

### Task 2: Add Hybrid Retrieval Scoring That Can Beat Naive RAG Recall

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\vector_index.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\retrieval_eval.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_storage.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_watch_vector.py`

- [ ] **Step 1: Write the failing hybrid ranking test**

```python
def test_hybrid_search_promotes_supported_vector_hit_without_losing_policy_controls(tmp_path, monkeypatch):
    kb = tmp_path / "kb"
    kb.mkdir()
    save_module(make_module("legacy-acronym", "ops"), kb)

    monkeypatch.setattr(
        "knowledge_manager.vector_index.VectorIndex.search",
        lambda self, query, top_k=20: [("ops/legacy-acronym", 0.97)],
    )

    results = search_modules("zzqv acronym", kb, enable_vector_fallback=True)

    assert results[0].module.id == "legacy-acronym"
    assert "vector_fallback" in results[0].reasons or results[0].source == "vector_fallback"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_watch_vector.py::test_hybrid_search_promotes_supported_vector_hit_without_losing_policy_controls -v`
Expected: `FAIL` because hybrid scoring does not exist yet.

- [ ] **Step 3: Implement minimal hybrid scoring**

```python
def _merge_hybrid_scores(
    lexical_results: list[SearchResult],
    vector_hits: list[tuple[str, float]],
    kb_path: Path,
) -> list[SearchResult]:
    merged: dict[str, SearchResult] = {
        f"{item.module.category}/{item.module.id}": item for item in lexical_results
    }
    for module_key, score in vector_hits:
        if module_key in merged:
            merged[module_key].reasons.append(f"vector_support:{round(score, 3)}")
            continue
        category, module_id = module_key.split("/", 1)
        module = load_module(module_id, category, kb_path)
        if module is None:
            continue
        merged[module_key] = SearchResult(module, "vector_fallback", [f"vector_support:{round(score, 3)}"])
    return list(merged.values())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_watch_vector.py::test_hybrid_search_promotes_supported_vector_hit_without_losing_policy_controls -v`
Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\storage.py D:\tyh\knowledge-manager\src\knowledge_manager\vector_index.py D:\tyh\knowledge-manager\src\knowledge_manager\retrieval_eval.py D:\tyh\knowledge-manager\tests\test_storage.py D:\tyh\knowledge-manager\tests\test_watch_vector.py
git commit -m "feat: add hybrid lexical semantic retrieval"
```

### Task 3: Replace Manual Source Pull With Durable Ingestion Jobs

**Files:**
- Create: `D:\tyh\knowledge-manager\src\knowledge_manager\ingestion_jobs.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\source_ingestion.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\cli.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py`
- Create: `D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_cli.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_http_server.py`

- [ ] **Step 1: Write the failing ingestion job lifecycle test**

```python
from knowledge_manager.ingestion_jobs import create_ingestion_job, claim_ingestion_job, complete_ingestion_job


def test_ingestion_job_claim_complete_round_trip(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()

    job = create_ingestion_job(kb, source_id="team-docs", trigger="manual")
    claimed = claim_ingestion_job(kb, job.job_id, worker_id="worker-1")
    finished = complete_ingestion_job(kb, job.job_id, pages_seen=12, modules_staged=7)

    assert claimed.status == "running"
    assert finished.status == "completed"
    assert finished.pages_seen == 12
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py::test_ingestion_job_claim_complete_round_trip -v`
Expected: `FAIL` because `ingestion_jobs.py` does not exist yet.

- [ ] **Step 3: Implement minimal append-only ingestion job storage**

```python
class IngestionJob(BaseModel):
    job_id: str
    source_id: str
    trigger: str
    status: str = "queued"
    worker_id: str = ""
    pages_seen: int = 0
    modules_staged: int = 0


def create_ingestion_job(kb_path: Path, source_id: str, trigger: str) -> IngestionJob:
    job = IngestionJob(job_id=f"job-{uuid4().hex[:12]}", source_id=source_id, trigger=trigger)
    _save_job(kb_path, job)
    return job
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py::test_ingestion_job_claim_complete_round_trip -v`
Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\ingestion_jobs.py D:\tyh\knowledge-manager\src\knowledge_manager\source_ingestion.py D:\tyh\knowledge-manager\src\knowledge_manager\cli.py D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py D:\tyh\knowledge-manager\tests\test_cli.py D:\tyh\knowledge-manager\tests\test_http_server.py
git commit -m "feat: add durable ingestion jobs"
```

### Task 4: Add Checkpoints, Resume, And Backpressure For Large Imports

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\ingestion_jobs.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\source_ingestion.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_source_ingestion.py`

- [ ] **Step 1: Write the failing resume test**

```python
def test_ingestion_job_resume_preserves_checkpoint(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    job = create_ingestion_job(kb, source_id="team-docs", trigger="manual")
    update_ingestion_checkpoint(kb, job.job_id, cursor="cursor-9", pages_seen=25)

    resumed = resume_ingestion_job(kb, job.job_id)

    assert resumed.resume_cursor == "cursor-9"
    assert resumed.pages_seen == 25
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py::test_ingestion_job_resume_preserves_checkpoint -v`
Expected: `FAIL` because checkpoint resume is missing.

- [ ] **Step 3: Implement minimal checkpoint persistence**

```python
class IngestionCheckpoint(BaseModel):
    cursor: str = ""
    pages_seen: int = 0


def update_ingestion_checkpoint(kb_path: Path, job_id: str, cursor: str, pages_seen: int) -> IngestionJob:
    job = load_ingestion_job(kb_path, job_id)
    job.resume_cursor = cursor
    job.pages_seen = pages_seen
    _save_job(kb_path, job)
    return job
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py::test_ingestion_job_resume_preserves_checkpoint -v`
Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\ingestion_jobs.py D:\tyh\knowledge-manager\src\knowledge_manager\source_ingestion.py D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py D:\tyh\knowledge-manager\tests\test_source_ingestion.py
git commit -m "feat: add ingestion checkpoints and resume"
```

### Task 5: Introduce Real Enterprise Tenancy And Workspace Isolation

**Files:**
- Create: `D:\tyh\knowledge-manager\src\knowledge_manager\tenancy.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\auth.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\rbac.py`
- Create: `D:\tyh\knowledge-manager\tests\test_tenancy.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_enterprise.py`

- [ ] **Step 1: Write the failing tenant isolation test**

```python
from knowledge_manager.tenancy import TenantContext


def test_list_modules_only_returns_requested_tenant_modules(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    save_module(make_module("auth-a", "auth", tenant_id="team-a"), kb)
    save_module(make_module("auth-b", "auth", tenant_id="team-b"), kb)

    modules = list_modules(kb, tenant=TenantContext(tenant_id="team-a"))

    assert [module.id for module in modules] == ["auth-a"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_tenancy.py::test_list_modules_only_returns_requested_tenant_modules -v`
Expected: `FAIL` because tenant model does not exist yet.

- [ ] **Step 3: Implement minimal tenant context and filtering**

```python
class TenantContext(BaseModel):
    tenant_id: str
    workspace_id: str = ""
    allow_global_reads: bool = True


def module_visible_to_tenant(module: Module, tenant: TenantContext | None) -> bool:
    if tenant is None:
        return True
    module_tenant = getattr(module.metadata, "tenant_id", "")
    return module_tenant == tenant.tenant_id or (tenant.allow_global_reads and not module_tenant)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_tenancy.py::test_list_modules_only_returns_requested_tenant_modules -v`
Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\tenancy.py D:\tyh\knowledge-manager\src\knowledge_manager\storage.py D:\tyh\knowledge-manager\src\knowledge_manager\auth.py D:\tyh\knowledge-manager\src\knowledge_manager\rbac.py D:\tyh\knowledge-manager\tests\test_tenancy.py D:\tyh\knowledge-manager\tests\test_enterprise.py
git commit -m "feat: add tenant aware module isolation"
```

### Task 6: Make Permission Resolution Explainable And Enterprise-Scoped

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\rbac.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_enterprise.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_http_server.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_mcp_server.py`

- [ ] **Step 1: Write the failing permission explanation test**

```python
def test_permission_checker_reports_effective_reason():
    checker = PermissionChecker(
        roles={"reviewer": {"permissions": ["module:read"], "scopes": ["category:policy"]}},
        group_mapping={"grp-reviewers": ["reviewer"]},
    )

    decision = checker.explain_module_access(["grp-reviewers"], {"category": "finance", "id": "fin-1"})

    assert decision.allowed is False
    assert "scope_mismatch" in decision.reasons
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_enterprise.py::test_permission_checker_reports_effective_reason -v`
Expected: `FAIL` because explainability helper is missing.

- [ ] **Step 3: Implement minimal explainable decision model**

```python
class AccessDecision(BaseModel):
    allowed: bool
    reasons: list[str] = Field(default_factory=list)
    matched_roles: list[str] = Field(default_factory=list)


def explain_module_access(self, groups: list[str], module: dict) -> AccessDecision:
    roles = self.resolve_roles(groups)
    for role in roles:
        if self._role_allows(role, module, "module:read"):
            return AccessDecision(allowed=True, reasons=["role_scope_match"], matched_roles=[role])
    return AccessDecision(allowed=False, reasons=["scope_mismatch"] if roles else ["no_matching_role"], matched_roles=roles)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_enterprise.py::test_permission_checker_reports_effective_reason -v`
Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\rbac.py D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py D:\tyh\knowledge-manager\tests\test_enterprise.py D:\tyh\knowledge-manager\tests\test_http_server.py D:\tyh\knowledge-manager\tests\test_mcp_server.py
git commit -m "feat: explain effective enterprise access decisions"
```

### Task 7: Build Migration Tooling That Removes Switching Friction

**Files:**
- Create: `D:\tyh\knowledge-manager\src\knowledge_manager\migration.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\cli.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py`
- Create: `D:\tyh\knowledge-manager\tests\test_migration.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_cli.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_http_server.py`

- [ ] **Step 1: Write the failing dry-run migration summary test**

```python
from knowledge_manager.migration import dry_run_import


def test_dry_run_import_reports_creates_updates_and_skips(tmp_path):
    source_dump = tmp_path / "export.json"
    source_dump.write_text('[{"id":"page-1","title":"Runbook","body":"text"}]', encoding="utf-8")

    summary = dry_run_import(source_dump, source_kind="llm_wiki")

    assert summary.total_documents == 1
    assert summary.creates == 1
    assert summary.errors == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_migration.py::test_dry_run_import_reports_creates_updates_and_skips -v`
Expected: `FAIL` because migration module does not exist yet.

- [ ] **Step 3: Implement minimal dry-run import summary**

```python
class ImportSummary(BaseModel):
    total_documents: int = 0
    creates: int = 0
    updates: int = 0
    skips: int = 0
    errors: list[str] = Field(default_factory=list)


def dry_run_import(source_path: Path, source_kind: str) -> ImportSummary:
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    return ImportSummary(total_documents=len(payload), creates=len(payload))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_migration.py::test_dry_run_import_reports_creates_updates_and_skips -v`
Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\migration.py D:\tyh\knowledge-manager\src\knowledge_manager\cli.py D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py D:\tyh\knowledge-manager\tests\test_migration.py D:\tyh\knowledge-manager\tests\test_cli.py D:\tyh\knowledge-manager\tests\test_http_server.py
git commit -m "feat: add migration dry run tooling"
```

### Task 8: Give Operators An Enterprise Admin View Instead Of Raw Reports

**Files:**
- Create: `D:\tyh\knowledge-manager\src\knowledge_manager\admin_views.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\ops_export.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_http_server.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_ops_export.py`

- [ ] **Step 1: Write the failing admin dashboard aggregation test**

```python
from knowledge_manager.admin_views import build_admin_dashboard


def test_build_admin_dashboard_reports_jobs_backlog_and_eval_regressions(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()

    dashboard = build_admin_dashboard(kb)

    assert "ingestion_jobs" in dashboard
    assert "stale_sources" in dashboard
    assert "eval_regressions" in dashboard
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_http_server.py::test_build_admin_dashboard_reports_jobs_backlog_and_eval_regressions -v`
Expected: `FAIL` because admin dashboard module does not exist yet.

- [ ] **Step 3: Implement minimal admin dashboard aggregation**

```python
def build_admin_dashboard(kb_path: Path) -> dict[str, Any]:
    return {
        "ingestion_jobs": [],
        "stale_sources": generate_source_backlog_export(kb_path).get("items", []),
        "review_backlog": generate_review_backlog_export(kb_path).get("items", []),
        "eval_regressions": [],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_http_server.py::test_build_admin_dashboard_reports_jobs_backlog_and_eval_regressions -v`
Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\admin_views.py D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py D:\tyh\knowledge-manager\src\knowledge_manager\ops_export.py D:\tyh\knowledge-manager\tests\test_http_server.py D:\tyh\knowledge-manager\tests\test_ops_export.py
git commit -m "feat: add enterprise admin dashboard view"
```

### Task 9: Add A Replacement-Grade End-To-End Migration Gate

**Files:**
- Modify: `D:\tyh\knowledge-manager\tests\test_integration.py`
- Modify: `D:\tyh\knowledge-manager\README.md`
- Create: `D:\tyh\knowledge-manager\docs\runbooks\migration-cutover.md`

- [ ] **Step 1: Write the failing replacement-flow integration test**

```python
def test_replacement_flow_import_ingest_eval_and_ops(runner, integration_kb, monkeypatch, tmp_path):
    export_path = tmp_path / "legacy-export.json"
    export_path.write_text('[{"id":"page-1","title":"Runbook","body":"rollback safely"}]', encoding="utf-8")

    dry_run = runner.invoke(cli, ["--kb-path", str(integration_kb), "migrate", "dry-run", str(export_path), "--source-kind", "llm_wiki"])
    ops = runner.invoke(cli, ["--kb-path", str(integration_kb), "ops", "--format", "json"])

    assert dry_run.exit_code == 0
    assert '"total_documents": 1' in dry_run.output
    assert '"source_backlog"' in ops.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_integration.py::test_replacement_flow_import_ingest_eval_and_ops -v`
Expected: `FAIL` until migration flow is wired end-to-end.

- [ ] **Step 3: Implement minimal cutover documentation and final wiring**

```markdown
# Migration Cutover

1. Export incumbent data and run `km migrate dry-run`.
2. Validate creates/updates/skips before importing.
3. Run source pull jobs until backlog stabilizes.
4. Run eval gate and compare MRR/recall metrics against incumbent baseline.
5. Review tenant permissions and risky-miss backlog before switching clients.
6. Keep rollback bundle with original export, import summary, and eval report.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_integration.py::test_replacement_flow_import_ingest_eval_and_ops -v`
Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add D:\tyh\knowledge-manager\tests\test_integration.py D:\tyh\knowledge-manager\README.md D:\tyh\knowledge-manager\docs\runbooks\migration-cutover.md
git commit -m "docs: add migration cutover gate"
```

### Task 10: Run The Enterprise Replacement Verification Sweep

**Files:**
- Modify: `D:\tyh\knowledge-manager\README.md`
- Modify: `D:\tyh\knowledge-manager\docs\superpowers\plans\2026-06-12-enterprise-replacement-acceleration-plan.md`
- Modify: `D:\tyh\knowledge-manager\tests\test_integration.py`

- [ ] **Step 1: Run focused replacement verification**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_retrieval_eval.py D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py D:\tyh\knowledge-manager\tests\test_tenancy.py D:\tyh\knowledge-manager\tests\test_migration.py -q`
Expected: all focused replacement tests `PASS`

- [ ] **Step 2: Run enterprise full suite**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_schemas.py D:\tyh\knowledge-manager\tests\test_storage.py D:\tyh\knowledge-manager\tests\test_http_server.py D:\tyh\knowledge-manager\tests\test_mcp_server.py D:\tyh\knowledge-manager\tests\test_cli.py D:\tyh\knowledge-manager\tests\test_source_ingestion.py D:\tyh\knowledge-manager\tests\test_confluence.py D:\tyh\knowledge-manager\tests\test_notion.py D:\tyh\knowledge-manager\tests\test_policy.py D:\tyh\knowledge-manager\tests\test_ops_export.py D:\tyh\knowledge-manager\tests\test_eval_runner.py D:\tyh\knowledge-manager\tests\test_enterprise.py D:\tyh\knowledge-manager\tests\test_dual_view.py D:\tyh\knowledge-manager\tests\test_watch_vector.py D:\tyh\knowledge-manager\tests\test_retrieval_eval.py D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py D:\tyh\knowledge-manager\tests\test_tenancy.py D:\tyh\knowledge-manager\tests\test_migration.py D:\tyh\knowledge-manager\tests\test_integration.py -q`
Expected: full enterprise replacement suite `PASS`

- [ ] **Step 3: Update release positioning**

```markdown
## Replacement Readiness

- Hybrid retrieval quality measured with MRR, nDCG, recall, and first-hit rank.
- Ingestion runs are durable jobs with checkpoints and resume support.
- Tenant-aware access and explainable permission decisions are enforced.
- Migration dry runs and cutover docs reduce incumbent switching risk.
- Enterprise admin views expose jobs, backlogs, stale sources, and eval regressions.
```

- [ ] **Step 4: Re-run README/spec validation checks**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_integration.py -k "replacement_flow or enterprise_ingest_eval_ops_flow" -q`
Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add D:\tyh\knowledge-manager\README.md D:\tyh\knowledge-manager\docs\superpowers\plans\2026-06-12-enterprise-replacement-acceleration-plan.md D:\tyh\knowledge-manager\tests\test_integration.py
git commit -m "docs: certify enterprise replacement readiness"
```

## Release Exit Criteria

- Retrieval is measured with first-hit rank, recall, MRR, and nDCG on enterprise eval suites rather than relying on hit-rate alone.
- Hybrid lexical + semantic retrieval improves difficult-query recall without bypassing provenance or policy controls.
- Source ingestion runs as durable jobs with queueing, checkpoints, retry classification, and resume support.
- Tenant/workspace isolation exists and enterprise permission decisions are explainable to operators.
- Migration from incumbent tools can be dry-run, summarized, and gated before cutover.
- Admin surfaces expose ingestion jobs, stale sources, review backlog, risky misses, and eval regressions.
- End-to-end migration + ingest + eval + ops integration tests pass and serve as replacement proof.

## Self-Review

### Spec coverage
- Retrieval-quality gap is covered by Tasks 1-2 and the replacement verification in Task 10.
- Industrial ingestion gap is covered by Tasks 3-4.
- Enterprise tenancy and explainable access gaps are covered by Tasks 5-6.
- Migration friction and product adoption gaps are covered by Tasks 7-9.
- Release-proof requirements are covered by Task 10 and the exit criteria.

### Placeholder scan
- No `TODO`, `TBD`, or “implement later” placeholders remain.
- Each task includes exact files, an actual failing test, a concrete command, a minimal implementation snippet, and a commit step.

### Type consistency
- `RankedCaseSummary`, `IngestionJob`, `TenantContext`, `AccessDecision`, and `ImportSummary` are introduced before later tasks reference them.
- The same file paths, commands, and helper names are reused consistently across tasks.
