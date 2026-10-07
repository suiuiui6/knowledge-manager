from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import json
from typing import AsyncIterator

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from knowledge_manager.audit import AuditEvent, log_audit_event
from knowledge_manager.http_authz import (
    enforce_subject_metadata_override,
    enforce_subject_module_access,
    require_auth_system_ready,
    require_identity,
    resolve_tenant_context,
)
from knowledge_manager.schemas import GraphData, GraphEdge, GraphNode, PaginatedResponse
from knowledge_manager.storage import (
    aggregate_usage_stats,
    analyze_graph,
    generate_health_report,
    generate_ops_report,
    generate_recommendations,
    get_subtree,
    get_tree,
    load_index,
    load_module,
    list_modules,
    search_modules,
)
from knowledge_manager.tenancy import TenantContext, module_visible_to_tenant
from knowledge_manager.tenant_views import (
    build_tenant_graph,
    build_tenant_index,
    build_tenant_ops_report,
    build_tenant_recommendations,
    build_tenant_subgraph,
    build_tenant_subtree,
    build_tenant_tree,
    filter_review_backlog_export,
    filter_source_backlog_items,
)


class MigrationDryRunRequest(BaseModel):
    source_path: str
    source_kind: str


class AccessExplainRequest(BaseModel):
    groups: list[str] = Field(default_factory=list)
    category: str
    module_id: str
    roles: dict = Field(default_factory=dict)
    group_mapping: dict = Field(default_factory=dict)


def _load_config_safe(kb_path: Path):
    from knowledge_manager.schemas import Config

    cfg_path = kb_path / "config.json"
    if not cfg_path.exists():
        return None
    try:
        return Config.model_validate_json(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _start_upload_job(
    kb_path: Path,
    filename: str,
    payload: bytes,
    category: str,
    mode: str,
    *,
    tenant_id: str = "",
    workspace_id: str = "",
) -> str:
    from knowledge_manager.ingestion_jobs import create_ingestion_job, update_job_payload

    job = create_ingestion_job(
        kb_path,
        source_id="upload",
        trigger="http-upload",
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )
    tmp_dir = kb_path / ".tmp" / "uploads"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    payload_path = tmp_dir / f"{job.job_id}-{Path(filename).name}"
    payload_path.write_bytes(payload)
    update_job_payload(
        kb_path,
        job.job_id,
        payload_kind="upload",
        payload_path=str(payload_path),
        payload_meta={"filename": filename, "category": category, "mode": mode},
    )
    return job.job_id


def create_app(kb_path: Path) -> FastAPI:
    app = FastAPI(title="Knowledge Manager", version="0.5.0")

    def _load_config():
        return _load_config_safe(kb_path)

    @app.middleware("http")
    async def inject_request_id(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    ui_dist = Path(__file__).resolve().parent.parent.parent / "src" / "ui" / "dist"

    # ── Health ──

    @app.get("/api/health")
    def api_health():
        report = generate_health_report(kb_path)
        return report.model_dump()

    @app.get("/api/ready")
    def api_ready():
        from knowledge_manager.runtime_checks import evaluate_readiness

        state = evaluate_readiness(kb_path)
        try:
            require_auth_system_ready(kb_path)
        except HTTPException as exc:
            reasons = list(state.get("reasons", []))
            reasons.append(str(exc.detail))
            state = {**state, "ready": False, "reasons": reasons}
        return JSONResponse(status_code=200 if state["ready"] else 503, content=state)

    @app.get("/api/metrics")
    def api_metrics():
        from knowledge_manager.runtime_checks import collect_runtime_metrics

        return PlainTextResponse(collect_runtime_metrics(kb_path), media_type="text/plain")

    # ── Stats ──

    @app.get("/api/stats")
    def api_stats(period: int = Query(30, ge=7, le=90)):
        data = aggregate_usage_stats(kb_path, period_days=period)
        return data.model_dump()

    # ── Index ──

    @app.get("/api/index")
    def api_index(request: Request, tenant_id: str = Query("")):
        tenant = resolve_tenant_context(request, kb_path, tenant_id=tenant_id)
        index = build_tenant_index(kb_path, tenant)
        if index is None:
            return {"version": "1.0", "categories": {}, "stats": {"total_modules": 0}}
        d = index.model_dump()
        d.pop("graph", None)
        d.pop("tree", None)
        return d

    # ── Tree ──

    @app.get("/api/tree")
    def api_tree(request: Request, tenant_id: str = Query("")):
        tenant = resolve_tenant_context(request, kb_path, tenant_id=tenant_id)
        tree = build_tenant_tree(kb_path, tenant)
        return tree.model_dump()

    @app.get("/api/tree/{cat}/{mod_id}")
    def api_tree_node(request: Request, cat: str, mod_id: str, tenant_id: str = Query("")):
        tenant = resolve_tenant_context(request, kb_path, tenant_id=tenant_id)
        subtree = build_tenant_subtree(cat, mod_id, kb_path, tenant)
        if subtree is None:
            raise HTTPException(404, f"Module not found: {cat}/{mod_id}")
        return subtree.model_dump()

    # ── Modules ──

    @app.get("/api/modules")
    def api_modules_list(
        request: Request,
        category: str = Query(""),
        status: str = Query(""),
        tag: str = Query(""),
        tenant_id: str = Query(""),
        page: int = Query(1, ge=1),
        limit: int = Query(50, ge=1, le=200),
    ):
        tenant = resolve_tenant_context(request, kb_path, tenant_id=tenant_id)
        modules = list_modules(kb_path, tenant=tenant)
        if category:
            modules = [m for m in modules if m.category == category]
        if status:
            modules = [m for m in modules if m.metadata.status == status]
        if tag:
            modules = [m for m in modules if tag in m.metadata.tags]

        total = len(modules)
        pages = (total + limit - 1) // limit if total > 0 else 0
        start = (page - 1) * limit
        end = start + limit
        page_items = modules[start:end]

        items = [
            {
                "id": m.id,
                "category": m.category,
                "title": m.title,
                "summary": m.summary,
                "tags": m.metadata.tags,
                "confidence": m.metadata.confidence,
                "status": m.metadata.status,
                "word_count": m.word_count(),
                "updated_at": m.updated_at.isoformat(),
            }
            for m in page_items
        ]
        return PaginatedResponse(items=items, total=total, page=page, limit=limit, pages=pages).model_dump()

    @app.get("/api/modules/{cat}/{mod_id}")
    def api_module_detail(
        request: Request,
        cat: str,
        mod_id: str,
        include_archived: bool = Query(False),
        tenant_id: str = Query(""),
    ):
        tenant = resolve_tenant_context(request, kb_path, tenant_id=tenant_id)
        # Handle .md suffix: strip and return 501 for M1
        if mod_id.endswith(".md"):
            real_id = mod_id[:-3]
            md_path = kb_path / cat / f"{real_id}.md"
            if md_path.exists():
                from fastapi.responses import PlainTextResponse
                return PlainTextResponse(md_path.read_text(encoding="utf-8"), media_type="text/markdown")
            module = load_module(real_id, cat, kb_path)
            if module is None:
                raise HTTPException(404, f"Module not found: {cat}/{real_id}")
            if tenant is not None and not module_visible_to_tenant(module, tenant):
                raise HTTPException(404, f"Module not found: {cat}/{real_id}")
            # Module exists but no .md file yet — generate on the fly
            from knowledge_manager.markdown import render_markdown_module
            from fastapi.responses import PlainTextResponse
            return PlainTextResponse(render_markdown_module(module), media_type="text/markdown")
        module = load_module(mod_id, cat, kb_path)
        if module is None:
            raise HTTPException(404, f"Module not found: {cat}/{mod_id}")
        if tenant is not None and not module_visible_to_tenant(module, tenant):
            raise HTTPException(404, f"Module not found: {cat}/{mod_id}")
        if module.metadata.status == "archived" and not include_archived:
            raise HTTPException(410, f"Module archived: {cat}/{mod_id}")
        return module.model_dump()

    # ── Search ──

    @app.post("/api/search")
    def api_search(request: Request, body: dict):
        query = (body.get("query") or "").strip()
        if not query:
            raise HTTPException(422, "query is required")
        category = body.get("category") or None
        include_archived = body.get("include_archived", False)
        top_k = min(body.get("top_k", 10), 50)
        agent_id = body.get("agent_id") or None
        task_type = body.get("task_type") or None
        risk_level = body.get("risk_level") or None
        tenant_id = body.get("tenant_id") or ""
        workspace_id = body.get("workspace_id") or ""
        tenant = resolve_tenant_context(
            request,
            kb_path,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )

        results = search_modules(
            query,
            kb_path,
            category=category,
            limit=top_k,
            include_archived=include_archived,
            agent_id=agent_id,
            task_type=task_type,
            risk_level=risk_level,
            tenant=tenant,
        )

        from knowledge_manager.storage import _classify_intent

        intent = _classify_intent(query)
        return {
            "query": query,
            "intent": intent,
            "agent_id": agent_id,
            "task_type": task_type,
            "risk_level": risk_level,
            "tenant_id": tenant.tenant_id if tenant else None,
            "results": [
                {
                    "id": r.module.id,
                    "category": r.module.category,
                    "title": r.module.title,
                    "summary": r.module.summary,
                    "tags": r.module.metadata.tags,
                    "confidence": r.module.metadata.confidence,
                    "status": r.module.metadata.status,
                    "source": r.source,
                    "policy_reasons": r.reasons,
                    "related_modules": r.module.metadata.related_modules,
                    "snippet": _snippet(r.module.content.overview, query),
                    "caveats": r.module.content.caveats,
                }
                for r in results
            ],
            "took_ms": 0,
        }

    # ── Write endpoints (M6) ──

    @app.post("/api/modules")
    def api_module_create(body: dict, request: Request):
        from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata

        subject = require_identity(request, kb_path, "module.write")
        try:
            module = Module(
                id=body["id"],
                category=body["category"],
                title=body["title"],
                summary=body["summary"],
                content=ModuleContent(**body.get("content", {"overview": "", "details": ""})),
                metadata=ModuleMetadata(**body.get("metadata", {})),
            )
        except Exception as e:
            raise HTTPException(422, str(e))
        enforce_subject_metadata_override(
            request,
            subject,
            kb_path,
            tenant_id=module.metadata.tenant_id,
            workspace_id=module.metadata.workspace_id,
        )
        module.metadata.tenant_id = module.metadata.tenant_id or subject.tenant_id
        module.metadata.workspace_id = module.metadata.workspace_id or subject.workspace_id

        submit_to_staging = body.get("submit_to_staging", True)
        if submit_to_staging:
            from knowledge_manager.storage import save_to_staging, save_staging_meta
            from knowledge_manager.schemas import StagingMeta

            staging = kb_path / ".staging"
            staging.mkdir(exist_ok=True)
            save_to_staging(module, staging)
            save_staging_meta(StagingMeta(module_id=module.id, submitted_by="web-ui"), staging)
            return {"id": module.id, "category": module.category, "status": "staged", "review_required": True}

        from knowledge_manager.storage import save_module
        maintenance_state: list[dict] = []
        save_module(module, kb_path, maintenance_state=maintenance_state)
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
                request_id=getattr(request.state, "request_id", ""),
            ),
        )
        return {
            **module.model_dump(mode="json"),
            "status": "created",
            "maintenance": maintenance_state[0] if maintenance_state else {"deferred": False},
        }

    @app.put("/api/modules/{cat}/{mod_id}")
    def api_module_update(cat: str, mod_id: str, body: dict, request: Request):
        subject = require_identity(request, kb_path, "module.write")
        module = load_module(mod_id, cat, kb_path)
        if module is None:
            raise HTTPException(404, f"Module not found: {cat}/{mod_id}")
        enforce_subject_module_access(subject, module, kb_path)

        for field in ("title", "summary"):
            if field in body:
                setattr(module, field, body[field])
        if "content" in body:
            for k, v in body["content"].items():
                if hasattr(module.content, k) and v:
                    setattr(module.content, k, v)
        if "metadata" in body:
            metadata_updates = body["metadata"]
            enforce_subject_metadata_override(
                request,
                subject,
                kb_path,
                tenant_id=metadata_updates.get("tenant_id", module.metadata.tenant_id),
                workspace_id=metadata_updates.get("workspace_id", module.metadata.workspace_id),
            )
            for k, v in body["metadata"].items():
                if hasattr(module.metadata, k):
                    setattr(module.metadata, k, v)
            module.updated_at = datetime.now(timezone.utc)

        from knowledge_manager.storage import save_module
        maintenance_state: list[dict] = []
        save_module(module, kb_path, maintenance_state=maintenance_state)
        log_audit_event(
            kb_path,
            AuditEvent(
                user=subject.user,
                operation="module.update",
                module_id=module.id,
                category=module.category,
                tenant_id=subject.tenant_id,
                resource=f"/api/modules/{module.category}/{module.id}",
                result="success",
                request_id=getattr(request.state, "request_id", ""),
            ),
        )
        return {
            **module.model_dump(mode="json"),
            "status": "updated",
            "maintenance": maintenance_state[0] if maintenance_state else {"deferred": False},
        }

    @app.delete("/api/modules/{cat}/{mod_id}")
    def api_module_delete(cat: str, mod_id: str, request: Request):
        from knowledge_manager.storage import delete_module

        subject = require_identity(request, kb_path, "module.delete")
        module = load_module(mod_id, cat, kb_path)
        if module is None:
            raise HTTPException(404, f"Module not found: {cat}/{mod_id}")
        enforce_subject_module_access(subject, module, kb_path)
        maintenance_state: list[dict] = []
        if not delete_module(mod_id, cat, kb_path, maintenance_state=maintenance_state):
            raise HTTPException(404, f"Module not found: {cat}/{mod_id}")
        log_audit_event(
            kb_path,
            AuditEvent(
                user=subject.user,
                operation="module.delete",
                module_id=mod_id,
                category=cat,
                tenant_id=subject.tenant_id,
                resource=f"/api/modules/{cat}/{mod_id}",
                result="success",
                request_id=getattr(request.state, "request_id", ""),
            ),
        )
        return {
            "deleted": f"{cat}/{mod_id}",
            "maintenance": maintenance_state[0] if maintenance_state else {"deferred": False},
        }

    # ── Staging API (M6) ──

    @app.get("/api/staging")
    def api_staging_list(request: Request, tenant_id: str = Query(""), workspace_id: str = Query("")):
        from knowledge_manager.storage import list_staging, load_staging_meta

        require_identity(request, kb_path, "module.review")
        tenant = resolve_tenant_context(
            request,
            kb_path,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        staging = kb_path / ".staging"
        items = []
        for m in list_staging(staging):
            if tenant is not None and not module_visible_to_tenant(m, tenant):
                continue
            meta = load_staging_meta(m.id, staging)
            cfg = _load_config()
            required = cfg.review.required_approvals if cfg else 1
            items.append({
                "module_id": m.id,
                "status": meta.status if meta else "pending",
                "submitted_by": meta.submitted_by if meta else "",
                "submitted_at": meta.submitted_at.isoformat() if meta and meta.submitted_at else "",
                "approvals": meta.approval_count() if meta else 0,
                "required_approvals": required,
                "module_summary": m.summary,
                "preview": {"title": m.title, "category": m.category, "tags": m.metadata.tags},
            })
        return {"items": items}

    @app.post("/api/staging/{module_id}/approve")
    def api_staging_approve(module_id: str, request: Request, body: dict | None = None):
        from knowledge_manager.storage import (
            approve_from_staging, load_from_staging, load_staging_meta, list_staging,
            save_staging_meta,
        )
        from knowledge_manager.schemas import ReviewRecord, StagingMeta

        subject = require_identity(request, kb_path, "module.review")
        staging = kb_path / ".staging"
        staged_module = load_from_staging(module_id, staging)
        if staged_module is None:
            raise HTTPException(404, f"Module not found: {module_id}")
        enforce_subject_module_access(subject, staged_module, kb_path)
        meta = load_staging_meta(module_id, staging)
        if meta is None:
            meta = StagingMeta(module_id=module_id)

        if body and "reviewer" in body and body["reviewer"] != subject.user:
            raise HTTPException(status_code=422, detail="reviewer is server-assigned")
        comment = (body or {}).get("comment", "")
        meta.reviews.append(ReviewRecord(reviewer=subject.user, action="approved", comment=comment))

        cfg = _load_config()
        required = cfg.review.required_approvals if cfg else 1
        if meta.approval_count() >= required:
            approve_from_staging(module_id, staging, kb_path)
            log_audit_event(
                kb_path,
                AuditEvent(
                    user=subject.user,
                    operation="staging.approve",
                    module_id=module_id,
                    category=staged_module.category,
                    tenant_id=subject.tenant_id,
                    resource=f"/api/staging/{module_id}/approve",
                    result="success",
                    request_id=getattr(request.state, "request_id", ""),
                ),
            )
            return {"status": "merged", "approvals": meta.approval_count()}
        save_staging_meta(meta, staging)
        log_audit_event(
            kb_path,
            AuditEvent(
                user=subject.user,
                operation="staging.approve",
                module_id=module_id,
                category=staged_module.category,
                tenant_id=subject.tenant_id,
                resource=f"/api/staging/{module_id}/approve",
                result="pending",
                request_id=getattr(request.state, "request_id", ""),
            ),
        )
        return {"status": "pending", "approvals": meta.approval_count(), "required": required}

    @app.post("/api/staging/{module_id}/reject")
    def api_staging_reject(module_id: str, request: Request, body: dict | None = None):
        from knowledge_manager.storage import load_from_staging, load_staging_meta, save_staging_meta
        from knowledge_manager.schemas import ReviewRecord, StagingMeta

        subject = require_identity(request, kb_path, "module.review")
        staging = kb_path / ".staging"
        staged_module = load_from_staging(module_id, staging)
        if staged_module is None:
            raise HTTPException(404, f"Module not found: {module_id}")
        enforce_subject_module_access(subject, staged_module, kb_path)
        meta = load_staging_meta(module_id, staging)
        if meta is None:
            meta = StagingMeta(module_id=module_id)

        if body and "reviewer" in body and body["reviewer"] != subject.user:
            raise HTTPException(status_code=422, detail="reviewer is server-assigned")
        comment = (body or {}).get("comment", "No reason given")
        meta.reviews.append(ReviewRecord(reviewer=subject.user, action="changes-requested", comment=comment))
        meta.status = "changes-requested"
        save_staging_meta(meta, staging)
        log_audit_event(
            kb_path,
            AuditEvent(
                user=subject.user,
                operation="staging.reject",
                module_id=module_id,
                category=staged_module.category,
                tenant_id=subject.tenant_id,
                resource=f"/api/staging/{module_id}/reject",
                result="success",
                request_id=getattr(request.state, "request_id", ""),
            ),
        )
        return {"status": "changes-requested", "module_id": module_id}

    # ── Tree mutation (M6) ──

    @app.put("/api/tree")
    def api_tree_update(body: dict, request: Request):
        from knowledge_manager.storage import load_index, save_index, save_tree

        require_identity(request, kb_path, "module.write")
        action = body.get("action")
        node_id = body.get("node_id", "")
        new_parent = body.get("new_parent", "")
        position = body.get("position", 0)

        index = load_index(kb_path)
        if index is None or index.tree is None:
            raise HTTPException(404, "No tree structure found. Build it with km tree build --llm first.")

        tree = index.tree
        if action == "move" and node_id and new_parent:
            node, old_parent = _find_node_and_parent(tree, node_id)
            new_parent_node = _find_node_by_id(tree, new_parent)
            if node and new_parent_node:
                if old_parent:
                    old_parent.children = [c for c in old_parent.children if c.id != node.id]
                new_parent_node.children.insert(position, node)
                save_tree(tree, kb_path)

        return {"status": "updated"}

    def _find_node_and_parent(root, target_id: str):
        def _search(node, parent):
            if node.id == target_id:
                return node, parent
            for child in node.children:
                found, p = _search(child, node)
                if found:
                    return found, p
            return None, None
        return _search(root, None)

    def _find_node_by_id(root, target_id: str):
        if root.id == target_id:
            return root
        for child in root.children:
            found = _find_node_by_id(child, target_id)
            if found:
                return found
        return None

    # ── Chat (M2) ──

    class ChatRequest(BaseModel):
        query: str = Field(..., min_length=1)
        history: list[dict] = Field(default_factory=list)
        mode: str = Field(default="precise")

    @app.post("/api/chat")
    async def api_chat(body: ChatRequest):
        from knowledge_manager.chat import ChatPipeline
        from knowledge_manager.llm_clients import create_client

        cfg = _load_config()
        if not cfg or not cfg.llm_providers:
            raise HTTPException(503, "No LLM provider configured")
        provider_name, provider_cfg = cfg.get_default_provider()
        llm_client = create_client(provider_name, provider_cfg)
        pipeline = ChatPipeline(kb_path, llm_client)

        async def event_stream() -> AsyncIterator[str]:
            async for event in pipeline.chat(body.query, body.history, body.mode):
                yield f"event: {event.type}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ── Graph ──

    @app.get("/api/graph")
    def api_graph(request: Request, tenant_id: str = Query("")):
        tenant = resolve_tenant_context(request, kb_path, tenant_id=tenant_id)
        return build_tenant_graph(kb_path, tenant).model_dump()

    @app.get("/api/graph/{cat}/{mod_id}")
    def api_graph_node(request: Request, cat: str, mod_id: str, tenant_id: str = Query("")):
        tenant = resolve_tenant_context(request, kb_path, tenant_id=tenant_id)
        graph = build_tenant_subgraph(cat, mod_id, kb_path, tenant)
        if graph is None:
            raise HTTPException(404, f"Module not found: {cat}/{mod_id}")
        return graph.model_dump()

    # ── Recommendations ──

    @app.get("/api/recommendations")
    def api_recommendations(request: Request, tenant_id: str = Query("")):
        tenant = resolve_tenant_context(request, kb_path, tenant_id=tenant_id)
        report = build_tenant_recommendations(kb_path, tenant)
        return report.model_dump()

    @app.get("/api/ops")
    def api_ops(request: Request, tenant_id: str = Query(""), workspace_id: str = Query("")):
        require_identity(request, kb_path, "audit.read")
        tenant = resolve_tenant_context(
            request,
            kb_path,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        report = build_tenant_ops_report(kb_path, tenant)
        return report.model_dump()

    @app.get("/api/ops/backlog")
    def api_ops_backlog(request: Request, tenant_id: str = Query(""), workspace_id: str = Query("")):
        from knowledge_manager.ops_export import generate_review_backlog_export

        require_identity(request, kb_path, "audit.read")
        tenant = resolve_tenant_context(
            request,
            kb_path,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        export = generate_review_backlog_export(kb_path)
        return filter_review_backlog_export(kb_path, tenant, export)

    @app.get("/api/ops/backlog/review")
    def api_ops_backlog_review(request: Request, tenant_id: str = Query(""), workspace_id: str = Query("")):
        from knowledge_manager.ops_export import generate_review_backlog_export

        require_identity(request, kb_path, "audit.read")
        tenant = resolve_tenant_context(
            request,
            kb_path,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        export = generate_review_backlog_export(kb_path)
        return filter_review_backlog_export(kb_path, tenant, export)

    @app.get("/api/ops/backlog/risky-misses")
    def api_ops_backlog_risky_misses(request: Request):
        from knowledge_manager.ops_export import generate_risky_miss_export

        require_identity(request, kb_path, "config.manage")
        return generate_risky_miss_export(kb_path)

    @app.get("/api/ops/backlog/source")
    def api_ops_backlog_source(request: Request, tenant_id: str = Query(""), workspace_id: str = Query("")):
        from knowledge_manager.ops_export import generate_source_backlog_export

        require_identity(request, kb_path, "audit.read")
        tenant = resolve_tenant_context(
            request,
            kb_path,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        export = generate_source_backlog_export(kb_path)
        items = filter_source_backlog_items(kb_path, tenant, export.get("items", []))
        return {**export, "total": len(items), "items": items}

    @app.get("/api/dual-view")
    def api_dual_view(request: Request, tenant_id: str = Query(""), workspace_id: str = Query("")):
        from knowledge_manager.dual_view import build_dual_view

        require_identity(request, kb_path, "audit.read")
        tenant = resolve_tenant_context(
            request,
            kb_path,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        return build_dual_view(kb_path, tenant=tenant)

    @app.get("/api/source/jobs")
    def api_source_jobs(request: Request, tenant_id: str = Query(""), workspace_id: str = Query("")):
        from knowledge_manager.ingestion_jobs import list_ingestion_jobs

        subject = require_identity(request, kb_path, "audit.read")
        tenant = resolve_tenant_context(
            request,
            kb_path,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        jobs = list_ingestion_jobs(kb_path)
        if tenant is not None:
            jobs = [
                job for job in jobs
                if (
                    (not job.tenant_id and tenant.allow_global_reads)
                    or job.tenant_id == tenant.tenant_id
                ) and (
                    (not tenant.workspace_id)
                    or not job.workspace_id
                    or job.workspace_id == tenant.workspace_id
                )
            ]
        log_audit_event(
            kb_path,
            AuditEvent(
                user=subject.user,
                operation="source.jobs.read",
                tenant_id=subject.tenant_id,
                resource="/api/source/jobs",
                result="success",
                request_id=getattr(request.state, "request_id", ""),
            ),
        )
        return {
            "total": len(jobs),
            "items": [job.model_dump(mode="json") for job in jobs],
        }

    @app.post("/api/migrate/dry-run")
    def api_migrate_dry_run(request: MigrationDryRunRequest):
        from knowledge_manager.migration import dry_run_import

        source_path = Path(request.source_path)
        if not source_path.exists():
            raise HTTPException(status_code=404, detail="migration source not found")
        summary = dry_run_import(Path(request.source_path), source_kind=request.source_kind)
        return summary.model_dump()

    @app.get("/api/admin/dashboard")
    def api_admin_dashboard(request: Request, tenant_id: str = Query(""), workspace_id: str = Query("")):
        from knowledge_manager.admin_views import build_admin_dashboard

        subject = require_identity(request, kb_path, "config.manage")
        tenant = resolve_tenant_context(
            request,
            kb_path,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        log_audit_event(
            kb_path,
            AuditEvent(
                user=subject.user,
                operation="admin.dashboard.read",
                tenant_id=subject.tenant_id,
                resource="/api/admin/dashboard",
                result="success",
                request_id=getattr(request.state, "request_id", ""),
            ),
        )
        return build_admin_dashboard(kb_path, tenant=tenant)

    @app.post("/api/access/explain")
    def api_access_explain(request: AccessExplainRequest):
        from knowledge_manager.rbac import PermissionChecker

        checker = PermissionChecker(
            roles=request.roles,
            group_mapping=request.group_mapping,
        )
        decision = checker.explain_module_access(
            request.groups,
            {"category": request.category, "id": request.module_id},
        )
        return decision.model_dump()

    # ── UI entry ──

    @app.post("/api/upload")
    async def api_upload(
        request: Request,
        file: UploadFile = File(...),
        category: str = Form(default="general"),
        mode: str = Form(default="auto"),
    ):
        subject = require_identity(request, kb_path, "module.write")
        content = await file.read()
        filename = file.filename or "upload"
        job_id = _start_upload_job(
            kb_path,
            filename,
            content,
            category,
            mode,
            tenant_id=subject.tenant_id,
            workspace_id=subject.workspace_id,
        )
        log_audit_event(
            kb_path,
            AuditEvent(
                user=subject.user,
                operation="source.job.enqueue",
                tenant_id=subject.tenant_id,
                resource="/api/upload",
                result="accepted",
                details=f"job_id={job_id};filename={filename}",
                request_id=getattr(request.state, "request_id", ""),
            ),
        )
        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted",
                "job_id": job_id,
                "filename": filename,
            },
        )

    @app.get("/ui", response_class=HTMLResponse)
    def ui_entry():
        index_html = ui_dist / "index.html"
        if index_html.exists():
            return HTMLResponse(index_html.read_text(encoding="utf-8"))
        return RedirectResponse("/ui/fallback")

    @app.get("/ui/fallback", response_class=HTMLResponse)
    def ui_fallback():
        from knowledge_manager.ui_fallback import FALLBACK_HTML
        return HTMLResponse(FALLBACK_HTML, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

    # Serve static files if dist exists
    if ui_dist.exists():
        app.mount("/assets", StaticFiles(directory=str(ui_dist / "assets")), name="assets")

    from knowledge_manager.auth import inject_auth_middleware
    inject_auth_middleware(app, kb_path)

    return app


def _snippet(text: str, query: str, maxlen: int = 100) -> str:
    if not text or not query:
        return text[:maxlen] if len(text) > maxlen else text
    terms = query.lower().split()
    text_lower = text.lower()
    best_pos = -1
    for term in terms:
        pos = text_lower.find(term)
        if pos != -1 and (best_pos == -1 or pos < best_pos):
            best_pos = pos
    if best_pos == -1:
        return text[:maxlen] + ("..." if len(text) > maxlen else "")
    start = max(0, best_pos - maxlen // 2)
    end = min(len(text), best_pos + maxlen // 2)
    snippet = text[start:end]
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return prefix + snippet + suffix
