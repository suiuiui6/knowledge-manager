import json
import re
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from knowledge_manager.cache import ModuleCache
from knowledge_manager.tenancy import TenantContext, module_visible_to_tenant
from knowledge_manager.tenant_views import (
    build_tenant_graph,
    build_tenant_index,
    build_tenant_ops_report,
    build_tenant_recommendations,
    filter_review_backlog_export,
    filter_source_backlog_items,
)
from knowledge_manager.storage import (
    _load_config_safe,
    load_changelogs,
    load_federation,
    load_index,
    load_module,
    load_module_changelog,
    record_load_event,
    search_modules,
)


def _tenant_matches(session_tenant: TenantContext | None, requested_tenant_id: str) -> bool:
    if session_tenant is None or not requested_tenant_id:
        return True
    return session_tenant.tenant_id == requested_tenant_id


def _snippet(text: str, query: str, maxlen: int = 100) -> str:
    """Extract a snippet from text around the first occurrence of a query term."""
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


def _load_projection_documents(kb_path: Path) -> dict[str, dict]:
    from knowledge_manager.search_projection import (
        build_search_projection,
        load_search_projection_readonly,
        projection_document_complete,
    )

    payload = load_search_projection_readonly(kb_path)
    if payload is None:
        payload = build_search_projection(kb_path)
    documents = payload.get("documents", {})
    if documents and not all(projection_document_complete(document) for document in documents.values()):
        payload = build_search_projection(kb_path)
        documents = payload.get("documents", {})
    return documents


def _projection_visible_to_tenant(document: dict, tenant: TenantContext | None) -> bool:
    if tenant is None:
        return True
    doc_tenant = document.get("tenant_id", "")
    if doc_tenant == tenant.tenant_id:
        return True
    return tenant.allow_global_reads and not doc_tenant


def _projection_neighbor(target_kb: Path, ref: str) -> dict | None:
    parts = ref.split("/", 1)
    if len(parts) != 2:
        return None
    documents = _load_projection_documents(target_kb)
    document = documents.get(ref)
    if document is None:
        return None
    return {
        "id": document["module_id"],
        "category": document["category"],
        "title": document["title"],
        "summary": document["summary"],
        "tags": document.get("tags", []),
        "confidence": document.get("confidence", "medium"),
        "caveats": document.get("caveats", ""),
        "related_modules": document.get("related_modules", []),
        "tenant_id": document.get("tenant_id", ""),
        "workspace_id": document.get("workspace_id", ""),
        "content": {
            "overview": document.get("overview", ""),
            "details": document.get("details", ""),
            "examples": document.get("examples", ""),
            "references": document.get("references", ""),
        },
    }


def create_server(
    kb_path: Path,
    cache: ModuleCache | None = None,
    federation: dict | None = None,
    session_tenant: TenantContext | None = None,
    security_mode: str | None = None,
) -> FastMCP:
    if cache is None:
        cache = ModuleCache()

    # Session-level tracking: recently loaded module IDs for query context boosting
    _session_loaded: list[str] = []

    # Load federation namespaces if not provided
    if federation is None:
        federation = load_federation(kb_path)

    cfg = _load_config_safe(kb_path)
    resolved_security_mode = security_mode or (
        "multi_tenant" if cfg and cfg.security.multi_tenant_mode else "single_tenant"
    )
    global_resources_enabled = not (
        cfg and cfg.security.mcp_global_resources == "disabled"
    )
    untrusted_global_resources_allowed = global_resources_enabled and not (
        resolved_security_mode == "multi_tenant" and session_tenant is None
    )

    def _resolve_kb(namespace: str) -> Path:
        """Resolve a namespace to its kb_path. 'default' maps to the main KB."""
        if not namespace or namespace == "default":
            return kb_path
        if namespace not in federation:
            raise ValueError(f"Unknown namespace: {namespace}")
        return federation[namespace]["path"]

    def _effective_tenant(tenant_id: str = "") -> TenantContext | None:
        if session_tenant is not None:
            if tenant_id and not _tenant_matches(session_tenant, tenant_id):
                raise ValueError("tenant override is not allowed for this MCP session")
            return session_tenant
        return TenantContext(tenant_id=tenant_id) if tenant_id else None

    def _tenant_scoped_resources_available() -> bool:
        return session_tenant is not None

    def _resource_access_denied() -> str:
        return json.dumps({"error": "resource unavailable without trusted tenant context"})

    mcp = FastMCP("knowledge-manager")

    # ── Main KB resources ──

    if untrusted_global_resources_allowed or _tenant_scoped_resources_available():
        @mcp.resource("knowledge://index")
        def get_index() -> str:
            if session_tenant is not None:
                return build_tenant_index(kb_path, session_tenant).model_dump_json()
            index = load_index(kb_path)
            if index is None:
                return json.dumps({
                    "version": "1.0",
                    "description": "Empty knowledge base — use `km add` to populate",
                    "categories": {},
                    "stats": {},
                })
            return index.model_dump_json()

        @mcp.resource("knowledge://changelog/{module_key}")
        def get_module_changelog(module_key: str) -> str:
            """Get changelog history for a specific module (category/id)."""
            if resolved_security_mode == "multi_tenant":
                return _resource_access_denied()
            entries = load_module_changelog(kb_path, module_key)
            return json.dumps(entries, indent=2)

        @mcp.resource("knowledge://changelog")
        def get_changelog() -> str:
            """Get recent knowledge base changelog (last 7 days of module changes)."""
            if resolved_security_mode == "multi_tenant":
                return _resource_access_denied()
            changelogs = load_changelogs(kb_path, days=7)
            return json.dumps(changelogs, indent=2)

        @mcp.resource("knowledge://health")
        def get_health() -> str:
            """Get the full knowledge base health report."""
            if resolved_security_mode == "multi_tenant":
                return _resource_access_denied()
            from knowledge_manager.storage import generate_health_report
            report = generate_health_report(kb_path)
            return report.model_dump_json(indent=2)

        @mcp.resource("knowledge://health/{module_key}")
        def get_module_health(module_key: str) -> str:
            """Get health report for a specific module (category/id, single segment key)."""
            if resolved_security_mode == "multi_tenant":
                return _resource_access_denied()
            from knowledge_manager.storage import load_module, compute_module_health
            parts = module_key.split("/", 1)
            if len(parts) != 2:
                return json.dumps({"error": f"Invalid module key: {module_key}. Use 'category/id' format."})
            mod = load_module(parts[1], parts[0], kb_path)
            if mod is None:
                return json.dumps({"error": f"Module not found: {module_key}"})
            h = compute_module_health(mod, kb_path)
            return h.model_dump_json(indent=2)

        @mcp.resource("knowledge://stats")
        def get_stats() -> str:
            """Get knowledge base usage statistics (last 30 days)."""
            if resolved_security_mode == "multi_tenant":
                return _resource_access_denied()
            from knowledge_manager.storage import aggregate_usage_stats
            data = aggregate_usage_stats(kb_path, period_days=30)
            return data.model_dump_json(indent=2)

        @mcp.resource("knowledge://recommendations")
        def get_recommendations() -> str:
            """Get actionable recommendations for KB improvement."""
            if session_tenant is not None:
                return build_tenant_recommendations(kb_path, session_tenant).model_dump_json(indent=2)
            from knowledge_manager.storage import generate_recommendations
            report = generate_recommendations(kb_path)
            return report.model_dump_json(indent=2)

        @mcp.resource("knowledge://ops")
        def get_ops() -> str:
            """Get operator-focused source, lifecycle, and policy backlog report."""
            return build_tenant_ops_report(kb_path, session_tenant).model_dump_json(indent=2)

        @mcp.resource("knowledge://ops/backlog")
        def get_ops_backlog() -> str:
            """Get exportable review and stale-source backlog data."""
            from knowledge_manager.ops_export import generate_review_backlog_export

            export = generate_review_backlog_export(kb_path)
            export = filter_review_backlog_export(kb_path, session_tenant, export)
            return json.dumps(export, ensure_ascii=False, indent=2)

        @mcp.resource("knowledge://ops/backlog/review")
        def get_ops_backlog_review() -> str:
            """Get the staging review backlog export."""
            from knowledge_manager.ops_export import generate_review_backlog_export

            export = generate_review_backlog_export(kb_path)
            export = filter_review_backlog_export(kb_path, session_tenant, export)
            return json.dumps(export, ensure_ascii=False, indent=2)

        if resolved_security_mode != "multi_tenant":
            @mcp.resource("knowledge://ops/backlog/risky-misses")
            def get_ops_backlog_risky_misses() -> str:
                """Get queries that surfaced no final results."""
                from knowledge_manager.ops_export import generate_risky_miss_export

                return json.dumps(generate_risky_miss_export(kb_path), ensure_ascii=False, indent=2)

        @mcp.resource("knowledge://ops/backlog/source")
        def get_ops_backlog_source() -> str:
            """Get the stale-source backlog export."""
            from knowledge_manager.ops_export import generate_source_backlog_export

            export = generate_source_backlog_export(kb_path)
            items = filter_source_backlog_items(kb_path, session_tenant, export.get("items", []))
            return json.dumps({**export, "total": len(items), "items": items}, ensure_ascii=False, indent=2)

        @mcp.resource("knowledge://dual-view")
        def get_dual_view() -> str:
            """Get source-to-module and module-to-source projection data."""
            from knowledge_manager.dual_view import build_dual_view

            return json.dumps(build_dual_view(kb_path, tenant=session_tenant), ensure_ascii=False, indent=2)

    # ── Federation: namespace-scoped resources ──

    if federation and untrusted_global_resources_allowed:
        # Register namespace-scoped resources programmatically
        for ns_name, ns_data in federation.items():
            ns_path = ns_data["path"]

            def _make_index(path, name=ns_name):
                @mcp.resource(f"knowledge://{ns_name}/index")
                def handler() -> str:
                    index = load_index(path)
                    if index is None:
                        return json.dumps({"error": f"Namespace '{name}' has no index"})
                    return index.model_dump_json()
                return handler
            _make_index(ns_path)

            def _make_health(path, name=ns_name):
                @mcp.resource(f"knowledge://{ns_name}/health")
                def handler() -> str:
                    from knowledge_manager.storage import generate_health_report
                    report = generate_health_report(path)
                    return report.model_dump_json(indent=2)
                return handler
            _make_health(ns_path)

            def _make_stats(path, name=ns_name):
                @mcp.resource(f"knowledge://{ns_name}/stats")
                def handler() -> str:
                    from knowledge_manager.storage import aggregate_usage_stats
                    data = aggregate_usage_stats(path, period_days=30)
                    return data.model_dump_json(indent=2)
                return handler
            _make_stats(ns_path)

            def _make_changelog(path, name=ns_name):
                @mcp.resource(f"knowledge://{ns_name}/changelog")
                def handler() -> str:
                    changelogs = load_changelogs(path, days=7)
                    return json.dumps(changelogs, indent=2)
                return handler
            _make_changelog(ns_path)

        @mcp.resource("knowledge://federation/index")
        def get_federation_index() -> str:
            """Get a summary index of all federated knowledge bases."""
            summary = {"namespaces": {}, "total_namespaces": len(federation), "total_modules": 0}
            search_default_ns = []
            for ns_name, ns_data in federation.items():
                idx = ns_data["index"]
                module_count = sum(len(c.modules) for c in idx.categories.values())
                summary["total_modules"] += module_count
                summary["namespaces"][ns_name] = {
                    "description": ns_data["description"],
                    "total_modules": module_count,
                    "categories": list(idx.categories.keys()),
                    "last_updated": idx.updated_at.isoformat() if idx.updated_at else "",
                    "search_default": ns_data["search_default"],
                }
                if ns_data["search_default"]:
                    search_default_ns.append(ns_name)
            summary["search_default_namespaces"] = search_default_ns
            return json.dumps(summary, indent=2)

    # ── Tools ──

    @mcp.tool(name="knowledge_graph")
    def knowledge_graph_tool(query: str = "", tenant_id: str = "") -> str:
        """Return knowledge graph statistics or find related modules by query."""
        from knowledge_manager.storage import analyze_graph, detect_clusters, search_modules, list_modules

        try:
            tenant = _effective_tenant(tenant_id)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        if query:
            results = [
                result
                for result in search_modules(query, kb_path, limit=5, tenant=tenant)
                if tenant is None or module_visible_to_tenant(result.module, tenant)
            ]
            output = {"query": query, "results": []}
            for sr in results:
                node = {
                    "id": f"{sr.module.category}/{sr.module.id}",
                    "title": sr.module.title,
                    "related_modules": sr.module.metadata.related_modules,
                }
                output["results"].append(node)
            return json.dumps(output, indent=2)

        if tenant is not None:
            graph = build_tenant_graph(kb_path, tenant)
            return json.dumps({"stats": graph.stats, "clusters": [], "graph": graph.model_dump()}, indent=2)
        gs = analyze_graph(kb_path)
        clusters = detect_clusters(kb_path)
        return json.dumps({
            "stats": gs.model_dump(),
            "clusters": [c.model_dump() for c in clusters],
        }, indent=2)

    @mcp.tool(name="load_module")
    def load_module_tool(module_id: str, category: str, namespace: str = "default", tenant_id: str = "") -> str:
        """Load a full knowledge module by ID and category. Use namespace for federated KBs."""
        target_kb = _resolve_kb(namespace)
        try:
            tenant = _effective_tenant(tenant_id)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        cached = cache.get(module_id, namespace, category)
        if cached is not None and (tenant is None or module_visible_to_tenant(cached, tenant)):
            return cached.model_dump_json(indent=2)

        module = load_module(module_id, category, target_kb)
        if module is None:
            return f"Module not found: {module_id} in category {category}"
        if tenant is not None and not module_visible_to_tenant(module, tenant):
            return f"Module not found: {module_id} in category {category}"

        cache.put(module, namespace)
        record_load_event(module_id, category, target_kb)
        module_key = f"{module.category}/{module.id}"
        if module_key in _session_loaded:
            _session_loaded.remove(module_key)
        _session_loaded.append(module_key)
        if len(_session_loaded) > 20:
            _session_loaded.pop(0)
        return module.model_dump_json(indent=2)

    @mcp.tool(name="search_modules")
    def search_modules_tool(
        query: str,
        category: str = "",
        include_archived: bool = False,
        namespace: str = "default",
        agent_id: str = "",
        task_type: str = "",
        risk_level: str = "",
        tenant_id: str = "",
    ) -> str:
        """Search modules by keyword. Use namespace for federated KBs."""
        target_kb = _resolve_kb(namespace)
        try:
            tenant = _effective_tenant(tenant_id)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        results = [
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
                "caveats": r.module.content.caveats,
                "related_modules": r.module.metadata.related_modules,
                "snippet": _snippet(r.module.content.overview, query),
            }
            for r in search_modules(
                query,
                target_kb,
                category if category else None,
                boost_ids=_session_loaded,
                include_archived=include_archived,
                agent_id=agent_id or None,
                task_type=task_type or None,
                risk_level=risk_level or None,
                tenant=tenant,
            )
            if tenant is None or module_visible_to_tenant(r.module, tenant)
        ]
        return json.dumps(results, separators=(",", ":"))

    @mcp.tool(name="list_categories")
    def list_categories_tool(namespace: str = "default", tenant_id: str = "") -> str:
        """List all categories and their module counts. Use namespace for federated KBs."""
        target_kb = _resolve_kb(namespace)
        try:
            tenant = _effective_tenant(tenant_id)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        if tenant is None:
            index = load_index(target_kb)
            if index is None:
                return json.dumps([])
            result = [
                {
                    "category": name,
                    "module_count": len(cat.modules),
                    "description": cat.description,
                }
                for name, cat in index.categories.items()
            ]
            return json.dumps(result, indent=2)

        from knowledge_manager.storage import list_modules

        categories: dict[str, int] = {}
        for module in list_modules(target_kb, tenant=tenant):
            categories[module.category] = categories.get(module.category, 0) + 1
        result = [
            {"category": name, "module_count": count, "description": ""}
            for name, count in sorted(categories.items())
        ]
        return json.dumps(result, indent=2)

    @mcp.tool(name="expand_module")
    def expand_module_tool(module_id: str, category: str, namespace: str = "default", tenant_id: str = "") -> str:
        """Load a module and its directly related neighbor modules (1-hop graph expansion)."""
        target_kb = _resolve_kb(namespace)
        try:
            tenant = _effective_tenant(tenant_id)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        module = load_module(module_id, category, target_kb)
        if module is None or (tenant is not None and not module_visible_to_tenant(module, tenant)):
            return json.dumps({"error": f"Module not found: {module_id} in category {category}"})

        neighbors = []
        for ref in module.metadata.related_modules:
            parts = ref.split("/", 1)
            if len(parts) != 2:
                continue
            n = load_module(parts[1], parts[0], target_kb)
            if n is not None and (tenant is None or module_visible_to_tenant(n, tenant)):
                neighbors.append({
                    "id": n.id,
                    "category": n.category,
                    "title": n.title,
                    "summary": n.summary,
                    "tags": n.metadata.tags,
                    "confidence": n.metadata.confidence,
                    "caveats": n.content.caveats,
                    "related_modules": n.metadata.related_modules,
                })

        return json.dumps({
            "module": {
                "id": module.id,
                "category": module.category,
                "title": module.title,
                "summary": module.summary,
                "confidence": module.metadata.confidence,
            },
            "neighbors": neighbors,
        }, separators=(",", ":"))

    @mcp.tool(name="deep_search")
    def deep_search_tool(query: str, category: str = "", namespace: str = "default", tenant_id: str = "") -> str:
        """Search, expand top results, and load full content — all in one call.

        Returns top-3 search results with full module content, plus neighbors for
        each via graph expansion. Use namespace for federated KBs.
        """
        target_kb = _resolve_kb(namespace)
        try:
            tenant = _effective_tenant(tenant_id)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        search_results = search_modules(
            query,
            target_kb,
            category if category else None,
            limit=3,
            boost_ids=_session_loaded,
            tenant=tenant,
        )
        output = []
        for sr in search_results:
            if tenant is not None and not module_visible_to_tenant(sr.module, tenant):
                continue
            module_data = {
                "id": sr.module.id,
                "category": sr.module.category,
                "title": sr.module.title,
                "summary": sr.module.summary,
                "tags": sr.module.metadata.tags,
                "confidence": sr.module.metadata.confidence,
                "source": sr.source,
                "caveats": sr.module.content.caveats,
                "related_modules": sr.module.metadata.related_modules,
                "content": {
                    "overview": sr.module.content.overview,
                    "details": sr.module.content.details,
                    "examples": sr.module.content.examples,
                    "references": sr.module.content.references,
                },
            }
            neighbors = []
            for ref in sr.module.metadata.related_modules:
                neighbor = _projection_neighbor(target_kb, ref)
                if neighbor is None or not _projection_visible_to_tenant(neighbor, tenant):
                    continue
                neighbors.append({
                    "id": neighbor["id"],
                    "category": neighbor["category"],
                    "title": neighbor["title"],
                    "summary": neighbor["summary"],
                    "confidence": neighbor["confidence"],
                })
            module_data["neighbors"] = neighbors
            output.append(module_data)
        return json.dumps(output, separators=(",", ":"))

    @mcp.tool(name="explain_access")
    def explain_access_tool(
        groups: list[str],
        category: str,
        module_id: str,
        roles: dict | None = None,
        group_mapping: dict | None = None,
    ) -> str:
        """Explain whether the provided groups can read a module."""
        from knowledge_manager.rbac import PermissionChecker

        checker = PermissionChecker(
            roles=roles or {},
            group_mapping=group_mapping or {},
        )
        decision = checker.explain_module_access(
            groups,
            {"category": category, "id": module_id},
        )
        return decision.model_dump_json(indent=2)

    # ── Lint resource (M7) ──

    if untrusted_global_resources_allowed:
        @mcp.resource("knowledge://lint")
        def get_lint() -> str:
            """Get knowledge base contradiction and structural issue report."""
            from knowledge_manager.linter import DeepLinter

            linter = DeepLinter(kb_path)
            issues = linter.lint_all("quick")
            return json.dumps([i.model_dump() for i in issues], indent=2, default=str)

    # ── Research tool (M4) ──

    @mcp.tool(name="research")
    async def research_tool(query: str, depth: str = "shallow") -> str:
        """Research a topic when knowledge base has no relevant modules.

        Args:
            query: Research question
            depth: \"shallow\" (fast) or \"deep\" (thorough)

        Returns:
            Research result with temporary answer and staged module list
        """
        from knowledge_manager.researcher import Researcher
        from knowledge_manager.llm_clients import create_client

        cfg = _load_config_safe(kb_path)
        if cfg is None:
            return json.dumps({"error": "No config found"})
        try:
            provider_name, provider_cfg = cfg.get_default_provider()
        except ValueError:
            return json.dumps({"error": "No LLM provider configured"})

        llm_client = create_client(provider_name, provider_cfg)
        researcher = Researcher(kb_path, cfg.research, llm_client)

        result = await researcher.research(query, depth)
        return json.dumps({
            "query": result.query,
            "temporary_answer": result.answer_synthesis[:500],
            "staged_modules": result.staged_ids,
            "sources_used": result.sources_used,
            "took_ms": result.took_ms,
            "hint": f"Use km review to review staged modules: {', '.join(result.staged_ids)}" if result.staged_ids else "",
        }, indent=2)

    # ── Federation: federated_search tool ──

    if federation:

        @mcp.tool(name="federated_search")
        def federated_search_tool(query: str, namespaces: str = "", top_per_ns: int = 5) -> str:
            """Search across multiple federated knowledge bases.

            Args:
                query: Search query string.
                namespaces: Comma-separated namespace names. Empty = all search_default namespaces.
                top_per_ns: Maximum results per namespace.
            """
            if namespaces:
                ns_list = [n.strip() for n in namespaces.split(",") if n.strip()]
            else:
                ns_list = [n for n, d in federation.items() if d.get("search_default", True)]

            output: dict = {"query": query, "results": {}}
            for ns_name in ns_list:
                if ns_name not in federation:
                    output["results"][ns_name] = {"error": f"Unknown namespace: {ns_name}"}
                    continue
                ns_path = federation[ns_name]["path"]
                ns_results = search_modules(query, ns_path, limit=top_per_ns)
                output["results"][ns_name] = [
                    {
                        "id": r.module.id,
                        "category": r.module.category,
                        "title": r.module.title,
                        "summary": r.module.summary,
                        "tags": r.module.metadata.tags,
                        "confidence": r.module.metadata.confidence,
                        "status": r.module.metadata.status,
                        "source": r.source,
                        "caveats": r.module.content.caveats,
                        "related_modules": r.module.metadata.related_modules,
                        "snippet": _snippet(r.module.content.overview, query),
                    }
                    for r in ns_results
                ]
                output["results"][ns_name + "_count"] = len(output["results"][ns_name])
            return json.dumps(output, indent=2)

    # ── Write Tools (P0) ──

    @mcp.tool(name="create_module")
    def create_module_tool(title: str, content: str, category: str = "general",
                           summary: str = "", tags: str = "", confidence: str = "medium") -> str:
        """Create a new knowledge module and stage it for review.

        Args:
            title: Module title (5+ chars)
            content: Main content body (overview/details combined)
            category: Category name (existing or new)
            summary: One-line summary (auto-generated if empty)
            tags: Comma-separated tags
            confidence: high/medium/low
        """
        from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata, StagingMeta
        from knowledge_manager.storage import save_to_staging, save_staging_meta

        if len(title) < 5:
            return json.dumps({"error": "Title must be at least 5 characters"})
        if len(content) < 20:
            return json.dumps({"error": "Content must be at least 20 characters"})
        if confidence not in ("high", "medium", "low"):
            confidence = "medium"

        import re as _re
        mod_id = _re.sub(r"[^a-z0-9-]", "", title.lower().replace(" ", "-"))[:50]

        module = Module(
            id=mod_id,
            category=category,
            title=title,
            summary=summary or title,
            content=ModuleContent(
                overview=content[:200],
                details=content,
            ),
            metadata=ModuleMetadata(
                tags=[t.strip() for t in tags.split(",") if t.strip()],
                confidence=confidence,
                status="draft",
            ),
        )

        staging = kb_path / ".staging"
        staging.mkdir(exist_ok=True)
        save_to_staging(module, staging)
        meta = StagingMeta(module_id=mod_id, submitted_by="mcp-agent")
        save_staging_meta(meta, staging)

        return json.dumps({
            "status": "staged",
            "module_id": mod_id,
            "category": category,
            "title": title,
            "hint": f"Module staged for review. Use km review approve {category}/{mod_id} to publish.",
        }, indent=2)

    @mcp.tool(name="update_module")
    def update_module_tool(module_id: str, category: str, title: str = "",
                           content: str = "", summary: str = "",
                           tags: str = "", confidence: str = "") -> str:
        """Update an existing module's fields. Only specified fields are changed.

        Args:
            module_id: Module ID to update
            category: Module's category
            title: New title (empty = no change)
            content: New content (empty = no change)
            summary: New summary (empty = no change)
            tags: New comma-separated tags (empty = no change)
            confidence: New confidence level (empty = no change)
        """
        from knowledge_manager.storage import load_module, save_module

        mod = load_module(module_id, category, kb_path)
        if mod is None:
            return json.dumps({"error": f"Module not found: {category}/{module_id}"})

        if title and len(title) >= 5:
            mod.title = title
        if summary:
            mod.summary = summary
        if content and len(content) >= 20:
            mod.content.details = content
        if tags:
            mod.metadata.tags = [t.strip() for t in tags.split(",") if t.strip()]
        if confidence in ("high", "medium", "low"):
            mod.metadata.confidence = confidence

        save_module(mod, kb_path)
        return json.dumps({
            "status": "updated",
            "module_id": module_id,
            "category": category,
            "title": mod.title,
        }, indent=2)

    @mcp.tool(name="delete_module")
    def delete_module_tool(module_id: str, category: str) -> str:
        """Archive a module (soft delete). Archived modules are hidden from search by default.

        Args:
            module_id: Module ID to archive
            category: Module's category
        """
        from knowledge_manager.storage import load_module, save_module

        mod = load_module(module_id, category, kb_path)
        if mod is None:
            return json.dumps({"error": f"Module not found: {category}/{module_id}"})

        mod.metadata.status = "archived"
        save_module(mod, kb_path)
        return json.dumps({
            "status": "archived",
            "module_id": module_id,
            "category": category,
            "hint": "Module archived. Use include_archived=true in search to find it.",
        }, indent=2)

    return mcp
