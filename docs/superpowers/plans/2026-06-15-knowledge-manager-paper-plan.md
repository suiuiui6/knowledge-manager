# Knowledge Manager Paper Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `D:\tyh\knowledge-manager` into a submission-ready Chinese applied-paper package, with `PKU core / stronger general journal accepted` as the main outcome and `SCI Q4 accepted / major revision then accept` as the stretch add-on.

**Architecture:** Position the project as a Chinese application-oriented systems paper rather than a novelty-first AI paper. The paper's defensible claim is that a git-native, reviewed, structured knowledge-module system can support small-to-medium LLM workflows more effectively and more maintainably than chunk-only approaches. The execution path is evidence-first: freeze the claim, refresh the validation baseline, run a small-but-strong comparative experiment set, add a compact ablation and failure analysis package, then write the paper around proven results rather than writing around hopes.

**Tech Stack:** Python, pytest, MCP, markdown planning artifacts, existing `knowledge-manager` evaluation code, manually curated corpora, standard academic writing workflow

---

## Evidence Snapshot

**Current repo strengths already usable in the paper:**
- `knowledge-manager/README.md`
- `knowledge-manager/test-results/perf-run-production-gate-20260613-r16-matrix-summary.json`
- `knowledge-manager/test-results/llm-routing.md`
- `knowledge-manager/test-results/mcp-protocol.md`
- `knowledge-manager/test-results/test-summary.md`
- `knowledge-manager/src/knowledge_manager/extractor.py`
- `knowledge-manager/src/knowledge_manager/cli.py`
- `knowledge-manager/src/knowledge_manager/eval_runner.py`
- `knowledge-manager/src/knowledge_manager/retrieval_eval.py`
- `knowledge-manager/tests/test_eval_runner.py`
- `knowledge-manager/tests/test_retrieval_eval.py`
- `knowledge-manager/tests/test_llm.py`
- `knowledge-manager/tests/test_http_server.py`
- `knowledge-manager/docs/runbooks/enterprise-performance-test-plan.md`

**Current supported claims:**
- The system implements a real `extract -> review -> approve -> serve` workflow and exposes it through both CLI and MCP surfaces.
- The MCP path is not just conceptual: checked-in protocol testing shows `14/14` compliance tests passing against the MCP `2024-11-05` spec.
- The project now has stronger production-shape evidence than the old `2026-05-29` snapshot. The `2026-06-13` release-gate matrix reports `ready_for_production = true` at required `xs`, `s`, and `m` scales.
- Search and MCP retrieval latency are paper-usable engineering evidence: `search_http` is about `207/220 ms`, `371/381 ms`, and `405/414 ms` mean/p95 at `xs`, `s`, and `m`; `mcp_search_modules` is about `208/230 ms`, `477/487 ms`, and `594/625 ms`.
- The evaluation stack is substantially stronger than a hit-rate-only demo. Current code and tests support `first-hit rank`, `MRR`, `nDCG@k`, `recall@k`, `baseline win rate`, `false-positive/false-negative rate`, and `policy-vs-retrieval failure` decomposition.
- Extraction robustness is materially stronger than the old report suggests: the extractor now uses long-text chunking, a `4000`-character effective chunk cap, cross-chunk deduplication, JSON-retry logic, source-language preservation, and metadata-only verbose logging.
- There is bounded evidence that index-guided autonomous loading is useful. The checked-in routing report shows `4/5` scenario-level success on a real OAuth knowledge base, with no irrelevant over-loading.

**Current unsupported or weakly supported claims:**
- Fresh end-to-end narrative validation on a new, complex, real corpus is still missing. Most post-`2026-05-29` evidence is tests, gates, and seeded benchmark artifacts rather than a new paper-ready case study.
- General superiority over chunk-based RAG is still unproven until at least `2` real corpora and `2` serious baselines are compared under a judged-query setup.
- Large-document handling is improved, but not yet strong enough to claim blanket robustness without a dedicated long-document benchmark and saved outputs.
- Real-world autonomous agent utility in live conversations remains weakly evidenced; current routing proof is useful but still tiny and boundary-limited.
- Scale claims must stay bounded to `xs/s/m`. Current docs explicitly say not to claim `l` or `xl` readiness without dedicated artifacts.
- Strong algorithmic novelty is still not supported. The paper should remain architecture- and workflow-centered.

**Current risk notes from observed evidence:**
- The old `OAuth vs JWT` routing case still exposes a real boundary-detection weakness: the system lacks a strong signal for saying a topic is outside coverage.
- Troubleshooting-oriented retrieval is still weakly signaled because summaries and `caveats` are not yet consistently populated for debug scenarios.
- Some June benchmark artifacts still record `PermissionError` / `ToolError` entries on write-heavy or upload-like paths, so read/search claims are stronger than write-path claims.
- For paper use, we still need saved eval suites and checked-in `km eval run` outputs on representative real user queries rather than relying only on unit tests and release gates.
- Future formal experiments must run in a clean writable environment and save artifacts systematically; do not treat thread-local verification constraints as publishable evidence.

---

## Submission Strategy

### Route A: Stretch Target

**Label:** `SCI Q4 applied systems / software / information systems / knowledge engineering journal`

**This route is allowed only if all of these are true:**
- At least 3 real corpora are built and reported.
- At least 3 baseline systems are compared under a unified setup.
- Main metrics include `hit rate`, `first-hit rank`, `MRR`, `nDCG@k`, `recall@k`, latency, and context cost.
- At least 3 ablations are complete.
- Failure analysis is explicit and honest.
- Large-document handling is either improved or clearly bounded with measured evidence.

### Route B: Safer Target

**Label:** `PKU core / stronger general journal / stronger applied software or information journal`

**This route is viable if all of these are true:**
- The paper is framed as an applied system rather than algorithmic novelty.
- At least 2 real corpora are built and reported.
- At least 2 baseline systems are compared.
- Main retrieval metrics are reported formally.
- The paper includes at least one failure-analysis subsection.
- The system contribution is expressed in practical and architectural terms, not inflated claims.

### Routing Rule

- [ ] If baseline comparisons are weak or mixed, use `Route B`.
- [ ] If large-document robustness remains poor and no live agent utility study is added, use `Route B`.
- [ ] If the evidence base is still dominated by tests and release-gate artifacts rather than fresh judged-query experiments on real corpora, use `Route B`.
- [ ] If the system clearly beats baselines on multiple corpora and ablations validate the core design choices, evaluate `Route A` as a bonus.

---

## Paper Positioning

### Main Research Question

- [ ] Freeze the primary question as:
  `For small-to-medium team knowledge bases, does a reviewed structured knowledge-module workflow with MCP-based on-demand loading outperform chunk-only retrieval workflows for LLM-oriented engineering use?`

### Contribution Shape

- [ ] Lock the paper to `1 main contribution + 2 support contributions`.

**Main contribution:**
- [ ] A git-native, reviewed, structured knowledge-module system for LLM workflows.

**Support contribution 1:**
- [ ] A module-oriented retrieval and serving path using index-guided MCP loading.

**Support contribution 2:**
- [ ] A practical evaluation framework covering retrieval quality, context cost, workflow validation, and system failure modes.

### Claims to Avoid

- [ ] Do not claim the system replaces all RAG systems.
- [ ] Do not claim broad agent autonomy unless live agent routing is actually measured.
- [ ] Do not claim algorithmic novelty unless experiments show more than architectural integration.
- [ ] Do not claim robustness on long documents unless long-document benchmarks are repaired and reported.
- [ ] Do not overstate enterprise scope unless enterprise data is actually used.

---

## Proposed Titles

- [ ] `Knowledge Manager: A Git-Native MCP-Ready System for Structured Knowledge Modules`
- [ ] `Structured Knowledge Modules for LLM Workflows: Design and Validation of Knowledge Manager`
- [ ] `A Lightweight Knowledge Infrastructure for AI-Assisted Engineering Workflows`
- [ ] Chinese fallback title:
  `面向大语言模型工作流的结构化知识管理系统设计与实现`
- [ ] Chinese stronger academic variant:
  `面向小中规模团队知识库的结构化知识模块管理与按需加载方法`

---

## Dataset and Evaluation Plan

### Task 1: Freeze Real Corpora

**Files:**
- Read: `D:\tyh\knowledge-manager\README.md`
- Read: `D:\tyh\knowledge-manager\docs\validation-report-2026-05-29.md`
- Create: `D:\tyh\paper-assets\corpora\corpus-plan.md`
- Create: `D:\tyh\paper-assets\corpora\corpus-inventory.csv`

- [ ] **Step 1: Select corpus families**
  - Corpus A: architecture / engineering knowledge docs
  - Corpus B: ops / runbook / deployment docs
  - Corpus C: API / database / product technical docs

- [ ] **Step 2: Define minimum corpus size**
  - Minimum for `Route B`: `2 corpora`, `30-60 source documents or equivalent units`, `30-50 judged queries`
  - Minimum for `Route A`: `3 corpora`, `100+ source documents or equivalent units`, `100+ judged queries`

- [ ] **Step 3: Include one long-document-heavy corpus**
  - Purpose: directly evaluate the already-known long-document extraction weakness

- [ ] **Step 4: Record corpus metadata**
  - Source type
  - Document count
  - Total words
  - Average document length
  - Domain label
  - Whether docs are long-form

- [ ] **Step 5: Save corpus plan**
  - Save a single markdown file listing corpora, scope, and rationale

### Task 2: Build Judged Query Set

**Files:**
- Create: `D:\tyh\paper-assets\eval\query-guidelines.md`
- Create: `D:\tyh\paper-assets\eval\judged-queries.json`
- Read: `D:\tyh\knowledge-manager\src\knowledge_manager\eval_runner.py`

- [ ] **Step 1: Define query/task categories**
  - Factual retrieval
  - How-to / procedure
  - Decision / tradeoff
  - Risk / policy-sensitive
  - Cross-module synthesis

- [ ] **Step 2: Define annotation fields**
  - `query`
  - `required_modules`
  - `category`
  - `task_type`
  - `risk_level`
  - `notes`

- [ ] **Step 3: Build judging rules**
  - A module is required only if omitting it would materially weaken task completion
  - Distinguish `must load` from `nice to load`

- [ ] **Step 4: Set scale**
  - `Route B`: `30-50 judged queries`
  - `Route A`: `100+ judged queries`

- [ ] **Step 5: Label failure-oriented cases**
  - Short abbreviations
  - Synonyms
  - Broad ambiguous queries
  - Long-document-derived queries

---

## Baseline Plan

### Task 3: Freeze Baselines

**Files:**
- Read: `D:\tyh\knowledge-manager\src\knowledge_manager\eval_runner.py`
- Create: `D:\tyh\paper-assets\eval\baseline-plan.md`

- [ ] **Step 1: External baseline 1**
  - Raw-document keyword / BM25 retrieval baseline

- [ ] **Step 2: External baseline 2**
  - Chunked vector retrieval baseline

- [ ] **Step 3: External baseline 3**
  - Chunked hybrid RAG baseline

- [ ] **Step 4: Optional internal baseline**
  - Same system without human review, if the comparison is easy to run

- [ ] **Step 5: Baseline acceptance rule**
  - `Route B` requires at least 2 serious baselines
  - `Route A` requires at least 3 serious baselines

---

## Metric Plan

### Task 4: Freeze Metrics Before Running Experiments

**Files:**
- Read: `D:\tyh\knowledge-manager\src\knowledge_manager\retrieval_eval.py`
- Read: `D:\tyh\knowledge-manager\src\knowledge_manager\eval_runner.py`
- Create: `D:\tyh\paper-assets\eval\metric-plan.md`

- [ ] **Step 1: Retrieval quality metrics**
  - `hit rate`
  - `first-hit rank`
  - `MRR`
  - `nDCG@k`
  - `recall@k`

- [ ] **Step 2: Efficiency metrics**
  - Retrieval latency
  - End-to-end latency
  - Average context tokens

- [ ] **Step 3: Extraction metrics**
  - Extraction success rate
  - Mean modules per source
  - Acceptance rate after review
  - Module completeness score

- [ ] **Step 4: Application metrics**
  - Module review pass rate
  - Knowledge reuse rate
  - Time-to-locate-target-module
  - Manual search reduction
  - Maintenance cost proxy

- [ ] **Step 5: Optional safety/governance metrics**
  - Policy failure rate
  - Retrieval failure rate
  - Suppression-driven failure rate
  - Risky miss count or rate

- [ ] **Step 6: Reporting rule**
  - `Route B`: retrieval + efficiency + extraction + application metrics are mandatory
  - `Route A`: retrieval + efficiency + extraction + application metrics + at least one safety/governance slice are expected

---

## Core Experiment Plan

### Task 5: Minimal Publishable Experiment Pack

**Files:**
- Create: `D:\tyh\paper-assets\results\main-results.md`
- Create: `D:\tyh\paper-assets\results\main-results.csv`

- [ ] **Step 1: Run all systems on the judged query set**
- [ ] **Step 2: Produce one unified result table**
- [ ] **Step 3: Report corpus-wise breakdown**
- [ ] **Step 4: Report aggregate metrics**
- [ ] **Step 5: Compare context cost**

**Acceptance rule:**
- [ ] `Route B`: this is the minimum viable main experiment section
- [ ] `Route A`: this is necessary but not sufficient

### Task 6: Long-Document Benchmark

**Files:**
- Create: `D:\tyh\paper-assets\results\long-doc-benchmark.md`
- Create: `D:\tyh\paper-assets\results\long-doc-benchmark.csv`

- [ ] **Step 1: Build a size-bucket benchmark**
  - Short docs
  - Medium docs
  - Long docs

- [ ] **Step 2: Report extraction success and completeness by bucket**
- [ ] **Step 3: Report timeout or zero-module outcomes**
- [ ] **Step 4: If chunking or multi-pass fixes are implemented later, run before/after comparisons**

**Acceptance rule:**
- [ ] This benchmark is mandatory for both routes because the current repo evidence already exposes this weakness

### Task 7: Ablation Pack

**Files:**
- Create: `D:\tyh\paper-assets\results\ablation-results.md`
- Create: `D:\tyh\paper-assets\results\ablation-results.csv`

- [ ] **Step 1: Structured modules vs raw chunk retrieval**
- [ ] **Step 2: With review vs without review**
- [ ] **Step 3: Lexical-only vs lexical+vector fallback vs hybrid retrieval**
- [ ] **Step 4: Policy-aware retrieval on/off**

**Acceptance rule:**
- [ ] `Route B`: at least 1 to 2 ablations complete
- [ ] `Route A`: at least 3 ablations complete

### Task 8: Failure Analysis Pack

**Files:**
- Create: `D:\tyh\paper-assets\results\failure-analysis.md`

- [ ] **Step 1: Document short-query failures**
  - Example family: `auth`, abbreviations, shortened intent terms

- [ ] **Step 2: Document synonym failures**
- [ ] **Step 3: Document noisy broad-query hits**
- [ ] **Step 4: Document long-document extraction failures**
- [ ] **Step 5: Document empty-field / missing-link modules**
- [ ] **Step 6: Document policy-suppressed relevant hits if policy-aware evaluation is in scope**

**Acceptance rule:**
- [ ] A full failure taxonomy is mandatory for `Route A`
- [ ] A representative failure subsection is mandatory for `Route B`

### Task 9: End-to-End Utility Study

**Files:**
- Create: `D:\tyh\paper-assets\results\utility-study.md`

- [ ] **Step 1: Define task completion scenarios**
  - Answer generation
  - Module selection correctness
  - Cross-module synthesis

- [ ] **Step 2: Compare whether the system loads the right modules more often than baselines**
- [ ] **Step 3: Compare answer support quality where feasible**

**Acceptance rule:**
- [ ] `Route B`: strong plus, not strictly required if retrieval evidence is strong
- [ ] `Route A`: highly recommended; if absent, the paper must stay conservative about agent-level utility claims

---

## Writing Plan

### Task 10: Freeze Paper Story Before Drafting

**Files:**
- Create: `D:\tyh\paper-assets\writing\storyline.md`

- [ ] **Step 1: Lock the paper type**
  - Chinese applied systems paper first, SCI Q4 stretch second

- [ ] **Step 2: Lock the audience**
  - Researchers and practitioners in software systems, information systems, knowledge engineering, and LLM workflow tooling

- [ ] **Step 3: Lock the message**
  - For small-to-medium knowledge bases, structured reviewed modules may be a better operational substrate than chunk-only retrieval

- [ ] **Step 4: Lock the boundary**
  - Not a replacement for all large-scale RAG

### Task 11: Draft the Manuscript in This Order

**Files:**
- Create: `D:\tyh\paper-assets\writing\00-title-abstract.md`
- Create: `D:\tyh\paper-assets\writing\01-introduction.md`
- Create: `D:\tyh\paper-assets\writing\02-related-work.md`
- Create: `D:\tyh\paper-assets\writing\03-problem-setting.md`
- Create: `D:\tyh\paper-assets\writing\04-system-design.md`
- Create: `D:\tyh\paper-assets\writing\05-implementation.md`
- Create: `D:\tyh\paper-assets\writing\06-experimental-setup.md`
- Create: `D:\tyh\paper-assets\writing\07-results.md`
- Create: `D:\tyh\paper-assets\writing\08-ablation-failure-analysis.md`
- Create: `D:\tyh\paper-assets\writing\09-discussion-limitations.md`
- Create: `D:\tyh\paper-assets\writing\10-conclusion.md`

- [ ] **Step 1: Write `04-system-design.md` first**
- [ ] **Step 2: Write `05-implementation.md` second**
- [ ] **Step 3: Write `06-experimental-setup.md` third**
- [ ] **Step 4: Write `07-results.md` fourth**
- [ ] **Step 5: Write `08-ablation-failure-analysis.md` fifth**
- [ ] **Step 6: Write `01-introduction.md` only after results are stable**
- [ ] **Step 7: Write `02-related-work.md` after the final framing is stable**
- [ ] **Step 8: Write `00-title-abstract.md` near the end**

### Task 12: Figure and Table Pack

**Files:**
- Create: `D:\tyh\paper-assets\figures\figure-plan.md`

- [ ] **Step 1: Figure 1**
  - System architecture

- [ ] **Step 2: Figure 2**
  - Knowledge-module lifecycle: extract -> review -> approve -> load

- [ ] **Step 3: Table 1**
  - Module schema and field semantics

- [ ] **Step 4: Table 2**
  - Dataset statistics

- [ ] **Step 5: Table 3**
  - Main experimental comparison

- [ ] **Step 6: Table 4**
  - Ablation results

- [ ] **Step 7: Table 5**
  - Failure analysis examples

- [ ] **Step 8: Figure 3**
  - Performance / scale curve using measured rather than projected values when available

---

## Timeline

### Week 1

- [ ] Freeze the main research question
- [ ] Freeze contribution shape
- [ ] Freeze route criteria for `Route A` vs `Route B`
- [ ] Build corpus plan
- [ ] Build query annotation guidelines

### Week 2

- [ ] Collect and clean corpora
- [ ] Build judged query set
- [ ] Freeze baselines
- [ ] Freeze metrics
- [ ] Start related-work collection

### Week 3

- [ ] Run minimal publishable experiment pack
- [ ] Run long-document benchmark
- [ ] Start preliminary result tables

### Week 4

- [ ] Run ablations
- [ ] Run failure analysis
- [ ] Decide if end-to-end utility study is feasible

### Week 5

- [ ] Draft system design
- [ ] Draft implementation
- [ ] Draft experimental setup
- [ ] Draft results

### Week 6

- [ ] Draft failure analysis and discussion
- [ ] Draft introduction
- [ ] Draft related work
- [ ] Draft abstract and conclusion

### Week 7

- [ ] Internal review for claim inflation
- [ ] Cut unsupported claims
- [ ] Tighten tables and figures
- [ ] Choose provisional submission route

### Week 8

- [ ] If `Route A` thresholds are met, polish the SCI Q4 version
- [ ] If `Route A` thresholds are not met, reshape immediately into the stronger `Route B` manuscript
- [ ] Final reference cleanup
- [ ] Submission formatting

---

## Decision Gates

### Gate 1: After Week 3

- [ ] If there are still no serious external baselines, do not pretend `Route A` is active
- [ ] If corpora remain tiny or toy-like, do not submit anywhere yet

### Gate 2: After Week 4

- [ ] If ablations are incomplete, `Route A` is not ready
- [ ] If long-document results remain catastrophic and unexplained, `Route A` is not ready

### Gate 3: After Week 6

- [ ] If the paper still reads like a product description, reframe before submission
- [ ] If the results only show functionality and not comparative value, move to `Route B`

### Gate 4: Final Route Choice

- [ ] Choose `Route A` only if the paper has:
  - 3 corpora or equivalent strong evidence breadth
  - 3 baselines
  - 3 ablations
  - explicit failure analysis
  - strong or at least consistent advantages

- [ ] Choose `Route B` if the paper has:
  - 2 corpora
  - 2 baselines
  - formal metrics
  - one honest failure section
  - strong systems framing

---

## Review Risks to Check Before Submission

- [ ] `Novelty inflation risk`
  - Are we describing system integration as if it were a new retrieval theory?

- [ ] `Evidence inflation risk`
  - Are we claiming autonomy or robustness beyond measured evidence?

- [ ] `Scale mismatch risk`
  - Are we generalizing from toy corpora to broad production settings?

- [ ] `RAG strawman risk`
  - Are baselines fair and well implemented?

- [ ] `Boundary honesty risk`
  - Did we clearly state the method is best suited to small-to-medium knowledge bases?

---

## Final Recommendation

- [ ] Build everything to `Route B` evidence standards first.
- [ ] Decide submission route only after Week 6 evidence is visible.
- [ ] Treat `PKU core / stronger general journal` as the success floor, not the failure outcome.
- [ ] Treat `SCI Q4` as a stretch target that becomes realistic only when evidence breadth and rigor catch up with the system quality.
