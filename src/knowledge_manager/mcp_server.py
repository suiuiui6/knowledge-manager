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
                "id": m.id,
                "category": m.category,
                "title": m.title,
                "summary": m.summary,
                "tags": m.metadata.tags,
            }
            for m in search_modules(query, kb_path, category if category else None)
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

    return mcp
