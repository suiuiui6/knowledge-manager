import json
import re
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from knowledge_manager.cache import ModuleCache
from knowledge_manager.storage import load_index, load_module, record_load_event, search_modules


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


def create_server(kb_path: Path, cache: ModuleCache | None = None) -> FastMCP:
    if cache is None:
        cache = ModuleCache()

    mcp = FastMCP("knowledge-manager")

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

    @mcp.tool(name="load_module")
    def load_module_tool(module_id: str, category: str) -> str:
        """Load a full knowledge module by ID and category."""
        cached = cache.get(module_id)
        if cached is not None:
            return cached.model_dump_json(indent=2)

        module = load_module(module_id, category, kb_path)
        if module is None:
            return f"Module not found: {module_id} in category {category}"

        cache.put(module)
        record_load_event(module_id, category, kb_path)
        return module.model_dump_json(indent=2)

    @mcp.tool(name="search_modules")
    def search_modules_tool(query: str, category: str = "") -> str:
        """Search modules by keyword. Word-boundary matching across title, tags,
        summary, and overview; results scored and sorted by relevance.
        Optionally filter by category."""
        results = [
            {
                "id": r.module.id,
                "category": r.module.category,
                "title": r.module.title,
                "summary": r.module.summary,
                "tags": r.module.metadata.tags,
                "confidence": r.module.metadata.confidence,
                "source": r.source,
                "caveats": r.module.content.caveats,
                "related_modules": r.module.metadata.related_modules,
                "snippet": _snippet(r.module.content.overview, query),
            }
            for r in search_modules(query, kb_path, category if category else None)
        ]
        return json.dumps(results, indent=2)

    @mcp.tool(name="list_categories")
    def list_categories_tool() -> str:
        """List all categories and their module counts."""
        index = load_index(kb_path)
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
    def expand_module_tool(module_id: str, category: str) -> str:
        """Load a module and its directly related neighbor modules (1-hop graph expansion)."""
        module = load_module(module_id, category, kb_path)
        if module is None:
            return json.dumps({"error": f"Module not found: {module_id} in category {category}"})

        neighbors = []
        for ref in module.metadata.related_modules:
            parts = ref.split("/", 1)
            if len(parts) != 2:
                continue
            n = load_module(parts[1], parts[0], kb_path)
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
    def deep_search_tool(query: str, category: str = "") -> str:
        """Search, expand top results, and load full content — all in one call.

        Returns top-3 search results with full module content, plus neighbors for
        each via graph expansion. Use when you need comprehensive knowledge without
        multiple round-trips.
        """
        search_results = search_modules(query, kb_path, category if category else None, limit=3)
        output = []
        for sr in search_results:
            full = load_module(sr.module.id, sr.module.category, kb_path)
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
            # Expand neighbors
            neighbors = []
            for ref in sr.module.metadata.related_modules:
                parts = ref.split("/", 1)
                if len(parts) == 2:
                    n = load_module(parts[1], parts[0], kb_path)
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

    return mcp
