# Enterprise Production Master Plan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `knowledge-manager` into a production-grade, industrial-grade, enterprise-grade knowledge operating system that enterprises can trust to ingest source systems, preserve provenance, enforce routing policy, operate safely, and continuously improve.

**Architecture:** Keep the existing git-native module model and extend it in layers: first harden source ingestion and provenance, then add governable routing and operator control loops, then complete enterprise trust boundaries and hybrid fallback. Every change remains file-based and inspectable, with optional enterprise capabilities implemented as isolated modules or plugins rather than forcing heavyweight infrastructure into the core.

**Tech Stack:** Python 3, pytest, existing CLI/HTTP/MCP surfaces, JSON/JSONL storage, optional OIDC/JWT validation libraries behind plugin boundaries, existing vector index scaffold.

---

## File Structure

### Existing files to extend
- `D:\tyh\knowledge-manager\src\knowledge_manager\schemas.py`
  Responsibility: canonical source/module/eval/auth schema definitions.
- `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
  Responsibility: persistence, retrieval, routing policy, ops reports, lifecycle transitions.
- `D:\tyh\knowledge-manager\src\knowledge_manager\source_ingestion.py`
  Responsibility: source pull orchestration, provenance stamping, sync state, invalidation.
- `D:\tyh\knowledge-manager\src\knowledge_manager\cli.py`
  Responsibility: operator entrypoints for source, eval, ops, auth, compliance workflows.
- `D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py`
  Responsibility: HTTP APIs for modules, ops, source state, auth-aware access, dual views.
- `D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py`
  Responsibility: agent-facing load/search/navigation surfaces and ops resources.
- `D:\tyh\knowledge-manager\src\knowledge_manager\auth.py`
  Responsibility: auth middleware, token validation, group extraction.
- `D:\tyh\knowledge-manager\src\knowledge_manager\audit.py`
  Responsibility: append-only audit trail and compliance export helpers.
- `D:\tyh\knowledge-manager\src\knowledge_manager\rbac.py`
  Responsibility: role mapping and scoped permission checks.
- `D:\tyh\knowledge-manager\src\knowledge_manager\eval_runner.py`
  Responsibility: benchmark execution, result decomposition, baseline comparison.
- `D:\tyh\knowledge-manager\src\knowledge_manager\vector_index.py`
  Responsibility: semantic fallback lookup under module-governed resolution.

### New files to create
- `D:\tyh\knowledge-manager\src\knowledge_manager\notion.py`
  Responsibility: read-only Notion connector normalized into the same source document shape as Confluence.
- `D:\tyh\knowledge-manager\src\knowledge_manager\policy.py`
  Responsibility: routing policy composition, validation, explanation formatting.
- `D:\tyh\knowledge-manager\src\knowledge_manager\ops_export.py`
  Responsibility: review backlog, risky misses, stale-source backlog, compliance bundle export formatting.
- `D:\tyh\knowledge-manager\src\knowledge_manager\dual_view.py`
  Responsibility: source graph <-> module graph projection and stale impact summaries.
- `D:\tyh\knowledge-manager\tests\test_notion.py`
  Responsibility: Notion connector normalization and retry coverage.
- `D:\tyh\knowledge-manager\tests\test_policy.py`
  Responsibility: routing policy merge, suppression, forced companion, explanation coverage.
- `D:\tyh\knowledge-manager\tests\test_ops_export.py`
  Responsibility: export payload, backlog shaping, dashboard counters.
- `D:\tyh\knowledge-manager\tests\test_dual_view.py`
  Responsibility: source/module projection and stale impact traversal.

## Delivery Stages

1. Foundation hardening
2. Enterprise ingestion platform
3. Provenance and lifecycle trust
4. Governable retrieval and control plane
5. Enterprise trust boundary
6. Dual view, hybrid fallback, and production rollout

### Task 1: Foundation Hardening For Safe Enterprise Expansion

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\source_ingestion.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\schemas.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_source_ingestion.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_schemas.py`

- [ ] **Step 1: Write the failing regression tests for partial sync merges and ingestion retries**

```python
def test_update_source_sync_merges_existing_sync_state(tmp_path):
    manager = SourceRegistry(tmp_path / ".sources")
    manager.save_source(
        SourceRecord(
            source_id="src-1",
            source_type="confluence",
            config={"base_url": "https://example.atlassian.net"},
            sync=SourceSyncState(
                last_cursor="cursor-1",
                last_synced_at="2026-06-12T00:00:00Z",
                page_versions={"123": "7"},
            ),
        )
    )

    manager.update_source_sync("src-1", SourceSyncState(last_error="timeout"))

    updated = manager.load_source("src-1")
    assert updated.sync.last_cursor == "cursor-1"
    assert updated.sync.page_versions == {"123": "7"}
    assert updated.sync.last_error == "timeout"


def test_pull_source_retries_only_transient_errors(tmp_path, monkeypatch):
    attempts = {"count": 0}

    class FlakyClient:
        def list_pages(self, *_args, **_kwargs):
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise RuntimeError("temporary failure")
            return []

    result = pull_source(..., client_factory=lambda *_: FlakyClient())

    assert result.pages_seen == 0
    assert attempts["count"] == 3
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_source_ingestion.py -k "merges_existing_sync_state or retries_only_transient_errors" -v`

Expected: `FAIL` because partial sync state is overwritten or retry behavior is incomplete.

- [ ] **Step 3: Implement minimal merge-safe sync state updates and explicit retry policy fields**

```python
def merge_sync_state(existing: SourceSyncState, patch: SourceSyncState) -> SourceSyncState:
    return SourceSyncState(
        last_cursor=patch.last_cursor if patch.last_cursor is not None else existing.last_cursor,
        last_synced_at=patch.last_synced_at if patch.last_synced_at is not None else existing.last_synced_at,
        last_error=patch.last_error if patch.last_error is not None else existing.last_error,
        page_versions=patch.page_versions or existing.page_versions,
    )


@dataclass
class PullRetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    retryable_errors: tuple[str, ...] = ("timeout", "temporary failure", "429")
```

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_source_ingestion.py -k "merges_existing_sync_state or retries_only_transient_errors" -v`

Expected: `2 passed`.

- [ ] **Step 5: Commit the foundation hardening slice**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\source_ingestion.py D:\tyh\knowledge-manager\src\knowledge_manager\schemas.py D:\tyh\knowledge-manager\tests\test_source_ingestion.py D:\tyh\knowledge-manager\tests\test_schemas.py
git commit -m "fix: harden source sync merge and retry policy"
```

### Task 2: Build A Real Connector Platform Beyond The First Flagship

**Files:**
- Create: `D:\tyh\knowledge-manager\src\knowledge_manager\notion.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\source_ingestion.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\cli.py`
- Create: `D:\tyh\knowledge-manager\tests\test_notion.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_cli.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_source_ingestion.py`

- [ ] **Step 1: Write the failing Notion connector and CLI tests**

```python
def test_notion_client_normalizes_pages():
    payload = {
        "results": [
            {
                "id": "page-1",
                "last_edited_time": "2026-06-10T08:00:00.000Z",
                "properties": {"title": {"title": [{"plain_text": "Runbook"}]}},
                "url": "https://www.notion.so/page-1",
            }
        ]
    }

    client = NotionClient(token="secret", database_id="db-1", session=FakeSession(payload))
    pages = client.list_pages()

    assert pages[0].source_id == "page-1"
    assert pages[0].title == "Runbook"
    assert pages[0].canonical_url == "https://www.notion.so/page-1"


def test_cli_source_add_notion_persists_registry(tmp_path):
    result = runner.invoke(
        cli,
        ["source", "add-notion", str(tmp_path), "--source-id", "ops", "--database-id", "db-1", "--token", "secret"],
    )
    assert result.exit_code == 0
    assert '"source_type": "notion"' in (tmp_path / ".sources" / "registry.json").read_text()
```

- [ ] **Step 2: Run the connector-focused tests to verify they fail**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_notion.py D:\tyh\knowledge-manager\tests\test_cli.py -k "notion" -v`

Expected: `FAIL` with `NotionClient` or CLI command missing.

- [ ] **Step 3: Implement normalized Notion listing and connector registration**

```python
class NotionClient:
    def __init__(self, token: str, database_id: str, session: Any | None = None) -> None:
        self._token = token
        self._database_id = database_id
        self._session = session or requests.Session()

    def list_pages(self, start_cursor: str | None = None) -> list[SourceDocument]:
        payload = self._session.post(...).json()
        return [self._normalize_page(item) for item in payload.get("results", [])]

    def _normalize_page(self, item: dict[str, Any]) -> SourceDocument:
        title_items = item.get("properties", {}).get("title", {}).get("title", [])
        title = "".join(piece.get("plain_text", "") for piece in title_items).strip() or item["id"]
        return SourceDocument(
            source_id=item["id"],
            title=title,
            body="",
            canonical_url=item.get("url", ""),
            updated_at=item.get("last_edited_time"),
            metadata={"source_type": "notion"},
        )
```

- [ ] **Step 4: Run the connector-focused tests to verify they pass**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_notion.py D:\tyh\knowledge-manager\tests\test_cli.py -k "notion" -v`

Expected: all Notion-focused tests `PASS`.

- [ ] **Step 5: Commit the connector platform slice**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\notion.py D:\tyh\knowledge-manager\src\knowledge_manager\source_ingestion.py D:\tyh\knowledge-manager\src\knowledge_manager\cli.py D:\tyh\knowledge-manager\tests\test_notion.py D:\tyh\knowledge-manager\tests\test_cli.py D:\tyh\knowledge-manager\tests\test_source_ingestion.py
git commit -m "feat: add notion ingestion connector"
```

### Task 3: Harden Provenance, Version Chains, And Source-Change Impact

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\schemas.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\source_ingestion.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_schemas.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_storage.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_source_ingestion.py`

- [ ] **Step 1: Write failing tests for supersession, derived lineage, and source impact invalidation**

```python
def test_module_metadata_tracks_supersedes_and_derived_from(tmp_path):
    storage = KnowledgeStorage(tmp_path)
    old_id = storage.create_module({"title": "Policy v1", "category": "policy"})
    new_id = storage.create_module({"title": "Policy v2", "category": "policy", "supersedes": [old_id]})

    module = storage.load_module(new_id)
    assert module.supersedes == [old_id]
    assert old_id in storage.get_supersession_chain(new_id)


def test_mark_source_change_flags_dependent_modules_stale(tmp_path):
    storage = KnowledgeStorage(tmp_path)
    module_id = storage.create_module(
        {"title": "Runbook", "category": "ops", "source_documents": [{"source_id": "page-1", "version": "3"}]}
    )

    affected = storage.mark_source_documents_changed({"page-1": "4"})

    assert affected == [module_id]
    assert storage.load_module(module_id).stale_due_to_source_change is True
```

- [ ] **Step 2: Run the provenance tests to verify they fail**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_schemas.py D:\tyh\knowledge-manager\tests\test_storage.py -k "supersedes or source_change" -v`

Expected: `FAIL` because lineage helpers and stale impact traversal are incomplete.

- [ ] **Step 3: Implement provenance graph fields and stale impact helpers**

```python
class ModuleRecord(BaseModel):
    ...
    source_documents: list[SourceDocumentRef] = Field(default_factory=list)
    source_spans: list[SourceSpan] = Field(default_factory=list)
    extraction_run_id: str | None = None
    derived_from: list[str] = Field(default_factory=list)
    supersedes: list[str] = Field(default_factory=list)
    stale_due_to_source_change: bool = False


def mark_source_documents_changed(self, versions: dict[str, str]) -> list[str]:
    affected: list[str] = []
    for module in self.iter_modules(include_archived=True):
        if any(ref.source_id in versions and ref.version != versions[ref.source_id] for ref in module.source_documents):
            module.stale_due_to_source_change = True
            self.save_module(module)
            affected.append(module.id)
    return affected
```

- [ ] **Step 4: Run the provenance tests to verify they pass**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_schemas.py D:\tyh\knowledge-manager\tests\test_storage.py D:\tyh\knowledge-manager\tests\test_source_ingestion.py -k "supersedes or source_change" -v`

Expected: all provenance-focused tests `PASS`.

- [ ] **Step 5: Commit the provenance trust slice**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\schemas.py D:\tyh\knowledge-manager\src\knowledge_manager\storage.py D:\tyh\knowledge-manager\src\knowledge_manager\source_ingestion.py D:\tyh\knowledge-manager\tests\test_schemas.py D:\tyh\knowledge-manager\tests\test_storage.py D:\tyh\knowledge-manager\tests\test_source_ingestion.py
git commit -m "feat: add module lineage and source impact tracking"
```

### Task 4: Externalize Governable Routing Into A Policy Engine

**Files:**
- Create: `D:\tyh\knowledge-manager\src\knowledge_manager\policy.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py`
- Create: `D:\tyh\knowledge-manager\tests\test_policy.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_storage.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_mcp_server.py`

- [ ] **Step 1: Write failing tests for policy layering, invalid suppression, and forced companions**

```python
def test_policy_merge_applies_workspace_then_agent_override():
    policy = merge_routing_policy(
        workspace={"risk_level_defaults": {"high": {"required_categories": ["policy"]}}},
        agent={"risk_level_defaults": {"high": {"required_categories": ["policy", "security"]}}},
    )
    assert policy["risk_level_defaults"]["high"]["required_categories"] == ["policy", "security"]


def test_search_results_explain_policy_suppression(tmp_path):
    storage = KnowledgeStorage(tmp_path)
    ...
    result = storage.search_modules("deploy secret rotation", risk_level="high", agent_id="ops-agent")
    assert "suppressed_by_policy" in result.explanations[0]
    assert "mandatory_companions" in result.explanations[0]
```

- [ ] **Step 2: Run the policy tests to verify they fail**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_policy.py D:\tyh\knowledge-manager\tests\test_storage.py D:\tyh\knowledge-manager\tests\test_mcp_server.py -k "policy or suppression or companions" -v`

Expected: `FAIL` because the dedicated policy engine and richer explanations do not exist yet.

- [ ] **Step 3: Implement reusable routing policy composition and explanation formatting**

```python
def evaluate_routing_policy(policy: RoutingPolicy, module: ModuleRecord, context: RoutingContext) -> PolicyDecision:
    if module.status in policy.blocked_statuses:
        return PolicyDecision(allowed=False, reasons=["blocked_status"])
    if module.stale_due_to_source_change and policy.suppress_stale:
        return PolicyDecision(allowed=False, reasons=["stale_source_change"])
    companions = policy.required_companions_by_category.get(module.category, [])
    return PolicyDecision(allowed=True, reasons=["eligible"], mandatory_companions=companions)


def format_policy_explanation(decision: PolicyDecision) -> dict[str, Any]:
    return {
        "allowed": decision.allowed,
        "reasons": decision.reasons,
        "mandatory_companions": decision.mandatory_companions,
    }
```

- [ ] **Step 4: Run the policy tests to verify they pass**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_policy.py D:\tyh\knowledge-manager\tests\test_storage.py D:\tyh\knowledge-manager\tests\test_mcp_server.py -k "policy or suppression or companions" -v`

Expected: policy-focused tests `PASS`.

- [ ] **Step 5: Commit the governable routing slice**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\policy.py D:\tyh\knowledge-manager\src\knowledge_manager\storage.py D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py D:\tyh\knowledge-manager\tests\test_policy.py D:\tyh\knowledge-manager\tests\test_storage.py D:\tyh\knowledge-manager\tests\test_mcp_server.py
git commit -m "feat: extract governable routing policy engine"
```

### Task 5: Build The Knowledge Ops Control Plane

**Files:**
- Create: `D:\tyh\knowledge-manager\src\knowledge_manager\ops_export.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\cli.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py`
- Create: `D:\tyh\knowledge-manager\tests\test_ops_export.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_cli.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_http_server.py`

- [ ] **Step 1: Write failing tests for review backlog, risky misses, and stale-source backlog exports**

```python
def test_generate_ops_exports_includes_stale_source_backlog(tmp_path):
    storage = KnowledgeStorage(tmp_path)
    ...
    export = generate_review_backlog_export(storage)
    assert export["stale_sources"][0]["source_id"] == "confluence-ops"


def test_cli_ops_export_risky_misses_writes_json(tmp_path):
    result = runner.invoke(cli, ["ops-export-risky-misses", str(tmp_path / "misses.json")])
    assert result.exit_code == 0
    assert json.loads((tmp_path / "misses.json").read_text())["items"] == []
```

- [ ] **Step 2: Run the ops export tests to verify they fail**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_ops_export.py D:\tyh\knowledge-manager\tests\test_cli.py D:\tyh\knowledge-manager\tests\test_http_server.py -k "backlog or risky_misses" -v`

Expected: `FAIL` because export helpers and endpoints are missing.

- [ ] **Step 3: Implement export helpers and operator surfaces**

```python
def generate_risky_miss_export(storage: KnowledgeStorage) -> dict[str, Any]:
    report = storage.generate_ops_report()
    return {
        "generated_at": utc_now(),
        "items": report["queries_with_zero_high_confidence_hits"],
        "summary": {"count": len(report["queries_with_zero_high_confidence_hits"])},
    }


@app.get("/api/ops/backlog")
def get_ops_backlog() -> dict[str, Any]:
    return generate_review_backlog_export(storage)
```

- [ ] **Step 4: Run the ops export tests to verify they pass**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_ops_export.py D:\tyh\knowledge-manager\tests\test_cli.py D:\tyh\knowledge-manager\tests\test_http_server.py -k "backlog or risky_misses" -v`

Expected: ops export tests `PASS`.

- [ ] **Step 5: Commit the ops control plane slice**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\ops_export.py D:\tyh\knowledge-manager\src\knowledge_manager\storage.py D:\tyh\knowledge-manager\src\knowledge_manager\cli.py D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py D:\tyh\knowledge-manager\tests\test_ops_export.py D:\tyh\knowledge-manager\tests\test_cli.py D:\tyh\knowledge-manager\tests\test_http_server.py
git commit -m "feat: add ops exports and backlog control plane"
```

### Task 6: Make Eval A Real Deployment Gate Instead Of A Smoke Check

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\eval_runner.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\schemas.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\cli.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_eval_runner.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_cli.py`

- [ ] **Step 1: Write failing tests for baseline comparison, false-positive/false-negative accounting, and budget tracking**

```python
def test_eval_run_reports_baseline_delta_and_budget_usage():
    result = run_eval_suite(
        ...,
        baseline_results={"case-1": {"required_hit": False, "tokens": 1800}},
    )
    assert result.summary.baseline_win_rate == 1.0
    assert result.summary.false_negative_rate == 0.0
    assert result.summary.avg_context_tokens == 900


def test_cli_eval_run_prints_failure_decomposition(tmp_path):
    result = runner.invoke(cli, ["eval", "run", str(tmp_path), "--cases", "cases.json"])
    assert "policy_failures=" in result.output
    assert "retrieval_failures=" in result.output
```

- [ ] **Step 2: Run the eval tests to verify they fail**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_eval_runner.py D:\tyh\knowledge-manager\tests\test_cli.py -k "baseline or false_negative or policy_failures" -v`

Expected: `FAIL` because the richer metrics and CLI reporting are missing.

- [ ] **Step 3: Implement baseline delta and failure decomposition**

```python
class EvalRunSummary(BaseModel):
    success_rate: float
    baseline_win_rate: float
    false_positive_rate: float
    false_negative_rate: float
    avg_context_tokens: int
    policy_failure_rate: float
    retrieval_failure_rate: float


def classify_eval_failure(case: EvalCaseResult) -> str:
    if case.policy_suppressed_modules and not case.required_modules_loaded:
        return "policy"
    if not case.required_modules_loaded:
        return "retrieval"
    return "none"
```

- [ ] **Step 4: Run the eval tests to verify they pass**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_eval_runner.py D:\tyh\knowledge-manager\tests\test_cli.py -k "baseline or false_negative or policy_failures" -v`

Expected: eval-focused tests `PASS`.

- [ ] **Step 5: Commit the eval gate slice**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\eval_runner.py D:\tyh\knowledge-manager\src\knowledge_manager\schemas.py D:\tyh\knowledge-manager\src\knowledge_manager\cli.py D:\tyh\knowledge-manager\tests\test_eval_runner.py D:\tyh\knowledge-manager\tests\test_cli.py
git commit -m "feat: turn eval into deployment gate"
```

### Task 7: Complete Enterprise Auth, Audit, And Scoped RBAC

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\auth.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\audit.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\rbac.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\cli.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_enterprise.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_http_server.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_cli.py`

- [ ] **Step 1: Write failing tests for signed JWT validation, group-role mapping, scoped module access, and audit separation**

```python
def test_validate_oidc_token_rejects_unsigned_payload():
    with pytest.raises(AuthError):
        validate_oidc_token("header.payload.", issuer="https://issuer.example.com", jwks={"keys": []})


def test_rbac_enforces_category_scope():
    checker = PermissionChecker(
        roles={"reviewer": {"permissions": ["module:read"], "scopes": ["category:policy"]}},
        group_mapping={"grp-reviewers": ["reviewer"]},
    )
    assert checker.can_read_module(["grp-reviewers"], {"category": "policy"}) is True
    assert checker.can_read_module(["grp-reviewers"], {"category": "finance"}) is False
```

- [ ] **Step 2: Run the enterprise auth tests to verify they fail**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_enterprise.py D:\tyh\knowledge-manager\tests\test_http_server.py D:\tyh\knowledge-manager\tests\test_cli.py -k "oidc or rbac or audit" -v`

Expected: `FAIL` because token signature validation and scoped permission checks are incomplete.

- [ ] **Step 3: Implement signature-checked OIDC, scoped RBAC, and append-only audit export**

```python
def validate_oidc_token(raw_token: str, issuer: str, jwks: dict[str, Any], audience: str | None = None) -> dict[str, Any]:
    header = jwt.get_unverified_header(raw_token)
    signing_key = find_signing_key(header["kid"], jwks)
    return jwt.decode(raw_token, signing_key, algorithms=["RS256"], issuer=issuer, audience=audience)


def can_access_module(self, claims: dict[str, Any], module: ModuleRecord, action: str) -> bool:
    roles = self.resolve_roles(claims.get("groups", []))
    return any(self._role_allows(role, module, action) for role in roles)
```

- [ ] **Step 4: Run the enterprise auth tests to verify they pass**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_enterprise.py D:\tyh\knowledge-manager\tests\test_http_server.py D:\tyh\knowledge-manager\tests\test_cli.py -k "oidc or rbac or audit" -v`

Expected: enterprise trust tests `PASS`.

- [ ] **Step 5: Commit the enterprise trust slice**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\auth.py D:\tyh\knowledge-manager\src\knowledge_manager\audit.py D:\tyh\knowledge-manager\src\knowledge_manager\rbac.py D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py D:\tyh\knowledge-manager\src\knowledge_manager\cli.py D:\tyh\knowledge-manager\tests\test_enterprise.py D:\tyh\knowledge-manager\tests\test_http_server.py D:\tyh\knowledge-manager\tests\test_cli.py
git commit -m "feat: harden auth audit and scoped rbac"
```

### Task 8: Expose Dual Source/Module Views And Hybrid Retrieval Fallback

**Files:**
- Create: `D:\tyh\knowledge-manager\src\knowledge_manager\dual_view.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\vector_index.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py`
- Create: `D:\tyh\knowledge-manager\tests\test_dual_view.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_http_server.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_mcp_server.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_watch_vector.py`

- [ ] **Step 1: Write failing tests for dual-view projection and fallback-to-module resolution**

```python
def test_dual_view_projects_sources_to_modules(tmp_path):
    storage = KnowledgeStorage(tmp_path)
    ...
    view = build_dual_view(storage)
    assert view["sources"][0]["module_ids"] == ["mod-1"]
    assert view["modules"][0]["source_ids"] == ["page-1"]


def test_vector_fallback_returns_module_resolution_not_raw_chunk(tmp_path):
    storage = KnowledgeStorage(tmp_path)
    result = storage.search_modules("legacy acronym query", enable_vector_fallback=True)
    assert result.results[0].source == "vector_fallback"
    assert result.results[0].module_id is not None
```

- [ ] **Step 2: Run the dual-view and fallback tests to verify they fail**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_dual_view.py D:\tyh\knowledge-manager\tests\test_http_server.py D:\tyh\knowledge-manager\tests\test_mcp_server.py D:\tyh\knowledge-manager\tests\test_watch_vector.py -k "dual_view or vector_fallback" -v`

Expected: `FAIL` because the graph projection and module-resolved fallback are incomplete.

- [ ] **Step 3: Implement source/module graph projection and controlled vector fallback**

```python
def build_dual_view(storage: KnowledgeStorage) -> dict[str, Any]:
    modules = list(storage.iter_modules(include_archived=True))
    return {
        "sources": project_sources(modules, storage.list_sources()),
        "modules": project_modules(modules),
        "stale_edges": project_stale_edges(modules),
    }


def resolve_vector_hit_to_module(self, hit: VectorHit) -> SearchResult | None:
    candidates = self.find_modules_by_source_reference(hit.document_id)
    if not candidates:
        return None
    return SearchResult(module_id=candidates[0].id, source="vector_fallback", score=hit.score)
```

- [ ] **Step 4: Run the dual-view and fallback tests to verify they pass**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_dual_view.py D:\tyh\knowledge-manager\tests\test_http_server.py D:\tyh\knowledge-manager\tests\test_mcp_server.py D:\tyh\knowledge-manager\tests\test_watch_vector.py -k "dual_view or vector_fallback" -v`

Expected: dual-view and fallback tests `PASS`.

- [ ] **Step 5: Commit the differentiator slice**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\dual_view.py D:\tyh\knowledge-manager\src\knowledge_manager\storage.py D:\tyh\knowledge-manager\src\knowledge_manager\vector_index.py D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py D:\tyh\knowledge-manager\tests\test_dual_view.py D:\tyh\knowledge-manager\tests\test_http_server.py D:\tyh\knowledge-manager\tests\test_mcp_server.py D:\tyh\knowledge-manager\tests\test_watch_vector.py
git commit -m "feat: add dual knowledge view and module-first vector fallback"
```

### Task 9: Production Readiness Gate, Docs, And Release Evidence

**Files:**
- Modify: `D:\tyh\knowledge-manager\README.md`
- Modify: `D:\tyh\knowledge-manager\docs\superpowers\specs\2026-06-09-m13-enterprise.md`
- Create: `D:\tyh\knowledge-manager\docs\runbooks\enterprise-rollout.md`
- Create: `D:\tyh\knowledge-manager\docs\runbooks\eval-gate.md`
- Modify: `D:\tyh\knowledge-manager\tests\test_integration.py`

- [ ] **Step 1: Write failing integration tests that represent the production gate**

```python
def test_enterprise_ingest_route_eval_operate_flow(tmp_path):
    kb = tmp_path / "kb"
    ...
    pull = runner.invoke(cli, ["source", "pull", str(kb), "--source-id", "ops"])
    eval_run = runner.invoke(cli, ["eval", "run", str(kb), "--cases", str(cases_path)])
    ops = runner.invoke(cli, ["ops", str(kb)])

    assert pull.exit_code == 0
    assert "baseline_win_rate" in eval_run.output
    assert "stale_sources" in ops.output
```

- [ ] **Step 2: Run the integration gate to verify it fails before docs and final wiring are complete**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_integration.py -k "enterprise_ingest_route_eval_operate_flow" -v`

Expected: `FAIL` until all end-to-end surfaces align.

- [ ] **Step 3: Write rollout docs and final integration wiring**

```markdown
# Enterprise Rollout

1. Configure source connectors with least-privilege credentials.
2. Run `km source pull <kb> --source-id <id>` until source registry is green.
3. Run `km eval run <kb> --cases <file>` and require `baseline_win_rate >= 0.7`.
4. Review `km ops <kb>` for stale sources, risky misses, and backlog size.
5. Enable HTTP auth middleware only after signed token validation passes in staging.
```

- [ ] **Step 4: Run the full enterprise verification sweep**

Run: `PYTHONPATH=D:\tyh\knowledge-manager\src python -m pytest D:\tyh\knowledge-manager\tests\test_schemas.py D:\tyh\knowledge-manager\tests\test_storage.py D:\tyh\knowledge-manager\tests\test_http_server.py D:\tyh\knowledge-manager\tests\test_mcp_server.py D:\tyh\knowledge-manager\tests\test_cli.py D:\tyh\knowledge-manager\tests\test_source_ingestion.py D:\tyh\knowledge-manager\tests\test_confluence.py D:\tyh\knowledge-manager\tests\test_notion.py D:\tyh\knowledge-manager\tests\test_policy.py D:\tyh\knowledge-manager\tests\test_ops_export.py D:\tyh\knowledge-manager\tests\test_eval_runner.py D:\tyh\knowledge-manager\tests\test_enterprise.py D:\tyh\knowledge-manager\tests\test_dual_view.py D:\tyh\knowledge-manager\tests\test_watch_vector.py D:\tyh\knowledge-manager\tests\test_integration.py -q`

Expected: full targeted enterprise suite `PASS`, with only pre-existing non-fatal dependency warnings allowed.

- [ ] **Step 5: Commit the release gate slice**

```bash
git add D:\tyh\knowledge-manager\README.md D:\tyh\knowledge-manager\docs\superpowers\specs\2026-06-09-m13-enterprise.md D:\tyh\knowledge-manager\docs\runbooks\enterprise-rollout.md D:\tyh\knowledge-manager\docs\runbooks\eval-gate.md D:\tyh\knowledge-manager\tests\test_integration.py
git commit -m "docs: add enterprise rollout and release gates"
```

## Release Exit Criteria

- Enterprise connectors support at least Confluence and Notion with incremental sync, retry visibility, and source-level status.
- Every published module can be traced to source documents, source spans, extraction run identity, and supersession lineage.
- Search/load results include enforceable routing-policy explanations, stale suppression, and mandatory-companion behavior.
- Operators can export stale-source backlog, risky misses, and review queues from CLI, HTTP, and MCP.
- Eval runs compare against a baseline and split misses into policy failures versus retrieval failures.
- OIDC validation checks signatures; RBAC supports group-to-role mapping plus category/module scopes; audit trails remain append-only.
- Source view and module view are both available, and semantic fallback resolves back to governed modules rather than raw chunks.
- Rollout documentation and integration tests provide a repeatable production gate.

## Self-Review

### Spec coverage
- `2026-06-09-m13-enterprise.md`: covered by Task 7 and Task 9 for SSO, audit, RBAC, and compliance-adjacent rollout/reporting.
- `2026-06-11-rag-migration-barriers-design.md`: P0 ingestion/provenance/routing are covered by Tasks 1-4; P1 ops/eval/auth are covered by Tasks 5-7; P2 dual view/hybrid fallback are covered by Task 8; production replacement posture is closed by Task 9.
- Existing implemented state is respected: this plan assumes Confluence, source registry, basic eval, ops report, and current routing scaffolding already exist and hardens them rather than restarting them.

### Placeholder scan
- No `TODO`, `TBD`, or “implement later” markers remain.
- Each task includes exact file paths, code snippets, commands, and expected outcomes.

### Type consistency
- `SourceSyncState`, `SourceDocument`, `ModuleRecord`, `RoutingPolicy`, `PolicyDecision`, and eval summary names are used consistently across tasks.
- Dual-view and vector fallback both resolve through module IDs, matching the module-first product thesis.
