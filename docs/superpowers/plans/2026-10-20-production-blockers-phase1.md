# 第一阶段生产阻断项改进实施计划

> **For agentic workers:** Execute this plan task-by-task with test-first changes and verification after each task.

**Goal:** 关闭 `knowledge-manager` 当前生产切换前的认证、完整性、任务一致性和性能阻断项。

**Architecture:** 保持 Git 原生 JSON 和单节点文件型架构。认证和租户范围在 HTTP/MCP 入口统一收敛，索引与任务状态通过原子文件替换和租约保护维护，性能优化优先复用现有派生索引和物化视图。

**Tech Stack:** Python 3.10+, Poetry, Pydantic 2, FastAPI, FastMCP, pytest, mypy, black。

---

### Task 1: 认证依赖与租户安全边界

**Files:**
- Modify: `pyproject.toml`
- Modify: `poetry.lock` via `poetry lock`
- Modify: `src/knowledge_manager/auth.py`
- Modify: `src/knowledge_manager/http_authz.py`
- Modify: `src/knowledge_manager/tenancy.py`
- Modify: `src/knowledge_manager/mcp_server.py`
- Test: `tests/test_enterprise.py`, `tests/test_http_server.py`, `tests/test_mcp_server.py`, `tests/test_tenancy.py`

- [ ] **Step 1: Add failing dependency and production-auth tests**
  - Add a test that imports `validate_oidc_token` in a clean project environment and asserts the configured JWT dependency is available.
  - Add tests for production mode with no `auth.json`, invalid token, cross-tenant HTTP search/detail, and multi-tenant MCP global resource denial.
  - Add a test that a non-admin cannot request a different tenant/workspace while an admin can explicitly override it.

- [ ] **Step 2: Run the focused tests and confirm expected failures**

  Run:

  ```powershell
  $env:PYTHONPATH='src'; pytest -q tests/test_enterprise.py tests/test_http_server.py tests/test_mcp_server.py tests/test_tenancy.py
  ```

- [ ] **Step 3: Add and lock the runtime JWT dependency**
  - Add the package providing the imported `jwt` module to `[tool.poetry.dependencies]`.
  - Run `poetry lock` and confirm the lock contains the package in the main group.

- [ ] **Step 4: Make tenant visibility explicit**
  - Add a configuration-controlled `allow_global_reads` decision for multi-tenant mode.
  - Default multi-tenant request contexts to deny unscoped global modules unless explicitly enabled.
  - Keep single-tenant local behavior unchanged.

- [ ] **Step 5: Run focused security tests and inspect failures**

  Run the same focused pytest command and then `poetry run mypy src/knowledge_manager/auth.py src/knowledge_manager/http_authz.py src/knowledge_manager/tenancy.py src/knowledge_manager/mcp_server.py`.

- [ ] **Step 6: Commit the security batch**

  ```powershell
  git add pyproject.toml poetry.lock src/knowledge_manager/auth.py src/knowledge_manager/http_authz.py src/knowledge_manager/tenancy.py src/knowledge_manager/mcp_server.py tests/test_enterprise.py tests/test_http_server.py tests/test_mcp_server.py tests/test_tenancy.py
  git commit -m "fix: close production auth and tenant boundaries"
  ```

### Task 2: Index integrity and atomic writes

**Files:**
- Modify: `src/knowledge_manager/ingestion_jobs.py`
- Modify: `src/knowledge_manager/rbac.py`
- Modify: `src/knowledge_manager/lexical_index.py`
- Modify: `src/knowledge_manager/runtime_checks.py`
- Modify: `src/knowledge_manager/storage.py` only where existing write paths need to call shared atomic helpers
- Test: `tests/test_runtime_checks.py`, `tests/test_ingestion_jobs.py`, `tests/test_storage.py`

- [ ] **Step 1: Add failing atomic-write and drift-repair tests**
  - Assert task JSON is written through a temporary file and replaced atomically.
  - Assert RBAC and lexical index writes leave valid JSON when replacement succeeds.
  - Create dangling index, search projection drift, and recommendation drift fixtures; assert integrity reports each issue and `repair_runtime_artifacts` restores all derived keys.

- [ ] **Step 2: Run focused tests to verify the regression tests fail**

  ```powershell
  $env:PYTHONPATH='src'; pytest -q tests/test_runtime_checks.py tests/test_ingestion_jobs.py tests/test_storage.py
  ```

- [ ] **Step 3: Introduce one shared atomic JSON writer**
  - Add a small internal helper that writes UTF-8 JSON to a sibling temporary file and calls `os.replace`.
  - Use it for ingestion job state, RBAC config, lexical index and any directly affected derived JSON.
  - Ensure temporary files are cleaned on failure.

- [ ] **Step 4: Preserve and verify repair ordering**
  - Rebuild the canonical index first, then lexical, search projection and recommendation indexes.
  - Keep repair idempotent and return the repaired artifact names.

- [ ] **Step 5: Run focused tests and integrity checks**

  ```powershell
  $env:PYTHONPATH='src'; pytest -q tests/test_runtime_checks.py tests/test_ingestion_jobs.py tests/test_storage.py
  python scripts/verify_install_smoke.py
  ```

- [ ] **Step 6: Commit the integrity batch**

  ```powershell
  git add src/knowledge_manager/ingestion_jobs.py src/knowledge_manager/rbac.py src/knowledge_manager/lexical_index.py src/knowledge_manager/runtime_checks.py src/knowledge_manager/storage.py tests/test_runtime_checks.py tests/test_ingestion_jobs.py tests/test_storage.py
  git commit -m "fix: make knowledge state writes atomic"
  ```

### Task 3: Ingestion job claim and recovery consistency

**Files:**
- Modify: `src/knowledge_manager/ingestion_jobs.py`
- Modify: `src/knowledge_manager/job_worker.py`
- Test: `tests/test_ingestion_jobs.py`, `tests/test_worker_service.py`, `tests/test_http_server.py`

- [ ] **Step 1: Add failing claim and lease tests**
  - Create a queued job and assert the first worker can claim it.
  - Assert a second worker cannot claim the same job while its lease is active.
  - Set an expired lease and assert another worker can reclaim it with an incremented attempt count.
  - Assert a completed or failed job cannot be claimed again.

- [ ] **Step 2: Run the job tests and confirm the current implementation fails**

  ```powershell
  $env:PYTHONPATH='src'; pytest -q tests/test_ingestion_jobs.py tests/test_worker_service.py
  ```

- [ ] **Step 3: Implement guarded claim semantics**
  - Load the job once, reject terminal states, reject active leases owned by another worker, and only then persist the running state.
  - Keep lease and heartbeat timestamps timezone-aware.
  - Return a clear conflict error that the worker converts into a non-destructive no-op.

- [ ] **Step 4: Add stale-job recovery behavior**
  - Requeue expired running jobs through the existing worker recovery path.
  - Preserve the previous error and attempt metadata for auditability.

- [ ] **Step 5: Run job and HTTP regression tests**

  ```powershell
  $env:PYTHONPATH='src'; pytest -q tests/test_ingestion_jobs.py tests/test_worker_service.py tests/test_http_server.py
  ```

- [ ] **Step 6: Commit the job batch**

  ```powershell
  git add src/knowledge_manager/ingestion_jobs.py src/knowledge_manager/job_worker.py tests/test_ingestion_jobs.py tests/test_worker_service.py tests/test_http_server.py
  git commit -m "fix: guard ingestion job claims and recovery"
  ```

### Task 4: Performance hotspot closure and fresh production evidence

**Files:**
- Inspect and modify only the measured hotspots in `src/knowledge_manager/storage.py`, `src/knowledge_manager/materialized_views.py`, `src/knowledge_manager/search_projection.py`, `src/knowledge_manager/recommendation_index.py`, `src/knowledge_manager/admin_views.py`, `src/knowledge_manager/http_server.py`, and `src/knowledge_manager/mcp_server.py`.
- Test: `tests/test_performance_benchmarks.py`, relevant storage/HTTP/MCP tests.

- [ ] **Step 1: Run targeted benchmark contract and hotspot tests**

  ```powershell
  $env:PYTHONPATH='src'; pytest -q tests/test_performance_benchmarks.py tests/test_performance_hotspots.py tests/test_search_projection.py tests/test_recommendation_index.py
  ```

- [ ] **Step 2: Capture a fresh XS/S/M baseline**
  - Generate a new dated matrix directory using the repository benchmark harness.
  - Record `gate_summary`, `release_verdict`, resource usage and integrity result before changing measured code.

- [ ] **Step 3: Fix only measured repeated work**
  - Reuse projection/materialized-view reads where valid.
  - Avoid rebuilding derived indexes inside request handlers.
  - Preserve tenant filtering and write-path invalidation semantics.

- [ ] **Step 4: Add or update regression assertions for the optimized path**
  - Assert response values and tenant visibility remain unchanged.
  - Assert the optimized path does not hydrate all modules when a projection-backed result is available.

- [ ] **Step 5: Run the full applicable verification set**

  ```powershell
  poetry run pytest -q
  poetry run black --check src tests scripts
  poetry run mypy src
  python scripts/verify_install_smoke.py
  python scripts/verify_production_readiness.py --kb-path D:\\tyh\\knowledge-manager\\kb --matrix-summary D:\\tyh\\knowledge-manager\\test-results\\phase1-current\\matrix-summary.json
  ```

- [ ] **Step 6: Commit the performance batch only with fresh evidence**

  ```powershell
  git add src tests test-results
  git commit -m "perf: close production benchmark hotspots"
  ```

## Final release gate

- [ ] All four task batches have separate commits and focused evidence.
- [ ] Current code snapshot passes the applicable full tests and static checks.
- [ ] Fresh XS/S/M reports contain `gate_summary` and `release_verdict`.
- [ ] Readiness and integrity pass, and backup/deployment evidence is current.
- [ ] Only then report whether production blockers are closed; otherwise report the remaining blockers explicitly.
