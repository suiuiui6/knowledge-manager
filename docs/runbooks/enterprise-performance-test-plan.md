# Enterprise Performance Test Plan

## Goal

Establish a production-grade performance test system for `knowledge-manager` that can prove whether the product is ready to replace classic RAG, pageindex, and llm-wiki in enterprise workloads.

This plan is aligned to the current codebase capabilities:

- Retrieval and hybrid retrieval in `src/knowledge_manager/storage.py`
- HTTP control plane in `src/knowledge_manager/http_server.py`
- Ingestion jobs and resume/checkpoint flow
- Tenant-aware filtering and access isolation
- Admin dashboard and migration dry-run operator paths

## 1. Performance Test Scope

Performance testing must cover three planes together instead of testing search alone.

### 1.1 Retrieval Plane

- `search_modules(...)`
- `POST /api/search`
- lexical retrieval
- hybrid retrieval with vector fallback
- tenant-aware retrieval

### 1.2 Control Plane

- `GET /api/modules`
- `GET /api/modules/{cat}/{mod_id}`
- `GET /api/admin/dashboard`
- `GET /api/source/jobs`
- `POST /api/migrate/dry-run`
- `POST /api/access/explain`

### 1.3 Ingestion / Job Plane

- create ingestion job
- claim ingestion job
- update checkpoint
- resume ingestion job
- complete ingestion job
- failed job retry path

## 2. Test Objectives

### 2.1 Product-Level Objectives

- Interactive retrieval must remain fast enough for chat/copilot use.
- Control-plane APIs must stay stable under concurrent operator traffic.
- Ingestion must degrade gracefully under high document volume and parallel pulls.
- Tenant filtering must not cause unacceptable overhead.
- Hybrid retrieval must improve recall without causing major latency regression.

### 2.2 Engineering-Level Objectives

- Identify p50, p95, p99 latency baselines.
- Identify throughput ceiling before error rate rises.
- Identify scale breakpoints for module count, tenant count, and job count.
- Separate CPU bottlenecks, file I/O bottlenecks, and JSON serialization bottlenecks.
- Produce capacity guidance for single-node production deployment.

## 3. Enterprise SLO and Exit Criteria

These are the recommended release gates for the current architecture.

| Domain | Metric | Target | Release Gate |
|---|---:|---:|---:|
| Search API | p50 latency | <= 120 ms | pass/fail |
| Search API | p95 latency | <= 350 ms | pass/fail |
| Search API | p99 latency | <= 800 ms | pass/fail |
| Search API | error rate | < 0.5% | pass/fail |
| Search API with tenant filter | p95 overhead vs baseline | <= 15% | pass/fail |
| Hybrid retrieval | p95 overhead vs lexical | <= 25% | pass/fail |
| Hybrid retrieval | recall@10 uplift | >= 10% | pass/fail |
| Modules list API | p95 latency | <= 250 ms | pass/fail |
| Module detail API | p95 latency | <= 150 ms | pass/fail |
| Admin dashboard | p95 latency | <= 500 ms | pass/fail |
| Source jobs list | p95 latency | <= 300 ms | pass/fail |
| Migration dry-run | p95 latency | <= 2 s per 1k source items | pass/fail |
| Job state transition | p95 latency | <= 100 ms | pass/fail |
| End-to-end ingestion | success rate | >= 99% | pass/fail |
| Long-run soak test | 6h error rate | < 0.2% | pass/fail |
| Resource efficiency | peak memory growth after soak | <= 20% drift | pass/fail |

### 3.1 Benchmark Gate Summary Contract

Every benchmark report emitted by `src/knowledge_manager/performance_benchmarks.py` must include a machine-readable `gate_summary` section.

Required gates in the current remediation phase:

- `search_http`
- `recommendations_http`
- `admin_dashboard_http`
- `module_crud_http`
- `mcp_search_modules`

Each gate entry must include:

- `status`: `pass`, `fail`, or `missing`
- `target_mean_ms`
- `actual_mean_ms`
- `target_p95_ms`
- `actual_p95_ms`

This keeps release decisions anchored to the same benchmark artifact that engineering uses for regression comparison.

### 3.2 Release Verdict Contract

Every benchmark report must also include a machine-readable `release_verdict` section.

Required fields:

- `ready_for_production`
- `failed_gates`
- `readiness_ready`
- `integrity_ok`
- `blockers`
- `hotspot_sections`

This verdict is the final gate used by release operations after combining benchmark gates with runtime readiness and integrity checks.

## Performance Closure Procedure

1. Run targeted pytest suites for retrieval, recommendations, admin dashboard, module CRUD, and benchmark contracts.
2. Generate a fresh benchmark matrix under a new dated directory such as `test-results/perf-run-production-gate-YYYYMMDD-rN`.
3. Run `python scripts/verify_production_readiness.py --kb-path <kb-path> --matrix-summary <matrix-summary>` or `km verify-production-readiness` and keep the JSON output with the benchmark evidence.
4. Compare the new `matrix-summary.json` against the immediately previous production-gate run.
5. Reject any patch that improves one gate while regressing another shared path by more than 10%.
6. Do not call the system production-grade until the required scales `xs`, `s`, and `m` all report `ready_for_production = true`.

## Release-Gate And Rollback Workflow

1. Deploy the target build first with `production_mode=false` and `multi_tenant_mode=false`.
2. Configure auth claims for `user`, `tenant_id`, and `workspace_id`.
3. In multi-tenant environments, disable MCP global resources before exposing MCP to non-admin consumers.
4. If `/api/upload` or source sync is enabled, run `km worker run` as a managed worker service and verify queue recovery for stale `running` or queued jobs before cutover.
5. Run the release gate with `verify_production_readiness.py` or `km verify-production-readiness`; the gate must combine readiness, integrity, and required benchmark scales.
6. Only after the gate passes should `production_mode=true` be enabled.
7. If the gate or cutover fails, roll back the code or configuration change, recover stale jobs and queue state with the worker service, and repeat the release gate before retrying.

## Capacity Boundary Rules

- The green `xs`, `s`, and `m` results define the currently validated operating envelope.
- Any increase beyond the last green `m` profile in module count, tenant count, or ingestion concurrency requires a fresh matrix run before release.
- Do not claim `l` or `xl` support until dedicated artifacts exist for those scales.
- Treat `km verify-deployment` as a required companion check to benchmark-only release evidence.

## 4. Concrete Performance Metrics Table

### 4.1 Core Metrics

| Category | Metric | Description | Collection Method |
|---|---|---|---|
| Latency | p50 / p90 / p95 / p99 / max | End-to-end response time | benchmark harness + HTTP client |
| Throughput | RPS / QPS / jobs/min | Sustainable request processing rate | load tool summary |
| Stability | error rate | non-2xx, timeout, assertion failure | HTTP status + harness checks |
| Saturation | CPU%, memory RSS, disk IOPS | resource usage at load | OS telemetry |
| Concurrency | active workers / concurrent clients | concurrency level under test | load config |
| Queue health | queued jobs, lease wait, retry count | ingestion job system pressure | job state counters |
| Data efficiency | average bytes read per request | I/O pressure proxy | optional tracing |
| Quality | recall@k, MRR, nDCG@k | retrieval quality under load | eval runner |
| Isolation | tenant leakage count | cross-tenant correctness failures | validation assertions |
| Freshness | ingest-to-search visibility lag | time until new content is searchable | end-to-end timestamp probes |

### 4.2 Endpoint-Level Metrics

| Surface | Key Metrics | Notes |
|---|---|---|
| `POST /api/search` | p50, p95, p99, RPS, result count, error rate | primary user-facing latency |
| `POST /api/search` with `tenant_id` | baseline delta, leakage count | isolation overhead must be explicit |
| `GET /api/modules` | p95, payload size, page size sensitivity | pagination and JSON encoding pressure |
| `GET /api/modules/{cat}/{mod_id}` | p95, p99 | detail load should stay cheap |
| `GET /api/admin/dashboard` | p95, CPU cost, memory spike | full aggregation path |
| `GET /api/source/jobs` | p95, list size sensitivity | admin operational visibility |
| `POST /api/migrate/dry-run` | total duration, items/sec, failure classification | incumbent replacement readiness |
| job create/claim/complete | state transition latency, contention | ingestion orchestration backbone |
| hybrid `search_modules` | lexical vs hybrid latency delta | judge vector fallback cost |

## 5. Test Dimensions

Each scenario must be tested across these axes.

| Dimension | Levels |
|---|---|
| Dataset size | XS, S, M, L, XL |
| Query complexity | exact keyword, mixed phrase, fuzzy concept, long natural language |
| Retrieval mode | lexical only, hybrid |
| Tenant topology | single tenant, 10 tenants, 100 tenants |
| Concurrency | 1, 8, 32, 128, 256 virtual users |
| Job pressure | idle, steady ingest, burst ingest, retry storm |
| Cache state | cold, warm, mixed |
| Traffic shape | steady, burst, ramp, soak |

## 6. Test Data Scale Design

The data model should simulate real enterprise knowledge rather than toy markdown.

### 6.1 Knowledge Base Size Tiers

| Tier | Modules | Categories | Avg module size | Total text volume | Tenants | Purpose |
|---|---:|---:|---:|---:|---:|---|
| XS | 1,000 | 20 | 2 KB | 2 GB logical read amplification not expected | 1 | local developer sanity |
| S | 10,000 | 50 | 3 KB | ~30 MB raw content | 5 | baseline performance |
| M | 50,000 | 100 | 4 KB | ~200 MB raw content | 20 | pre-production gate |
| L | 200,000 | 200 | 5 KB | ~1 GB raw content | 50 | enterprise replacement gate |
| XL | 1,000,000 | 500 | 5 KB | ~5 GB raw content | 100+ | architecture stress / future target |

Note: because the current implementation is file- and JSON-oriented, `L` is the realistic near-term hard gate and `XL` is a strategic stress target.

### 6.2 Content Composition

| Content Type | Share | Characteristics |
|---|---:|---|
| runbooks / how-to | 30% | high keyword overlap, long details field |
| policy / compliance | 20% | strict tenant and group isolation |
| ADR / decision records | 15% | long-form rationale, low query frequency, high importance |
| API / technical reference | 20% | exact-match heavy, acronym dense |
| incident / postmortem | 10% | time-based lookup, related-module graph heavy |
| migration / operations metadata | 5% | admin-plane access patterns |

### 6.3 Search Query Set Design

| Query Set | Count | Goal |
|---|---:|---|
| hot exact-match queries | 100 | measure best-case latency |
| medium ambiguity queries | 200 | measure ranking stability |
| long natural-language queries | 100 | simulate copilot/chat usage |
| tenant-sensitive queries | 100 | verify isolation correctness |
| low-hit / miss queries | 50 | measure worst-case scan behavior |
| multilingual or CJK queries | 50 | validate tokenizer branch cost |

Recommended golden set size for quality + latency joint testing: `500` queries.

### 6.4 Ingestion Data Design

| Tier | Source documents | Avg source size | Job count | Parallel connectors |
|---|---:|---:|---:|---:|
| S | 10,000 | 50 KB | 500 | 2 |
| M | 100,000 | 80 KB | 2,000 | 4 |
| L | 1,000,000 | 100 KB | 10,000 | 8 |

Each ingestion dataset should include:

- 70% normal updates
- 15% duplicate/near-duplicate pages
- 10% deletes or tombstones
- 5% malformed or permission-denied records

This is required to test retry, checkpoint, and resume paths realistically.

## 7. Test Scenario Matrix

### 7.1 Retrieval Benchmarks

| Scenario ID | Dataset | Mode | Concurrency | Duration | Success Criteria |
|---|---|---|---:|---:|---|
| R1 | S | lexical | 1 | 5 min | baseline p95 within target |
| R2 | S | hybrid | 1 | 5 min | recall uplift with acceptable overhead |
| R3 | M | lexical | 32 | 10 min | stable RPS, errors < 0.5% |
| R4 | M | hybrid | 32 | 10 min | p95 delta <= 25% |
| R5 | L | lexical + tenant | 64 | 15 min | no leakage, p95 within gate |
| R6 | L | hybrid + tenant | 64 | 15 min | quality uplift preserved |

### 7.2 Control Plane Benchmarks

| Scenario ID | API | Dataset | Concurrency | Duration | Success Criteria |
|---|---|---|---:|---:|---|
| C1 | `/api/modules` | S | 16 | 10 min | pagination stable |
| C2 | `/api/modules/{id}` | M | 32 | 10 min | p95 <= 150 ms |
| C3 | `/api/admin/dashboard` | M | 8 | 10 min | p95 <= 500 ms |
| C4 | `/api/source/jobs` | L jobs | 16 | 10 min | listing cost stays bounded |
| C5 | `/api/migrate/dry-run` | M source set | 4 | 20 runs | items/sec stable |

### 7.3 Ingestion Benchmarks

| Scenario ID | Dataset | Parallelism | Duration | Success Criteria |
|---|---|---:|---:|---|
| I1 | S | 2 workers | full run | baseline throughput |
| I2 | M | 4 workers | full run | checkpoint/resume stable |
| I3 | L | 8 workers | full run | retry rate controlled |
| I4 | M burst | 8 workers | 30 min | no lease deadlock |
| I5 | M retry storm | 8 workers | 30 min | failure isolation works |

### 7.4 Soak and Endurance

| Scenario ID | Traffic | Duration | Success Criteria |
|---|---|---:|---|
| S1 | search steady load at 60% peak | 6 h | latency drift <= 20% |
| S2 | mixed search + modules + jobs | 12 h | no memory leak trend |
| S3 | mixed load + periodic ingest | 24 h | no corruption or tenant leakage |

## 8. Recommended Load Profile

### 8.1 Ramp Test

- 0 -> 8 -> 32 -> 64 -> 128 concurrent users
- hold each step for 5 minutes
- locate saturation knee and error inflection point

### 8.2 Stress Test

- jump directly to 2x expected production concurrency
- keep pressure until p99 and error rate break
- identify the first failing subsystem

### 8.3 Soak Test

- 40% search
- 25% module list/detail
- 20% ingestion job operations
- 10% admin dashboard and source jobs
- 5% migration/access explain

## 9. Environment and Observability Requirements

### 9.1 Test Environments

| Environment | Purpose |
|---|---|
| local benchmark node | rapid iteration and regression detection |
| staging single-node | release gate and tuning |
| staging production-shape | final enterprise capacity test |

### 9.2 Observability

Collect at minimum:

- request latency histogram
- request count and error count
- CPU%
- RSS memory
- open file count
- disk read/write throughput
- per-job state counts
- queue wait time
- checkpoint frequency

Worker service and queue recovery are release-blocking checks whenever uploads or source sync are part of the production rollout.

## 10. Bottleneck Expectations For Current Architecture

Based on the current codebase, the first likely bottlenecks are:

1. `list_modules()` full file scan and JSON parse amplification
2. `search_modules()` per-request module enumeration and scoring cost
3. admin aggregation endpoints that repeatedly traverse the full knowledge base
4. tenant filtering overhead when performed after wide scans
5. migration dry-run and ingestion job state persistence on large file sets

## 11. Recommended Execution Order

### Phase 1

- retrieval baseline on `S`
- control-plane baseline on `S`
- ingestion state-transition benchmark

### Phase 2

- retrieval and tenant overhead on `M`
- admin and jobs listing on `M`
- checkpoint/resume ingestion on `M`

### Phase 3

- enterprise gate on `L`
- 6h soak
- hybrid quality-vs-latency validation

## 12. Final Deliverables

Each performance cycle should produce:

- raw benchmark JSON
- summary Markdown report
- bottleneck analysis
- SLO pass/fail table
- optimization backlog sorted by ROI
- before/after comparison against previous baseline

## 13. Immediate Recommended Baseline For This Repository

If only one initial round is run now, use this minimum baseline:

| Area | Dataset | Concurrency | Metric Focus |
|---|---|---:|---|
| `POST /api/search` | 10k modules | 1, 32, 128 | p95, p99, RPS |
| `POST /api/search` with `tenant_id` | 10k modules / 10 tenants | 32 | overhead and leakage |
| hybrid retrieval | 10k modules | 32 | recall uplift vs latency delta |
| `GET /api/modules` | 10k modules | 16 | pagination cost |
| `GET /api/admin/dashboard` | 10k modules | 8 | aggregation cost |
| `GET /api/source/jobs` | 100k jobs | 16 | list latency |
| job transitions | 100k jobs | 32 | claim/complete latency |
| soak mixed load | 10k modules | 6 h | drift and memory stability |

This baseline is sufficient to expose whether the current architecture is ready for a serious replacement narrative or still limited to team-scale deployments.
