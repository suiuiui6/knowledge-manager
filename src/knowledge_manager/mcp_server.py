import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from knowledge_manager.cache import ModuleCache
from knowledge_manager.storage import load_index, load_module, search_modules


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
                    "confidence": n.metadata.confidence,
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

    return mcp
