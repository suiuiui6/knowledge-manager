# Production-Grade Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `knowledge-manager` from its current feature-rich beta / 准生产级 state to a real production-grade single-node deployment baseline by first closing P0 security and isolation blockers, then finishing P1 durability, auditability, and release-operability work.

**Architecture:** Keep the current git-native, file-backed architecture. Do not introduce a database, Redis, Celery, or a distributed queue in this plan. Instead, harden the existing system in layers: derive request identity and tenant scope from authentication, make HTTP and MCP read/write surfaces safe by default, disable unsafe MCP resource exposure in multi-tenant mode, upgrade readiness to check runtime truth, and separate API enqueue from worker execution before production upload/source-sync cutover.

**Tech Stack:** Python 3.10+, FastAPI, FastMCP, Click, pytest, JSON/JSONL storage, existing `auth` / `rbac` / `tenancy` / `ingestion_jobs` / `job_worker` / `runtime_checks` modules, file-backed caches, materialized views, benchmark artifacts under `test-results/`.

---

## Real Current State This Plan Must Respect

The current repo already has meaningful production-shaped traits:

- packaged source layout via `pyproject.toml`
- broad test coverage across HTTP, MCP, storage, enterprise, and benchmark flows
- existing readiness, integrity, metrics, benchmark, and audit concepts
- useful runbooks and performance artifacts under `docs/runbooks/` and `test-results/`

The verified blockers from the audit and follow-up review are:

- HTTP authentication exists, but actual write/control-plane authorization is not enforced. `request.state.user` is populated when auth is enabled, but write and operator routes do not consume it for RBAC decisions.
- `auth.json` missing currently means anonymous pass-through. That is acceptable for local development, but not for production.
- Tenant scope is currently client-controlled on several surfaces. `/api/modules`, `/api/modules/{...}`, and `/api/search` accept `tenant_id` directly from query/body. In production, that is not a trustworthy isolation boundary.
- Data-plane tenant filtering is partial: `/api/index`, `/api/tree`, `/api/graph`, `/api/recommendations`, and related aggregate views do not currently enforce tenant scope.
- Control-plane endpoints are more seriously incomplete: `/api/staging`, `/api/ops*`, `/api/dual-view`, `/api/source/jobs`, and `/api/admin/dashboard` lack both tenant scope and admin/RBAC gating.
- HTTP staging approval/rejection trusts `reviewer` from the request body today, so reviewer identity can be forged.
- MCP resources are globally readable today and do not carry request auth context. In multi-tenant production mode, that is a P0 leak even if HTTP is fixed.
- Some MCP tools accept `tenant_id`, but they still trust caller-supplied tenant values. Others such as `knowledge_graph`, `expand_module`, and `deep_search` do not consistently apply tenant scope.
- `ModuleCache` currently keys only on `namespace + module_id`, so same-ID modules in different categories can collide and return cross-category data.
- Upload and deferred maintenance still depend on daemon threads inside the API process. That is not durable enough for production cutover if `/api/upload` or source sync are enabled.
- `/api/ready` exists, but it only checks config/default provider/index presence. It does not fail on auth misconfiguration in production mode, failed jobs, expired leases, maintenance backlog, or integrity drift.
- `updated_at` freshness is unreliable because the HTTP update flow only refreshes it during metadata updates, not for title/summary/content mutations.
- The benchmark matrix summary is per-scale (`xs`, `s`, `m`) rather than a single top-level release verdict. Any production gate script must evaluate all required scales, not a non-existent root verdict.
- The repo already has `audit.py`, but HTTP/MCP security-sensitive actions are not consistently written to that audit stream with `tenant_id`, `resource`, `request_id`, and `result`.

## Production Outcome For This Repo

For this repo's current architecture, "production-grade" means all of the following are true at the same time:

- `production_mode=true` is fail-closed for auth-sensitive behavior: missing auth config fails readiness and refuses write/control-plane traffic.
- request tenant scope comes from the authenticated subject by default, not from arbitrary query/body parameters.
- tenant override inputs remain possible only for admins or explicitly authorized operators, and every override is checked and audited.
- every mutable HTTP/API control-plane path enforces authentication plus explicit RBAC.
- all knowledge read surfaces are either tenant-scoped or intentionally admin-only.
- multi-tenant MCP mode does not expose global `knowledge://...` resources without trusted tenant context.
- MCP surfaces cannot leak cross-tenant data through global resources or same-ID cache collisions.
- upload/source jobs either run through a dedicated worker service or are not enabled for production traffic.
- readiness reflects runtime truth: auth health, integrity, failed/stale jobs, backlog thresholds, and benchmark verdicts.
- release evidence is reproducible from one verification command that combines readiness, integrity, and all required benchmark scales.
- audit logs can explain who changed what, under which tenant, against which resource, with which result and request ID.

## File Structure

### Existing files to extend

- `D:\tyh\knowledge-manager\src\knowledge_manager\auth.py`
  Responsibility: auth config loading, token/OIDC validation, request auth subject population.
- `D:\tyh\knowledge-manager\src\knowledge_manager\rbac.py`
  Responsibility: role mapping and permission checks.
- `D:\tyh\knowledge-manager\src\knowledge_manager\tenancy.py`
  Responsibility: tenant visibility rules and tenant override checks.
- `D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py`
  Responsibility: FastAPI routes, request middleware, data/control-plane endpoints, upload enqueue.
- `D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py`
  Responsibility: MCP resources and tools.
- `D:\tyh\knowledge-manager\src\knowledge_manager\cache.py`
  Responsibility: MCP per-module cache.
- `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
  Responsibility: persistence, projections, recommendations, ops data, freshness semantics.
- `D:\tyh\knowledge-manager\src\knowledge_manager\runtime_checks.py`
  Responsibility: readiness, integrity, metrics, repair.
- `D:\tyh\knowledge-manager\src\knowledge_manager\ingestion_jobs.py`
  Responsibility: durable ingestion job state and recovery metadata.
- `D:\tyh\knowledge-manager\src\knowledge_manager\job_worker.py`
  Responsibility: running queued ingestion and maintenance work.
- `D:\tyh\knowledge-manager\src\knowledge_manager\source_ingestion.py`
  Responsibility: source registry and source-sync orchestration.
- `D:\tyh\knowledge-manager\src\knowledge_manager\admin_views.py`
  Responsibility: admin dashboard aggregation.
- `D:\tyh\knowledge-manager\src\knowledge_manager\ops_export.py`
  Responsibility: export shaping for review/source/risky-miss backlogs.
- `D:\tyh\knowledge-manager\src\knowledge_manager\audit.py`
  Responsibility: append/read audit log events.
- `D:\tyh\knowledge-manager\src\knowledge_manager\performance_benchmarks.py`
  Responsibility: benchmark report generation and release verdict calculation.
- `D:\tyh\knowledge-manager\src\knowledge_manager\cli.py`
  Responsibility: operator commands, worker entrypoint, release verification command.
- `D:\tyh\knowledge-manager\src\knowledge_manager\schemas.py`
  Responsibility: config schemas, source/job ownership fields, security configuration.
- `D:\tyh\knowledge-manager\tests\test_http_server.py`
- `D:\tyh\knowledge-manager\tests\test_enterprise.py`
- `D:\tyh\knowledge-manager\tests\test_mcp_server.py`
- `D:\tyh\knowledge-manager\tests\test_cache.py`
- `D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py`
- `D:\tyh\knowledge-manager\tests\test_runtime_checks.py`
- `D:\tyh\knowledge-manager\tests\test_storage.py`
- `D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py`
- `D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md`
- `D:\tyh\knowledge-manager\docs\runbooks\enterprise-performance-test-plan.md`

### New files to create

- `D:\tyh\knowledge-manager\src\knowledge_manager\http_authz.py`
  Responsibility: request identity resolution, auth fail-closed checks, tenant-scope resolution, HTTP permission guards.
- `D:\tyh\knowledge-manager\src\knowledge_manager\tenant_views.py`
  Responsibility: tenant-filtered index/tree/graph/recommendation/admin projections reused across HTTP and MCP.
- `D:\tyh\knowledge-manager\src\knowledge_manager\worker_service.py`
  Responsibility: queue polling, stale-job recovery, worker heartbeat loop outside the API thread.
- `D:\tyh\knowledge-manager\tests\test_worker_service.py`
  Responsibility: worker loop, stale-job recovery, enqueue-only HTTP behavior.
- `D:\tyh\knowledge-manager\tests\test_audit.py`
  Responsibility: audit event shape, request ID propagation, denial logging.
- `D:\tyh\knowledge-manager\scripts\verify_production_readiness.py`
  Responsibility: one-command release verification across readiness, integrity, and required benchmark scales.

## Delivery Stages

1. `P0` Close production-blocking auth, tenancy, MCP, cache, readiness, and freshness gaps.
2. `P0` Add acceptance-grade release verification and rollout sequencing so production claims are evidence-backed.
3. `P1` Finish durable worker split, audit enrichment, and operator runbook hardening.

## Priority Map

### `P0` Release Blockers

- Task 1: fail-closed auth, HTTP RBAC, reviewer anti-spoofing
- Task 2: auth-derived tenant scope across HTTP data/control plane
- Task 3: MCP resource lockdown plus cache key migration
- Task 4: truthful readiness, freshness, multi-scale release verification

### `P1` Production Enhancements

- Task 5: durable worker split and stale queue recovery
- Task 6: auditability, release sequencing, and runbook/performance governance

`Task 5` must be promoted from `P1` to pre-cutover mandatory work if the production rollout will expose `/api/upload` or source-sync execution.

### Task 1 (P0): Fail-Closed Auth, HTTP RBAC, And Reviewer Anti-Spoofing

**Files:**
- Create: `D:\tyh\knowledge-manager\src\knowledge_manager\http_authz.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\auth.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\schemas.py`
- Test: `D:\tyh\knowledge-manager\tests\test_http_server.py`
- Test: `D:\tyh\knowledge-manager\tests\test_enterprise.py`

- [ ] **Step 1: Write the failing security tests for production fail-closed, RBAC, and reviewer spoofing**

```python
def _write_auth_fixture(kb: Path) -> None:
    (kb / "auth.json").write_text(
        json.dumps(
            {
                "provider": "token",
                "oidc_config": {
                    "static_tokens": {
                        "viewer-team-a": {"sub": "victor", "tenant_id": "team-a", "workspace_id": "ws-a"},
                        "reviewer-team-a": {"sub": "rachel", "tenant_id": "team-a", "workspace_id": "ws-a"},
                        "editor-team-a": {"sub": "alice", "tenant_id": "team-a", "workspace_id": "ws-a"},
                        "admin-root": {"sub": "root", "groups": ["admins"]},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (kb / "rbac.json").write_text(
        json.dumps({"users": {"victor": "viewer", "rachel": "reviewer", "alice": "editor", "root": "admin"}}),
        encoding="utf-8",
    )


def test_production_mode_without_auth_config_fails_closed(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="secured"), kb)
    (kb / "config.json").write_text(
        json.dumps(
            {
                "llm_providers": {"x": {"api_key": "k", "model": "m", "default": True}},
                "security": {"production_mode": True},
            }
        ),
        encoding="utf-8",
    )

    client = TestClient(create_app(kb))
    assert client.get("/api/ready").status_code == 503
    assert client.post(
        "/api/modules",
        json={
            "id": "ops-guide",
            "category": "ops",
            "title": "Ops Guide",
            "summary": "Ops guide summary.",
            "content": {"overview": "Ops overview.", "details": "Ops details long enough for validation."},
            "submit_to_staging": False,
        },
    ).status_code == 503


def test_viewer_cannot_access_write_or_control_plane_routes(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    _write_auth_fixture(kb)
    save_index(Index(description="secured"), kb)
    client = TestClient(create_app(kb))
    headers = {"Authorization": "Bearer viewer-team-a"}

    assert client.post("/api/modules", headers=headers, json={"id": "x", "category": "ops", "title": "Ops x", "summary": "Ops summary.", "content": {"overview": "Ops overview.", "details": "Ops details long enough for validation."}, "submit_to_staging": False}).status_code == 403
    assert client.get("/api/staging", headers=headers).status_code == 403
    assert client.get("/api/ops", headers=headers).status_code == 403


def test_http_staging_rejects_forged_reviewer_identity(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    _write_auth_fixture(kb)
    save_index(Index(description="secured"), kb)
    staged = Module(
        id="review-me",
        category="ops",
        title="Review me",
        summary="Review me summary for operators.",
        content=ModuleContent(overview="Review overview.", details="Review details long enough for validation."),
    )
    save_to_staging(staged, kb / ".staging")
    save_staging_meta(StagingMeta(module_id="review-me", status="pending"), kb / ".staging")

    client = TestClient(create_app(kb))
    response = client.post(
        "/api/staging/review-me/approve",
        headers={"Authorization": "Bearer reviewer-team-a"},
        json={"reviewer": "root", "comment": "forged identity"},
    )

    assert response.status_code == 422
```

- [ ] **Step 2: Run the focused P0 auth tests and verify they fail**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; python -m pytest D:\tyh\knowledge-manager\tests\test_http_server.py -k "production_mode_without_auth_config_fails_closed or viewer_cannot_access_write_or_control_plane_routes or http_staging_rejects_forged_reviewer_identity" -v --basetemp C:\tmp\km-pytest`

Expected: `FAIL` because production mode is not fail-closed, RBAC is not enforced on these routes, and reviewer identity is still trusted from the body.

- [ ] **Step 3: Add explicit security config and rich auth subject state**

```python
class SecurityConfig(BaseModel):
    production_mode: bool = False
    multi_tenant_mode: bool = False
    mcp_global_resources: Literal["enabled", "disabled"] = "enabled"
    required_perf_scales: list[str] = Field(default_factory=lambda: ["xs", "s", "m"])
    maintenance_backlog_warn: int = 25
    maintenance_backlog_fail: int = 100


class Config(BaseModel):
    llm_providers: Dict[str, LLMProviderConfig] = Field(default_factory=dict)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
```

```python
class AuthSubject(BaseModel):
    user: str
    tenant_id: str = ""
    workspace_id: str = ""
    groups: list[str] = Field(default_factory=list)


def _verify_token(self, request: Request) -> Optional[AuthSubject]:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    cfg = self.auth_config.oidc_config if self.auth_config else {}
    token_map = cfg.get("static_tokens", {})
    if token in token_map:
        payload = token_map[token]
        return AuthSubject(
            user=payload.get("sub") or payload.get("user") or "token-user",
            tenant_id=payload.get("tenant_id", ""),
            workspace_id=payload.get("workspace_id", ""),
            groups=payload.get("groups", []),
        )
    expected = cfg.get("static_token", "")
    if expected and token == expected:
        return AuthSubject(user="token-user")
    return None
```

- [ ] **Step 4: Add fail-closed HTTP guards and remove client-controlled reviewer identity**

```python
def require_auth_system_ready(kb_path: Path) -> None:
    cfg = _load_config_safe(kb_path)
    production_mode = bool(cfg and cfg.security.production_mode)
    auth_cfg = load_auth_config(kb_path)
    if production_mode and (auth_cfg is None or not auth_cfg.provider):
        raise HTTPException(status_code=503, detail="Authentication must be configured in production_mode")


def require_identity(request: Request, kb_path: Path, permission: str | None = None) -> AuthSubject:
    require_auth_system_ready(kb_path)
    subject = getattr(request.state, "auth_subject", None)
    if subject is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if permission and not check_permission(subject.user, permission, kb_path):
        raise HTTPException(status_code=403, detail=f"Permission denied: {permission}")
    return subject
```

```python
@app.post("/api/staging/{module_id}/approve")
def api_staging_approve(module_id: str, request: Request, body: dict | None = None):
    subject = require_identity(request, kb_path, "module.review")
    if body and "reviewer" in body and body["reviewer"] != subject.user:
        raise HTTPException(status_code=422, detail="reviewer is server-assigned")
    comment = (body or {}).get("comment", "")
    meta.reviews.append(ReviewRecord(reviewer=subject.user, action="approved", comment=comment))
```

```python
@app.post("/api/modules")
def api_module_create(request: Request, body: dict):
    subject = require_identity(request, kb_path, "module.write")
    module = Module(
        id=body["id"],
        category=body["category"],
        title=body["title"],
        summary=body["summary"],
        content=ModuleContent(**body.get("content", {"overview": "", "details": ""})),
        metadata=ModuleMetadata(**body.get("metadata", {})),
    )
    module.metadata.tenant_id = module.metadata.tenant_id or subject.tenant_id
    module.metadata.workspace_id = module.metadata.workspace_id or subject.workspace_id
    maintenance_state: list[dict[str, Any]] = []
    save_module(module, kb_path, maintenance_state=maintenance_state)
    return {**module.model_dump(mode="json"), "status": "created", "maintenance": maintenance_state[0] if maintenance_state else {"deferred": False}}


@app.get("/api/ops")
def api_ops(request: Request):
    require_identity(request, kb_path, "audit.read")
    tenant = resolve_tenant_context(request, kb_path)
    report = generate_ops_report(kb_path, tenant=tenant)
    return report.model_dump()
```

- [ ] **Step 5: Re-run focused tests plus the existing auth/RBAC suite**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; python -m pytest D:\tyh\knowledge-manager\tests\test_http_server.py D:\tyh\knowledge-manager\tests\test_enterprise.py -k "production_mode or reviewer or auth or permission or viewer_cannot" -v --basetemp C:\tmp\km-pytest`

Expected: new tests pass, existing enterprise auth/RBAC tests remain green.

- [ ] **Step 6: Commit the Task 1 slice**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\http_authz.py D:\tyh\knowledge-manager\src\knowledge_manager\auth.py D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py D:\tyh\knowledge-manager\src\knowledge_manager\schemas.py D:\tyh\knowledge-manager\tests\test_http_server.py D:\tyh\knowledge-manager\tests\test_enterprise.py
git commit -m "fix: fail closed auth and enforce http rbac"
```

**Acceptance Criteria**

- Unauthenticated write/control-plane requests return `401` when auth is configured.
- `production_mode=true` with missing auth config makes `/api/ready` return `503` and refuses write/control-plane traffic with `503`.
- Authenticated viewer requests to write/control-plane routes return `403`.
- `reviewer` supplied by clients is rejected or ignored; persisted reviewer identity comes from the authenticated subject only.
- Existing local development behavior remains available when `production_mode=false`.

### Task 2 (P0): Derive Tenant Scope From Auth And Apply It Across HTTP Data And Control Plane

**Files:**
- Create: `D:\tyh\knowledge-manager\src\knowledge_manager\tenant_views.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\http_authz.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\tenancy.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\schemas.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\ingestion_jobs.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\source_ingestion.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\admin_views.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\ops_export.py`
- Test: `D:\tyh\knowledge-manager\tests\test_http_server.py`
- Test: `D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py`
- Test: `D:\tyh\knowledge-manager\tests\test_enterprise.py`

- [ ] **Step 1: Write the failing tenant-scope tests using auth-derived scope instead of caller-chosen scope**

```python
def test_non_admin_cannot_override_tenant_scope(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    _write_auth_fixture(kb)
    save_index(Index(description="tenant aggregate"), kb)
    client = TestClient(create_app(kb))

    response = client.get("/api/index?tenant_id=team-b", headers={"Authorization": "Bearer editor-team-a"})
    assert response.status_code == 403


def test_authenticated_tenant_scope_filters_index_tree_graph_and_recommendations(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    _write_auth_fixture(kb)
    save_index(Index(description="tenant aggregate"), kb)
    save_module(Module(id="tenant-a", category="ops", title="Tenant A Guide", summary="Tenant A summary.", content=ModuleContent(overview="Tenant A overview.", details="Tenant A details long enough for validation."), metadata=ModuleMetadata(tenant_id="team-a", related_modules=["ops/tenant-b"])), kb)
    save_module(Module(id="tenant-b", category="ops", title="Tenant B Guide", summary="Tenant B summary.", content=ModuleContent(overview="Tenant B overview.", details="Tenant B details long enough for validation."), metadata=ModuleMetadata(tenant_id="team-b")), kb)

    client = TestClient(create_app(kb))
    headers = {"Authorization": "Bearer editor-team-a"}

    assert "tenant-b" not in json.dumps(client.get("/api/index", headers=headers).json())
    assert "tenant-b" not in json.dumps(client.get("/api/tree", headers=headers).json())
    assert "tenant-b" not in json.dumps(client.get("/api/graph", headers=headers).json())
    assert "tenant-b" not in json.dumps(client.get("/api/recommendations", headers=headers).json())


def test_admin_dashboard_and_source_jobs_filter_by_owned_tenant(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    _write_auth_fixture(kb)
    save_index(Index(description="tenant ops"), kb)
    job = create_ingestion_job(kb, source_id="upload", trigger="http-upload", tenant_id="team-a", workspace_id="ws-a")
    complete_ingestion_job(kb, job.job_id, pages_seen=1, modules_staged=1)

    client = TestClient(create_app(kb))
    headers = {"Authorization": "Bearer admin-root"}
    jobs = client.get("/api/source/jobs?tenant_id=team-a", headers=headers)
    dashboard = client.get("/api/admin/dashboard?tenant_id=team-a", headers=headers)

    assert jobs.status_code == 200
    assert jobs.json()["items"][0]["tenant_id"] == "team-a"
    assert all(item["tenant_id"] == "team-a" for item in dashboard.json()["ingestion_jobs"])
```

- [ ] **Step 2: Run the focused tenant tests and verify they fail**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; python -m pytest D:\tyh\knowledge-manager\tests\test_http_server.py D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py -k "override_tenant_scope or authenticated_tenant_scope_filters or source_jobs_filter_by_owned_tenant" -v --basetemp C:\tmp\km-pytest`

Expected: `FAIL` because tenant scope is still caller-controlled and jobs/dashboard data do not yet carry tenant ownership.

- [ ] **Step 3: Resolve tenant scope from the authenticated subject and support admin-only override**

```python
def can_access_tenant(subject: AuthSubject, requested_tenant_id: str, kb_path: Path) -> bool:
    if not requested_tenant_id:
        return True
    if subject.tenant_id and subject.tenant_id == requested_tenant_id:
        return True
    return get_user_role(subject.user, kb_path) == "admin"


def resolve_tenant_context(
    request: Request,
    kb_path: Path,
    requested_tenant_id: str = "",
    requested_workspace_id: str = "",
) -> TenantContext | None:
    cfg = _load_config_safe(kb_path)
    if cfg is None or not cfg.security.multi_tenant_mode:
        return None
    subject = require_identity(request, kb_path, "module.read")
    tenant_id = subject.tenant_id
    workspace_id = subject.workspace_id
    if requested_tenant_id and requested_tenant_id != tenant_id:
        if not can_access_tenant(subject, requested_tenant_id, kb_path):
            raise HTTPException(status_code=403, detail="tenant override denied")
        tenant_id = requested_tenant_id
    if requested_workspace_id and requested_workspace_id != workspace_id:
        if get_user_role(subject.user, kb_path) != "admin":
            raise HTTPException(status_code=403, detail="workspace override denied")
        workspace_id = requested_workspace_id
    return TenantContext(tenant_id=tenant_id, workspace_id=workspace_id)
```

- [ ] **Step 4: Add tenant/workspace ownership to source definitions and job records**

```python
class SourceDefinition(BaseModel):
    id: str
    type: Literal["confluence", "notion"] = "confluence"
    enabled: bool = True
    tenant_id: str = ""
    workspace_id: str = ""


class IngestionJob(BaseModel):
    job_id: str
    source_id: str
    trigger: str
    status: str = "queued"
    stage: str = "queued"
    tenant_id: str = ""
    workspace_id: str = ""


def create_ingestion_job(
    kb_path: Path,
    source_id: str,
    trigger: str,
    tenant_id: str = "",
    workspace_id: str = "",
) -> IngestionJob:
    job = IngestionJob(
        job_id=f"job-{uuid4().hex[:12]}",
        source_id=source_id,
        trigger=trigger,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )
    return _save_job(kb_path, job)
```

- [ ] **Step 5: Wire auth-derived tenant scope into every HTTP aggregate and control-plane view**

```python
@app.get("/api/index")
def api_index(request: Request, tenant_id: str = Query(""), workspace_id: str = Query("")):
    tenant = resolve_tenant_context(request, kb_path, tenant_id, workspace_id)
    return build_index_view(kb_path, tenant).model_dump(exclude={"graph", "tree"})


@app.get("/api/source/jobs")
def api_source_jobs(request: Request, tenant_id: str = Query(""), workspace_id: str = Query("")):
    require_identity(request, kb_path, "audit.read")
    tenant = resolve_tenant_context(request, kb_path, tenant_id, workspace_id)
    jobs = [job for job in list_ingestion_jobs(kb_path) if tenant is None or job.tenant_id == tenant.tenant_id]
    return {"total": len(jobs), "items": [job.model_dump(mode="json") for job in jobs]}


@app.get("/api/admin/dashboard")
def api_admin_dashboard(request: Request, tenant_id: str = Query(""), workspace_id: str = Query("")):
    require_identity(request, kb_path, "audit.read")
    tenant = resolve_tenant_context(request, kb_path, tenant_id, workspace_id)
    return build_admin_dashboard(kb_path, tenant=tenant)
```

- [ ] **Step 6: Re-run tenant HTTP tests and commit the Task 2 slice**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; python -m pytest D:\tyh\knowledge-manager\tests\test_http_server.py D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py D:\tyh\knowledge-manager\tests\test_enterprise.py -k "tenant or override_tenant_scope or dashboard or source_jobs" -v --basetemp C:\tmp\km-pytest`

Expected: tenant-scoped HTTP reads and control-plane views now derive scope from auth subject by default, while admin overrides remain explicit and guarded.

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\tenant_views.py D:\tyh\knowledge-manager\src\knowledge_manager\http_authz.py D:\tyh\knowledge-manager\src\knowledge_manager\tenancy.py D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py D:\tyh\knowledge-manager\src\knowledge_manager\storage.py D:\tyh\knowledge-manager\src\knowledge_manager\schemas.py D:\tyh\knowledge-manager\src\knowledge_manager\ingestion_jobs.py D:\tyh\knowledge-manager\src\knowledge_manager\source_ingestion.py D:\tyh\knowledge-manager\src\knowledge_manager\admin_views.py D:\tyh\knowledge-manager\src\knowledge_manager\ops_export.py D:\tyh\knowledge-manager\tests\test_http_server.py D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py D:\tyh\knowledge-manager\tests\test_enterprise.py
git commit -m "fix: derive tenant scope from auth across http surfaces"
```

**Acceptance Criteria**

- Non-admin users cannot switch tenant or workspace by changing query/body parameters.
- Authenticated tenant-scoped requests only see modules and aggregates for the authenticated tenant plus any explicitly allowed global data.
- `/api/index`, `/api/tree`, `/api/graph`, `/api/recommendations`, `/api/ops*`, `/api/source/jobs`, and `/api/admin/dashboard` all honor the resolved tenant context.
- Job and source records carry tenant/workspace ownership so operator surfaces can filter them safely.

### Task 3 (P0): Lock Down MCP Multi-Tenant Exposure And Fix Cache Key Collisions

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\cache.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\schemas.py`
- Test: `D:\tyh\knowledge-manager\tests\test_cache.py`
- Test: `D:\tyh\knowledge-manager\tests\test_mcp_server.py`

- [ ] **Step 1: Write the failing cache-isolation and MCP multi-tenant tests**

```python
def test_cache_isolates_by_namespace_category_and_module_id():
    cache = ModuleCache(max_size=10)
    mod_ops = Module(id="shared-id", category="ops", title="Ops Title", summary="Ops summary for category isolation.", content=ModuleContent(overview="Ops overview.", details="Ops details long enough for validation."))
    mod_fin = Module(id="shared-id", category="finance", title="Finance Title", summary="Finance summary for category isolation.", content=ModuleContent(overview="Finance overview.", details="Finance details long enough for validation."))
    mod_ops_ns2 = mod_ops.model_copy(update={"title": "Ops Title NS2"})

    cache.put(mod_ops, namespace="default")
    cache.put(mod_fin, namespace="default")
    cache.put(mod_ops_ns2, namespace="ns2")

    assert cache.get("shared-id", category="ops", namespace="default").title == "Ops Title"
    assert cache.get("shared-id", category="finance", namespace="default").title == "Finance Title"
    assert cache.get("shared-id", category="ops", namespace="ns2").title == "Ops Title NS2"

    cache.invalidate("shared-id", category="ops", namespace="default")
    assert cache.get("shared-id", category="ops", namespace="default") is None
    assert cache.get("shared-id", category="finance", namespace="default") is not None
    assert cache.get("shared-id", category="ops", namespace="ns2") is not None
```

```python
@pytest.mark.asyncio
async def test_multi_tenant_mcp_disables_global_resources(kb_path):
    server = create_server(kb_path, session_tenant=TenantContext(tenant_id="team-a"), security_mode="multi_tenant")
    with pytest.raises(Exception):
        await server.read_resource("knowledge://index")


@pytest.mark.asyncio
async def test_deep_search_expand_module_and_knowledge_graph_honor_trusted_tenant(kb_path):
    save_module(Module(id="tenant-a", category="ops", title="Tenant A Guide", summary="Tenant A rollback guidance.", content=ModuleContent(overview="Rollback safely for tenant A.", details="Tenant A details long enough for validation."), metadata=ModuleMetadata(tenant_id="team-a")), kb_path)
    save_module(Module(id="tenant-b", category="ops", title="Tenant B Guide", summary="Tenant B rollback guidance.", content=ModuleContent(overview="Rollback safely for tenant B.", details="Tenant B details long enough for validation."), metadata=ModuleMetadata(tenant_id="team-b")), kb_path)
    server = create_server(kb_path, session_tenant=TenantContext(tenant_id="team-a"), security_mode="multi_tenant")

    deep = await server.call_tool("deep_search", {"query": "rollback safely"})
    graph = await server.call_tool("knowledge_graph", {"query": "rollback"})

    assert "tenant-a" in deep[0].text and "tenant-b" not in deep[0].text
    assert "tenant-a" in graph[0].text and "tenant-b" not in graph[0].text
```

- [ ] **Step 2: Run the focused MCP/cache tests and verify they fail**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; python -m pytest D:\tyh\knowledge-manager\tests\test_cache.py D:\tyh\knowledge-manager\tests\test_mcp_server.py -k "cache_isolates_by_namespace_category_and_module_id or multi_tenant_mcp_disables_global_resources or honor_trusted_tenant" -v --basetemp C:\tmp\km-pytest`

Expected: `FAIL` because MCP cache keys still omit category and MCP global resources are still exposed in multi-tenant mode.

- [ ] **Step 3: Migrate cache keys to `namespace + category + module_id` and update all call sites**

```python
@staticmethod
def _make_key(module_id: str, category: str, namespace: str = "default") -> str:
    return f"{namespace}:{category}:{module_id}"


def get(self, module_id: str, category: str, namespace: str = "default") -> Optional[Module]:
    key = self._make_key(module_id, category, namespace)
    with self._lock:
        if key not in self._cache:
            return None
        self._cache.move_to_end(key)
        return self._cache[key]


def put(self, module: Module, namespace: str = "default") -> None:
    key = self._make_key(module.id, module.category, namespace)
    with self._lock:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = module
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)


def invalidate(self, module_id: str, category: str, namespace: str = "default") -> None:
    key = self._make_key(module_id, category, namespace)
    with self._lock:
        self._cache.pop(key, None)
```

```python
cached = cache.get(module_id, category=category, namespace=namespace)
if cached is not None and (tenant is None or module_visible_to_tenant(cached, tenant)):
    return cached.model_dump_json(indent=2)
module = load_module(module_id, category, target_kb)
cache.put(module, namespace=namespace)
```

- [ ] **Step 4: Disable unsafe global MCP resources in multi-tenant mode and trust only server-supplied tenant context**

```python
def create_server(
    kb_path: Path,
    cache: ModuleCache | None = None,
    federation: dict | None = None,
    session_tenant: TenantContext | None = None,
    security_mode: str = "single_tenant",
) -> FastMCP:
    if cache is None:
        cache = ModuleCache()
    if federation is None:
        federation = load_federation(kb_path)
    mcp = FastMCP("knowledge-manager")
    expose_global_resources = not (security_mode == "multi_tenant")
    if expose_global_resources:
        @mcp.resource("knowledge://index")
        def get_index() -> str:
            index = load_index(kb_path)
            if index is None:
                return json.dumps({"version": "1.0", "description": "Empty knowledge base", "categories": {}, "stats": {}})
            return index.model_dump_json()


def _resolve_mcp_tenant(tenant_id: str = "") -> TenantContext | None:
    if session_tenant is not None:
        if tenant_id and tenant_id != session_tenant.tenant_id:
            raise ValueError("tenant mismatch")
        return session_tenant
    if security_mode == "multi_tenant":
        raise ValueError("trusted tenant context required")
    return TenantContext(tenant_id=tenant_id) if tenant_id else None
```

```python
@mcp.resource("knowledge://tenant/{tenant_id}/index")
def get_tenant_index(tenant_id: str) -> str:
    tenant = _resolve_mcp_tenant(tenant_id)
    return build_index_view(kb_path, tenant).model_dump_json()


@mcp.tool(name="deep_search")
def deep_search_tool(query: str, category: str = "", namespace: str = "default", tenant_id: str = "") -> str:
    tenant = _resolve_mcp_tenant(tenant_id)
    target_kb = _resolve_kb(namespace)
    search_results = search_modules(query, target_kb, category if category else None, limit=3, boost_ids=_session_loaded, tenant=tenant)
    return json.dumps([_render_deep_search_result(target_kb, result.module) for result in search_results], indent=2)
```

- [ ] **Step 5: Re-run MCP/cache tests plus existing MCP tenant tests**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; python -m pytest D:\tyh\knowledge-manager\tests\test_cache.py D:\tyh\knowledge-manager\tests\test_mcp_server.py -k "tenant or cache_isolates_by_namespace_category_and_module_id or namespace_isolation or trusted_tenant" -v --basetemp C:\tmp\km-pytest`

Expected: cache collisions are eliminated, global MCP resources are not available in multi-tenant mode, and tool outputs stay inside trusted tenant scope.

- [ ] **Step 6: Commit the Task 3 slice**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\cache.py D:\tyh\knowledge-manager\src\knowledge_manager\mcp_server.py D:\tyh\knowledge-manager\src\knowledge_manager\schemas.py D:\tyh\knowledge-manager\tests\test_cache.py D:\tyh\knowledge-manager\tests\test_mcp_server.py
git commit -m "fix: lock down mcp multi-tenant exposure and cache keys"
```

**Acceptance Criteria**

- Cache lookup/invalidate behavior is isolated by namespace, category, and module ID.
- There are no remaining `cache.get()` / `cache.put()` / `cache.invalidate()` call sites using the old signature.
- In multi-tenant production mode, unsafe global `knowledge://...` MCP resources are disabled by default.
- Tenant-scoped MCP tools/resources use trusted server/session tenant context, not arbitrary caller-chosen tenant IDs.

### Task 4 (P0): Make Readiness Truthful, Fix `updated_at`, And Verify All Required Benchmark Scales

**Files:**
- Create: `D:\tyh\knowledge-manager\scripts\verify_production_readiness.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\runtime_checks.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\auth.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\performance_benchmarks.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\cli.py`
- Test: `D:\tyh\knowledge-manager\tests\test_runtime_checks.py`
- Test: `D:\tyh\knowledge-manager\tests\test_storage.py`
- Test: `D:\tyh\knowledge-manager\tests\test_http_server.py`
- Test: `D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py`

- [ ] **Step 1: Write the failing readiness, freshness, and multi-scale verification tests**

```python
def test_evaluate_readiness_fails_when_production_mode_has_no_auth(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="ready"), kb)
    (kb / "config.json").write_text(
        json.dumps({"llm_providers": {"x": {"api_key": "k", "model": "m", "default": True}}, "security": {"production_mode": True}}),
        encoding="utf-8",
    )

    state = evaluate_readiness(kb)
    assert state["ready"] is False
    assert any("auth" in reason.lower() for reason in state["reasons"])


def test_evaluate_readiness_fails_on_failed_jobs_and_expired_leases(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="ready"), kb)
    (kb / "config.json").write_text(json.dumps({"llm_providers": {"x": {"api_key": "k", "model": "m", "default": True}}}), encoding="utf-8")
    job = create_ingestion_job(kb, source_id="upload", trigger="http-upload")
    claimed = claim_ingestion_job(kb, job.job_id, worker_id="worker-1", lease_seconds=1)
    stale = claimed.model_copy(update={"lease_expires_at": datetime.now(timezone.utc) - timedelta(seconds=5)})
    (kb / ".jobs" / "ingestion" / f"{job.job_id}.json").write_text(stale.model_dump_json(indent=2), encoding="utf-8")
    fail_ingestion_job(kb, job.job_id, "boom")

    state = evaluate_readiness(kb)
    assert state["ready"] is False
    assert any("failed ingestion jobs" in reason.lower() for reason in state["reasons"])


def test_save_module_refreshes_updated_at_for_summary_change(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    module = Module(id="mod-1", category="ops", title="Original Title", summary="Original summary for refresh.", content=ModuleContent(overview="Original overview.", details="Original details long enough for validation."))
    save_module(module, kb, defer_noncritical=False)
    before = load_module("mod-1", "ops", kb).updated_at

    changed = load_module("mod-1", "ops", kb)
    changed.summary = "Changed summary for refresh semantics."
    save_module(changed, kb, defer_noncritical=False)

    assert load_module("mod-1", "ops", kb).updated_at > before


def test_verify_production_readiness_requires_all_required_scales(tmp_path):
    matrix = {
        "xs": {"release_verdict": {"ready_for_production": True}},
        "s": {"release_verdict": {"ready_for_production": False}},
        "m": {"release_verdict": {"ready_for_production": True}},
    }
    path = tmp_path / "matrix-summary.json"
    path.write_text(json.dumps(matrix), encoding="utf-8")
    verdict = evaluate_matrix_summary(path, required_scales=["xs", "s", "m"])
    assert verdict["ready_for_production"] is False
    assert verdict["failed_scales"] == ["s"]
```

- [ ] **Step 2: Run the focused readiness/freshness tests and verify they fail**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; python -m pytest D:\tyh\knowledge-manager\tests\test_runtime_checks.py D:\tyh\knowledge-manager\tests\test_storage.py D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py -k "production_mode_has_no_auth or failed_jobs_and_expired_leases or refreshes_updated_at_for_summary_change or requires_all_required_scales" -v --basetemp C:\tmp\km-pytest`

Expected: `FAIL` because readiness is too shallow, `updated_at` is stale for summary/content changes, and release verification does not aggregate required scales.

- [ ] **Step 3: Upgrade readiness from existence checks to runtime truth checks**

```python
def evaluate_readiness(kb_path: Path) -> dict[str, Any]:
    reasons: list[str] = []
    warnings: list[str] = []
    cfg = _load_config_safe(kb_path)
    if cfg is None:
        reasons.append("config missing or invalid")
    else:
        if cfg.security.production_mode:
            auth_cfg = load_auth_config(kb_path)
            if auth_cfg is None or not auth_cfg.provider:
                reasons.append("auth configuration missing in production_mode")
        try:
            cfg.get_default_provider()
        except Exception:
            reasons.append("default provider not configured")

    if load_index(kb_path) is None:
        reasons.append("index missing")

    integrity = run_integrity_check(kb_path)
    if not integrity["ok"]:
        reasons.append("integrity check failed")

    jobs = list_ingestion_jobs(kb_path)
    failed_jobs = [job.job_id for job in jobs if job.status == "failed"]
    stale_running = [job.job_id for job in jobs if job.status == "running" and job.lease_expires_at and job.lease_expires_at < datetime.now(timezone.utc)]
    if failed_jobs:
        reasons.append(f"failed ingestion jobs: {', '.join(failed_jobs[:3])}")
    if stale_running:
        reasons.append(f"stale running jobs: {', '.join(stale_running[:3])}")

    queued_maintenance = len(list((kb_path / '.cache' / 'maintenance').glob('*.queued.json')))
    if cfg and queued_maintenance > cfg.security.maintenance_backlog_fail:
        reasons.append(f"maintenance backlog above fail threshold: {queued_maintenance}")
    elif cfg and queued_maintenance > cfg.security.maintenance_backlog_warn:
        warnings.append(f"maintenance backlog above warning threshold: {queued_maintenance}")

    status = "ready" if not reasons and not warnings else ("degraded" if not reasons else "fail")
    return {"ready": not reasons, "status": status, "reasons": reasons, "warnings": warnings, "integrity_ok": integrity["ok"]}
```

- [ ] **Step 4: Centralize freshness updates and implement per-scale production verification**

```python
def save_module(module: Module, kb_path: Path, defer_noncritical: bool = True, maintenance_state: list[dict[str, Any]] | None = None) -> None:
    path = module.to_file_path(kb_path)
    if path.exists():
        existing = Module.model_validate_json(path.read_text(encoding="utf-8"))
        before = existing.model_dump(mode="json")
        after = module.model_dump(mode="json")
        before.pop("updated_at", None)
        after.pop("updated_at", None)
        if before != after:
            module.updated_at = datetime.now(timezone.utc)
    _atomic_write(path, module.model_dump_json(indent=2))
    _upsert_index_entry(module, kb_path)
    _invalidate_module_cache(kb_path)
    invalidate_materialized_views(kb_path)
```

```python
def evaluate_matrix_summary(path: Path, required_scales: list[str]) -> dict[str, Any]:
    matrix = json.loads(path.read_text(encoding="utf-8"))
    scale_verdicts = {scale: matrix.get(scale, {}).get("release_verdict", {}) for scale in required_scales}
    failed_scales = [scale for scale, verdict in scale_verdicts.items() if not verdict.get("ready_for_production", False)]
    return {
        "required_scales": required_scales,
        "scale_verdicts": scale_verdicts,
        "failed_scales": failed_scales,
        "ready_for_production": not failed_scales,
    }
```

```python
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kb-path", required=True)
    parser.add_argument("--matrix-summary", required=True)
    args = parser.parse_args()
    kb_path = Path(args.kb_path)
    cfg = _load_config_safe(kb_path)
    required_scales = cfg.security.required_perf_scales if cfg else ["xs", "s", "m"]
    matrix_verdict = evaluate_matrix_summary(Path(args.matrix_summary), required_scales)
    readiness = evaluate_readiness(kb_path)
    integrity = run_integrity_check(kb_path)
    verdict = {
        "ready_for_production": readiness["ready"] and integrity["ok"] and matrix_verdict["ready_for_production"],
        "readiness": readiness,
        "integrity": integrity,
        "performance": matrix_verdict,
    }
    print(json.dumps(verdict, ensure_ascii=False, indent=2))
    return 0 if verdict["ready_for_production"] else 1
```

- [ ] **Step 5: Re-run production-gate tests and smoke the verification script**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; python -m pytest D:\tyh\knowledge-manager\tests\test_runtime_checks.py D:\tyh\knowledge-manager\tests\test_storage.py D:\tyh\knowledge-manager\tests\test_http_server.py D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py -k "ready or integrity or updated_at or release_verdict or required_scales" -v --basetemp C:\tmp\km-pytest`

Run: `python D:\tyh\knowledge-manager\scripts\verify_production_readiness.py --kb-path D:\tyh\knowledge-manager\kb --matrix-summary D:\tyh\knowledge-manager\test-results\perf-run-production-gate-20260613-r5\matrix-summary.json`

Expected: tests pass; the script exits non-zero if any required scale, readiness check, or integrity check fails.

- [ ] **Step 6: Commit the Task 4 slice**

```bash
git add D:\tyh\knowledge-manager\scripts\verify_production_readiness.py D:\tyh\knowledge-manager\src\knowledge_manager\runtime_checks.py D:\tyh\knowledge-manager\src\knowledge_manager\storage.py D:\tyh\knowledge-manager\src\knowledge_manager\auth.py D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py D:\tyh\knowledge-manager\src\knowledge_manager\performance_benchmarks.py D:\tyh\knowledge-manager\src\knowledge_manager\cli.py D:\tyh\knowledge-manager\tests\test_runtime_checks.py D:\tyh\knowledge-manager\tests\test_storage.py D:\tyh\knowledge-manager\tests\test_http_server.py D:\tyh\knowledge-manager\tests\test_performance_benchmarks.py
git commit -m "feat: add truthful production readiness gates"
```

**Acceptance Criteria**

- `/api/ready` no longer passes on auth-missing production config, failed jobs, stale running jobs, or integrity failure.
- Maintenance backlog thresholds produce either `degraded` or `fail` instead of silent success.
- `updated_at` refreshes whenever persisted module content actually changes.
- Release verification fails if any required benchmark scale is not `ready_for_production=true`.

### Task 5 (P1 / Pre-Cutover If Upload Is Enabled): Replace In-Process Threads With A Durable Worker Loop

**Files:**
- Create: `D:\tyh\knowledge-manager\src\knowledge_manager\worker_service.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\ingestion_jobs.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\job_worker.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\cli.py`
- Test: `D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py`
- Create: `D:\tyh\knowledge-manager\tests\test_worker_service.py`

- [ ] **Step 1: Write the failing worker durability tests**

```python
def test_requeue_stale_running_jobs(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    job = create_ingestion_job(kb, source_id="upload", trigger="http-upload")
    claimed = claim_ingestion_job(kb, job.job_id, worker_id="worker-1", lease_seconds=1)
    stale = claimed.model_copy(update={"lease_expires_at": datetime.now(timezone.utc) - timedelta(seconds=5)})
    (kb / ".jobs" / "ingestion" / f"{job.job_id}.json").write_text(stale.model_dump_json(indent=2), encoding="utf-8")

    assert requeue_stale_jobs(kb) == [job.job_id]
    assert load_ingestion_job(kb, job.job_id).status == "queued"


def test_upload_endpoint_only_enqueues_job(tmp_path, monkeypatch):
    kb = tmp_path / "kb"
    kb.mkdir()
    started = {"count": 0}

    def explode(*_args, **_kwargs):
        started["count"] += 1
        raise AssertionError("http upload must not start a worker thread")

    monkeypatch.setattr("knowledge_manager.http_server.Thread", explode)
    client = TestClient(create_app(kb))
    response = client.post("/api/upload", files={"file": ("demo.md", b"# title")})

    assert response.status_code == 202
    assert started["count"] == 0
```

```python
def test_worker_run_once_drains_queued_jobs(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    job = create_ingestion_job(kb, source_id="upload", trigger="http-upload")
    processed = run_worker_loop(kb, once=True, poll_interval=0.01)
    assert processed >= 1
```

- [ ] **Step 2: Run the focused worker tests and verify they fail**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; python -m pytest D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py D:\tyh\knowledge-manager\tests\test_worker_service.py -k "stale_running_jobs or upload_endpoint_only_enqueues_job or worker_run_once_drains_queued_jobs" -v --basetemp C:\tmp\km-pytest`

Expected: `FAIL` because queue recovery and enqueue-only API behavior do not exist yet.

- [ ] **Step 3: Add leases, heartbeats, and stale-job recovery**

```python
class IngestionJob(BaseModel):
    job_id: str
    source_id: str
    trigger: str
    status: str = "queued"
    stage: str = "queued"
    attempt_count: int = 0
    lease_expires_at: datetime | None = None
    heartbeat_at: datetime | None = None


def claim_ingestion_job(kb_path: Path, job_id: str, worker_id: str, lease_seconds: int = 60) -> IngestionJob:
    job = load_ingestion_job(kb_path, job_id)
    if job is None:
        raise FileNotFoundError(job_id)
    return _save_job(kb_path, job.model_copy(update={"status": "running", "stage": "running", "worker_id": worker_id, "attempt_count": job.attempt_count + 1, "heartbeat_at": datetime.now(timezone.utc), "lease_expires_at": datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)}))
```

- [ ] **Step 4: Make HTTP enqueue-only and run jobs from a dedicated worker loop**

```python
def run_worker_loop(kb_path: Path, *, once: bool = False, poll_interval: float = 1.0) -> int:
    processed = 0
    requeue_stale_jobs(kb_path)
    while True:
        queued = [job for job in list_ingestion_jobs(kb_path) if job.status == "queued"]
        for job in queued:
            run_single_job(kb_path, job.job_id)
            processed += 1
        if once:
            return processed
        time.sleep(poll_interval)
```

```python
@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...), category: str = Form(default="general"), mode: str = Form(default="auto")):
    content = await file.read()
    filename = file.filename or "upload"
    job_id = _start_upload_job(kb_path, filename, content, category, mode)
    return JSONResponse(status_code=202, content={"status": "accepted", "job_id": job_id, "filename": filename})
```

- [ ] **Step 5: Add `km worker run` and verify recovery behavior**

```python
@cli.group("worker")
def worker() -> None:
    """Run local background workers."""


@worker.command("run")
@click.option("--once", is_flag=True, help="Process queued work once and exit.")
@click.option("--poll-interval", type=float, default=1.0)
@click.pass_context
def worker_run(ctx: click.Context, once: bool, poll_interval: float) -> None:
    from knowledge_manager.worker_service import run_worker_loop
    kb = ctx.obj["kb_path"]
    _require_kb(kb)
    processed = run_worker_loop(kb, once=once, poll_interval=poll_interval)
    click.echo(f"Processed {processed} job(s)")
```

- [ ] **Step 6: Commit the Task 5 slice**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\worker_service.py D:\tyh\knowledge-manager\src\knowledge_manager\ingestion_jobs.py D:\tyh\knowledge-manager\src\knowledge_manager\job_worker.py D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py D:\tyh\knowledge-manager\src\knowledge_manager\cli.py D:\tyh\knowledge-manager\tests\test_ingestion_jobs.py D:\tyh\knowledge-manager\tests\test_worker_service.py
git commit -m "feat: add durable worker loop and queue recovery"
```

**Acceptance Criteria**

- API upload requests only create durable jobs and return `202`; they do not start background worker threads.
- Stale running jobs can be requeued after restart/crash.
- A dedicated worker command can drain queued work deterministically.
- If upload/source sync is enabled in production, this task is complete before cutover.

### Task 6 (P1): Enrich Auditability, Add Request Correlation, And Document Rollout / Rollback

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\audit.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\http_authz.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\performance_benchmarks.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\cli.py`
- Create: `D:\tyh\knowledge-manager\tests\test_audit.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_http_server.py`
- Modify: `D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md`
- Modify: `D:\tyh\knowledge-manager\docs\runbooks\enterprise-performance-test-plan.md`

- [ ] **Step 1: Write the failing audit and request-correlation tests**

```python
def test_module_create_emits_audit_event_with_user_tenant_and_request_id(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    _write_auth_fixture(kb)
    save_index(Index(description="audit"), kb)
    client = TestClient(create_app(kb))
    response = client.post(
        "/api/modules",
        headers={"Authorization": "Bearer editor-team-a"},
        json={
            "id": "audit-mod",
            "category": "ops",
            "title": "Audit module",
            "summary": "Audit module summary.",
            "content": {"overview": "Audit overview.", "details": "Audit details long enough for validation."},
            "submit_to_staging": False,
        },
    )

    events = read_audit_log(kb)
    assert response.headers["X-Request-ID"]
    assert any(event["operation"] == "module.create" and event["user"] == "alice" and event["tenant_id"] == "team-a" and event["request_id"] for event in events)


def test_tenant_override_denial_is_audited(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    _write_auth_fixture(kb)
    save_index(Index(description="audit"), kb)
    client = TestClient(create_app(kb))
    response = client.get("/api/index?tenant_id=team-b", headers={"Authorization": "Bearer editor-team-a"})

    events = read_audit_log(kb)
    assert response.status_code == 403
    assert any(event["operation"] == "authz.denied" and event["result"] == "denied" for event in events)
```

- [ ] **Step 2: Run the focused audit tests and verify they fail**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; python -m pytest D:\tyh\knowledge-manager\tests\test_audit.py D:\tyh\knowledge-manager\tests\test_http_server.py -k "request_id or audit or tenant_override_denial" -v --basetemp C:\tmp\km-pytest`

Expected: `FAIL` because request correlation and HTTP security action audit events are not emitted yet.

- [ ] **Step 3: Extend audit event shape and emit events from security-sensitive HTTP paths**

```python
class AuditEvent:
    def __init__(
        self,
        user: str,
        operation: str,
        module_id: str = "",
        category: str = "",
        details: str = "",
        tenant_id: str = "",
        resource: str = "",
        result: str = "success",
        request_id: str = "",
    ):
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.user = user
        self.operation = operation
        self.module_id = module_id
        self.category = category
        self.details = details
        self.tenant_id = tenant_id
        self.resource = resource
        self.result = result
        self.request_id = request_id
```

```python
@app.middleware("http")
async def inject_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid4().hex
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response
```

```python
log_audit_event(
    kb_path,
    AuditEvent(
        user=subject.user,
        operation="module.create",
        module_id=module.id,
        category=module.category,
        tenant_id=subject.tenant_id,
        resource=f"/api/modules/{module.category}/{module.id}",
        result="success",
        request_id=request.state.request_id,
    ),
)
```

- [ ] **Step 4: Update runbooks and benchmark governance with exact rollout and rollback rules**

```markdown
## Production Release Sequencing

1. Deploy P0 code with `production_mode=false`, `multi_tenant_mode=false`, and enriched audit logging enabled.
2. Configure auth claims for user, tenant, and workspace; verify tenant-scoped tests and `verify_production_readiness.py`.
3. Enable `multi_tenant_mode=true` and set MCP global resources to disabled in environments serving multiple tenants.
4. If `/api/upload` or source sync are enabled, start `km worker run` under a service manager and verify no stale queue backlog.
5. Flip `production_mode=true` only after readiness, integrity, and all required performance scales pass.

## Rollback Rules

- If a release fails before `production_mode=true`, revert the release and keep fail-closed disabled.
- If a release fails after `production_mode=true`, revert the code/config release first; do not leave production indefinitely in open mode.
- After rollback, drain or requeue stale jobs with the worker command before retrying cutover.
```

- [ ] **Step 5: Re-run audit tests and verify docs mention multi-scale gates and rollback**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; python -m pytest D:\tyh\knowledge-manager\tests\test_audit.py D:\tyh\knowledge-manager\tests\test_http_server.py -k "audit or request_id or denial" -v --basetemp C:\tmp\km-pytest`

Run: `Select-String -Path D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md,D:\tyh\knowledge-manager\docs\runbooks\enterprise-performance-test-plan.md -Pattern "production_mode","rollback","xs","s","m","verify_production_readiness"`

Expected: audit tests pass and both runbooks contain explicit release-sequencing and rollback language.

- [ ] **Step 6: Commit the Task 6 slice**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\audit.py D:\tyh\knowledge-manager\src\knowledge_manager\http_authz.py D:\tyh\knowledge-manager\src\knowledge_manager\http_server.py D:\tyh\knowledge-manager\src\knowledge_manager\performance_benchmarks.py D:\tyh\knowledge-manager\src\knowledge_manager\cli.py D:\tyh\knowledge-manager\tests\test_audit.py D:\tyh\knowledge-manager\tests\test_http_server.py D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md D:\tyh\knowledge-manager\docs\runbooks\enterprise-performance-test-plan.md
git commit -m "feat: add audit correlation and rollout guidance"
```

**Acceptance Criteria**

- Audit logs capture at least `timestamp`, `user`, `operation`, `tenant_id`, `resource`, `result`, and `request_id`.
- Module create/update/delete, staging approve/reject, admin dashboard access, source-job actions, and tenant-override denials are audited.
- Operators have a written rollout sequence for enabling `multi_tenant_mode` and `production_mode`.
- Operators have explicit rollback guidance for failed cutovers and stale queue recovery.

## Coverage Check

- Fail-closed auth and HTTP RBAC: Task 1
- Auth-derived tenant scope across HTTP data/control plane: Task 2
- MCP resource lockdown and cache correctness: Task 3
- Truthful readiness, freshness, and multi-scale verification: Task 4
- Durable worker cutover path: Task 5
- Auditability, rollout, and rollback governance: Task 6

## Release Sequencing And Rollback

1. Land Tasks 1-4 first and keep `production_mode=false` while validating behavior in a staging environment.
2. Turn on auth claim population for `user`, `tenant_id`, and `workspace_id`; confirm HTTP and MCP tenant tests pass under real tokens.
3. In any multi-tenant environment, set MCP global resources to disabled before exposing MCP to non-admin consumers.
4. If production will use uploads or source sync, complete Task 5 before cutover and run the worker under a real service manager.
5. Run `verify_production_readiness.py` against the target KB and the latest matrix summary. All required scales must pass.
6. Only after the above succeeds should `production_mode=true` be enabled.

Rollback:

- Revert the release artifact or config change that introduced the regression.
- Re-run readiness and integrity checks before re-opening traffic.
- If jobs were left running or queued, recover them with the worker service before retrying deployment.
- Do not treat "leave production_mode off forever" as the steady-state solution; that is a break-glass fallback, not a production target.

## Notes For Execution

- Do not reopen architecture around databases, Celery, Redis, or distributed queues in this plan.
- The P0 work should ship in small, independently reviewable slices. Task 1 and Task 3 each materially reduce data-leak risk on their own.
- Keep using `--basetemp C:\tmp\km-pytest` on this workstation for deterministic local verification.
- If the first production cutover does not expose `/api/upload` or source sync, Task 5 can remain P1. If those capabilities are part of the cutover, Task 5 becomes mandatory before release.
