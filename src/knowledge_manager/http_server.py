from datetime import datetime, timezone
from pathlib import Path

import json
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from knowledge_manager.schemas import GraphData, GraphEdge, GraphNode, PaginatedResponse
from knowledge_manager.storage import (
    aggregate_usage_stats,
    analyze_graph,
    generate_health_report,
    generate_recommendations,
    get_subtree,
    get_tree,
    load_index,
    load_module,
    list_modules,
    search_modules,
)


def _load_config_safe(kb_path: Path):
    from knowledge_manager.schemas import Config

    cfg_path = kb_path / "config.json"
    if not cfg_path.exists():
        return None
    try:
        return Config.model_validate_json(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def create_app(kb_path: Path) -> FastAPI:
    app = FastAPI(title="Knowledge Manager", version="0.5.0")

    def _load_config():
        return _load_config_safe(kb_path)

    ui_dist = Path(__file__).resolve().parent.parent.parent / "src" / "ui" / "dist"

    # ── Health ──

    @app.get("/api/health")
    def api_health():
        report = generate_health_report(kb_path)
        return report.model_dump()

    # ── Stats ──

    @app.get("/api/stats")
    def api_stats(period: int = Query(30, ge=7, le=90)):
        data = aggregate_usage_stats(kb_path, period_days=period)
        return data.model_dump()

    # ── Index ──

    @app.get("/api/index")
    def api_index():
        index = load_index(kb_path)
        if index is None:
            return {"version": "1.0", "categories": {}, "stats": {"total_modules": 0}}
        d = index.model_dump()
        d.pop("graph", None)
        d.pop("tree", None)
        return d

    # ── Tree ──

    @app.get("/api/tree")
    def api_tree():
        tree = get_tree(kb_path)
        return tree.model_dump()

    @app.get("/api/tree/{cat}/{mod_id}")
    def api_tree_node(cat: str, mod_id: str):
        subtree = get_subtree(cat, mod_id, kb_path)
        if subtree is None:
            raise HTTPException(404, f"Module not found: {cat}/{mod_id}")
        return subtree.model_dump()

    # ── Modules ──

    @app.get("/api/modules")
    def api_modules_list(
        category: str = Query(""),
        status: str = Query(""),
        tag: str = Query(""),
        page: int = Query(1, ge=1),
        limit: int = Query(50, ge=1, le=200),
    ):
        modules = list_modules(kb_path)
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
    def api_module_detail(cat: str, mod_id: str, include_archived: bool = Query(False)):
        # Handle .md suffix: strip and return 501 for M1
        if mod_id.endswith(".md"):
            real_id = mod_id[:-3]
            md_path = kb_path / cat / f"{real_id}.md"
            if md_path.exists():
                from fastapi.responses import PlainTextResponse
                return PlainTextResponse(md_path.read_text(encoding="utf-8"), media_type="text/markdown")
            if load_module(real_id, cat, kb_path) is None:
                raise HTTPException(404, f"Module not found: {cat}/{real_id}")
            # Module exists but no .md file yet — generate on the fly
            module = load_module(real_id, cat, kb_path)
            from knowledge_manager.markdown import render_markdown_module
            from fastapi.responses import PlainTextResponse
            return PlainTextResponse(render_markdown_module(module), media_type="text/markdown")
        module = load_module(mod_id, cat, kb_path)
        if module is None:
            raise HTTPException(404, f"Module not found: {cat}/{mod_id}")
        if module.metadata.status == "archived" and not include_archived:
            raise HTTPException(410, f"Module archived: {cat}/{mod_id}")
        return module.model_dump()

    # ── Search ──

    @app.post("/api/search")
    def api_search(body: dict):
        query = (body.get("query") or "").strip()
        if not query:
            raise HTTPException(422, "query is required")
        category = body.get("category") or None
        include_archived = body.get("include_archived", False)
        top_k = min(body.get("top_k", 10), 50)

        results = search_modules(query, kb_path, category=category, limit=top_k, include_archived=include_archived)

        from knowledge_manager.storage import _classify_intent

        intent = _classify_intent(query)
        return {
            "query": query,
            "intent": intent,
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
    def api_module_create(body: dict):
        from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata

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

        submit_to_staging = body.get("submit_to_staging", True)
        if submit_to_staging:
            from knowledge_manager.storage import save_to_staging, save_staging_meta
            from knowledge_manager.schemas import StagingMeta

            staging = kb_path / ".staging"
            staging.mkdir(exist_ok=True)
            save_to_staging(module, staging)
            save_staging_meta(StagingMeta(module_id=module.id, submitted_by="web-ui"), staging)
            return {"id": module.id, "category": module.category, "status": "staged", "review_required": True}

        from knowledge_manager.storage import save_module, rebuild_index
        save_module(module, kb_path)
        rebuild_index(kb_path)
        return module.model_dump()

    @app.put("/api/modules/{cat}/{mod_id}")
    def api_module_update(cat: str, mod_id: str, body: dict):
        module = load_module(mod_id, cat, kb_path)
        if module is None:
            raise HTTPException(404, f"Module not found: {cat}/{mod_id}")

        for field in ("title", "summary"):
            if field in body:
                setattr(module, field, body[field])
        if "content" in body:
            for k, v in body["content"].items():
                if hasattr(module.content, k) and v:
                    setattr(module.content, k, v)
        if "metadata" in body:
            for k, v in body["metadata"].items():
                if hasattr(module.metadata, k):
                    setattr(module.metadata, k, v)
            module.updated_at = datetime.now(timezone.utc)

        from knowledge_manager.storage import save_module, rebuild_index
        save_module(module, kb_path)
        rebuild_index(kb_path)
        return module.model_dump()

    @app.delete("/api/modules/{cat}/{mod_id}")
    def api_module_delete(cat: str, mod_id: str):
        from knowledge_manager.storage import delete_module, load_index, save_index

        if not delete_module(mod_id, cat, kb_path):
            raise HTTPException(404, f"Module not found: {cat}/{mod_id}")
        index = load_index(kb_path)
        if index:
            index.remove_module(mod_id, cat)
            save_index(index, kb_path)
        return {"deleted": f"{cat}/{mod_id}"}

    # ── Staging API (M6) ──

    @app.get("/api/staging")
    def api_staging_list():
        from knowledge_manager.storage import list_staging, load_staging_meta

        staging = kb_path / ".staging"
        items = []
        for m in list_staging(staging):
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
    def api_staging_approve(module_id: str, body: dict | None = None):
        from knowledge_manager.storage import (
            approve_from_staging, load_staging_meta, list_staging,
            save_staging_meta, rebuild_index,
        )
        from knowledge_manager.schemas import ReviewRecord, StagingMeta

        staging = kb_path / ".staging"
        meta = load_staging_meta(module_id, staging)
        if meta is None:
            meta = StagingMeta(module_id=module_id)

        comment = (body or {}).get("comment", "")
        user = (body or {}).get("reviewer", "web-ui")
        meta.reviews.append(ReviewRecord(reviewer=user, action="approved", comment=comment))

        cfg = _load_config()
        required = cfg.review.required_approvals if cfg else 1
        if meta.approval_count() >= required:
            approve_from_staging(module_id, staging, kb_path)
            rebuild_index(kb_path)
            return {"status": "merged", "approvals": meta.approval_count()}
        save_staging_meta(meta, staging)
        return {"status": "pending", "approvals": meta.approval_count(), "required": required}

    @app.post("/api/staging/{module_id}/reject")
    def api_staging_reject(module_id: str, body: dict | None = None):
        from knowledge_manager.storage import load_staging_meta, save_staging_meta
        from knowledge_manager.schemas import ReviewRecord, StagingMeta

        staging = kb_path / ".staging"
        meta = load_staging_meta(module_id, staging)
        if meta is None:
            meta = StagingMeta(module_id=module_id)

        comment = (body or {}).get("comment", "No reason given")
        user = (body or {}).get("reviewer", "web-ui")
        meta.reviews.append(ReviewRecord(reviewer=user, action="changes-requested", comment=comment))
        meta.status = "changes-requested"
        save_staging_meta(meta, staging)
        return {"status": "changes-requested", "module_id": module_id}

    # ── Tree mutation (M6) ──

    @app.put("/api/tree")
    def api_tree_update(body: dict):
        from knowledge_manager.storage import load_index, save_index, save_tree

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
    def api_graph():
        index = load_index(kb_path)
        if index is None:
            return GraphData().model_dump()

        gs = analyze_graph(kb_path)
        nodes = []
        for cat_name, cat in index.categories.items():
            for m in cat.modules:
                key = f"{cat_name}/{m.id}"
                in_deg = 0
                out_deg = len(index.graph.get(key, []))
                for targets in index.graph.values():
                    if key in targets:
                        in_deg += 1
                nodes.append(GraphNode(
                    id=key, label=m.title, category=cat_name,
                    in_degree=in_deg, out_degree=out_deg,
                ))
        edges = []
        for src, targets in index.graph.items():
            for t in targets:
                edges.append(GraphEdge(source=src, target=t, weight=1.0))

        return GraphData(
            nodes=nodes,
            edges=edges,
            stats={"total_nodes": gs.total_nodes, "total_edges": gs.total_edges, "density": gs.density},
        ).model_dump()

    @app.get("/api/graph/{cat}/{mod_id}")
    def api_graph_node(cat: str, mod_id: str):
        index = load_index(kb_path)
        if index is None:
            raise HTTPException(404, "No knowledge base")
        center_key = f"{cat}/{mod_id}"
        module = load_module(mod_id, cat, kb_path)
        if module is None:
            raise HTTPException(404, f"Module not found: {center_key}")

        related = set(module.metadata.related_modules)
        related.add(center_key)
        nodes = []
        edges = []
        for ref in related:
            parts = ref.split("/", 1)
            if len(parts) != 2:
                continue
            ref_module = load_module(parts[1], parts[0], kb_path)
            if ref_module is None:
                continue
            nodes.append(GraphNode(
                id=ref, label=ref_module.title, category=parts[0],
                status=ref_module.metadata.status,
            ))
        for ref in module.metadata.related_modules:
            edges.append(GraphEdge(source=center_key, target=ref, weight=1.0))
        for ref in module.metadata.related_modules:
            ref_parts = ref.split("/", 1)
            if len(ref_parts) == 2:
                ref_mod = load_module(ref_parts[1], ref_parts[0], kb_path)
                if ref_mod:
                    for r2 in ref_mod.metadata.related_modules:
                        if r2 in related and r2 != ref:
                            edges.append(GraphEdge(source=ref, target=r2, weight=0.5))

        return GraphData(nodes=nodes, edges=edges, stats={"center": center_key, "depth": 1}).model_dump()

    # ── Recommendations ──

    @app.get("/api/recommendations")
    def api_recommendations():
        report = generate_recommendations(kb_path)
        return report.model_dump()

    # ── UI entry ──

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
