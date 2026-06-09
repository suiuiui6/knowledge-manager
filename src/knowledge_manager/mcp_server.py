import json
import re
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from knowledge_manager.cache import ModuleCache
from knowledge_manager.storage import load_changelogs, load_federation, load_index, load_module, load_module_changelog, record_load_event, search_modules


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


def create_server(kb_path: Path, cache: ModuleCache | None = None, federation: dict | None = None) -> FastMCP:
    if cache is None:
        cache = ModuleCache()

    # Session-level tracking: recently loaded module IDs for query context boosting
    _session_loaded: list[str] = []

    # Load federation namespaces if not provided
    if federation is None:
        federation = load_federation(kb_path)

    def _resolve_kb(namespace: str) -> Path:
        """Resolve a namespace to its kb_path. 'default' maps to the main KB."""
        if not namespace or namespace == "default":
            return kb_path
        if namespace not in federation:
            raise ValueError(f"Unknown namespace: {namespace}")
        return federation[namespace]["path"]

    mcp = FastMCP("knowledge-manager")

    # ── Main KB resources ──

    @mcp.resource("knowledge://index")
    def get_index() -> str:
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
        entries = load_module_changelog(kb_path, module_key)
        return json.dumps(entries, indent=2)

    @mcp.resource("knowledge://changelog")
    def get_changelog() -> str:
        """Get recent knowledge base changelog (last 7 days of module changes)."""
        changelogs = load_changelogs(kb_path, days=7)
        return json.dumps(changelogs, indent=2)

    @mcp.resource("knowledge://health")
    def get_health() -> str:
        """Get the full knowledge base health report."""
        from knowledge_manager.storage import generate_health_report
        report = generate_health_report(kb_path)
        return report.model_dump_json(indent=2)

    @mcp.resource("knowledge://health/{module_key}")
    def get_module_health(module_key: str) -> str:
        """Get health report for a specific module (category/id, single segment key)."""
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
        from knowledge_manager.storage import aggregate_usage_stats
        data = aggregate_usage_stats(kb_path, period_days=30)
        return data.model_dump_json(indent=2)

    @mcp.resource("knowledge://recommendations")
    def get_recommendations() -> str:
        """Get actionable recommendations for KB improvement."""
        from knowledge_manager.storage import generate_recommendations
        report = generate_recommendations(kb_path)
        return report.model_dump_json(indent=2)

    # ── Federation: namespace-scoped resources ──

    if federation:
        # Register namespace-scoped resources programmatically
        for ns_name, ns_data in federation.items():
            ns_path = ns_data["path"]

            def _make_index(path):
                @mcp.resource(f"knowledge://{ns_name}/index")
                def handler() -> str:
                    index = load_index(path)
                    if index is None:
                        return json.dumps({"error": f"Namespace '{ns_name}' has no index"})
                    return index.model_dump_json()
                return handler
            _make_index(ns_path)

            def _make_health(path):
                @mcp.resource(f"knowledge://{ns_name}/health")
                def handler() -> str:
                    from knowledge_manager.storage import generate_health_report
                    report = generate_health_report(path)
                    return report.model_dump_json(indent=2)
                return handler
            _make_health(ns_path)

            def _make_stats(path):
                @mcp.resource(f"knowledge://{ns_name}/stats")
                def handler() -> str:
                    from knowledge_manager.storage import aggregate_usage_stats
                    data = aggregate_usage_stats(path, period_days=30)
                    return data.model_dump_json(indent=2)
                return handler
            _make_stats(ns_path)

            def _make_changelog(path):
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
    def knowledge_graph_tool(query: str = "") -> str:
        """Return knowledge graph statistics or find related modules by query."""
        from knowledge_manager.storage import analyze_graph, detect_clusters, search_modules

        if query:
            results = search_modules(query, kb_path, limit=5)
            output = {"query": query, "results": []}
            for sr in results:
                node = {
                    "id": f"{sr.module.category}/{sr.module.id}",
                    "title": sr.module.title,
                    "related_modules": sr.module.metadata.related_modules,
                }
                output["results"].append(node)
            return json.dumps(output, indent=2)

        gs = analyze_graph(kb_path)
        clusters = detect_clusters(kb_path)
        return json.dumps({
            "stats": gs.model_dump(),
            "clusters": [c.model_dump() for c in clusters],
        }, indent=2)

    @mcp.tool(name="load_module")
    def load_module_tool(module_id: str, category: str, namespace: str = "default") -> str:
        """Load a full knowledge module by ID and category. Use namespace for federated KBs."""
        target_kb = _resolve_kb(namespace)
        ns_key = f"{namespace}:{module_id}"
        cached = cache.get(module_id, namespace)
        if cached is not None:
            return cached.model_dump_json(indent=2)

        module = load_module(module_id, category, target_kb)
        if module is None:
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
    def search_modules_tool(query: str, category: str = "", include_archived: bool = False, namespace: str = "default") -> str:
        """Search modules by keyword. Use namespace for federated KBs."""
        target_kb = _resolve_kb(namespace)
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
                "caveats": r.module.content.caveats,
                "related_modules": r.module.metadata.related_modules,
                "snippet": _snippet(r.module.content.overview, query),
            }
            for r in search_modules(query, target_kb, category if category else None, boost_ids=_session_loaded, include_archived=include_archived)
        ]
        return json.dumps(results, indent=2)

    @mcp.tool(name="list_categories")
    def list_categories_tool(namespace: str = "default") -> str:
        """List all categories and their module counts. Use namespace for federated KBs."""
        target_kb = _resolve_kb(namespace)
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

    @mcp.tool(name="expand_module")
    def expand_module_tool(module_id: str, category: str, namespace: str = "default") -> str:
        """Load a module and its directly related neighbor modules (1-hop graph expansion)."""
        target_kb = _resolve_kb(namespace)
        module = load_module(module_id, category, target_kb)
        if module is None:
            return json.dumps({"error": f"Module not found: {module_id} in category {category}"})

        neighbors = []
        for ref in module.metadata.related_modules:
            parts = ref.split("/", 1)
            if len(parts) != 2:
                continue
            n = load_module(parts[1], parts[0], target_kb)
            if n is not None:
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
        }, indent=2)

    @mcp.tool(name="deep_search")
    def deep_search_tool(query: str, category: str = "", namespace: str = "default") -> str:
        """Search, expand top results, and load full content — all in one call.

        Returns top-3 search results with full module content, plus neighbors for
        each via graph expansion. Use namespace for federated KBs.
        """
        target_kb = _resolve_kb(namespace)
        search_results = search_modules(query, target_kb, category if category else None, limit=3, boost_ids=_session_loaded)
        output = []
        for sr in search_results:
            full = load_module(sr.module.id, sr.module.category, target_kb)
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
            }
            if full is not None:
                module_data["content"] = {
                    "overview": full.content.overview,
                    "details": full.content.details,
                    "examples": full.content.examples,
                    "references": full.content.references,
                }
            neighbors = []
            for ref in sr.module.metadata.related_modules:
                parts = ref.split("/", 1)
                if len(parts) == 2:
                    n = load_module(parts[1], parts[0], target_kb)
                    if n is not None:
                        neighbors.append({
                            "id": n.id,
                            "category": n.category,
                            "title": n.title,
                            "summary": n.summary,
                            "confidence": n.metadata.confidence,
                        })
            module_data["neighbors"] = neighbors
            output.append(module_data)
        return json.dumps(output, indent=2)

    # ── Research tool (M4) ──

    @mcp.tool(name="research")
    def research_tool(query: str, depth: str = "shallow") -> str:
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

        result = asyncio.run(researcher.research(query, depth))
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

    return mcp
