import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from knowledge_manager.storage import load_index, load_module, list_modules


def create_server(kb_path: Path) -> FastMCP:
    mcp = FastMCP("knowledge-manager")

    @mcp.resource("knowledge://index")
    def get_index() -> str:
        index = load_index(kb_path)
        if index is None:
            return json.dumps({"categories": {}, "description": "", "stats": {}})
        return index.model_dump_json()

    @mcp.tool(name="load_module")
    def load_module_tool(module_id: str, category: str) -> str:
        """Load a full knowledge module by ID and category."""
        module = load_module(module_id, category, kb_path)
        if module is None:
            return f"Module not found: {module_id} in category {category}"
        return module.model_dump_json(indent=2)

    @mcp.tool(name="search_modules")
    def search_modules_tool(query: str) -> str:
        """Search modules by keyword match against title, summary, and tags."""
        modules = list_modules(kb_path)
        query_lower = query.lower()
        results = []
        for m in modules:
            searchable = " ".join([
                m.title, m.summary,
                " ".join(m.metadata.tags),
                m.content.overview,
            ]).lower()
            if any(word in searchable for word in query_lower.split()):
                results.append({
                    "id": m.id,
                    "category": m.category,
                    "title": m.title,
                    "summary": m.summary,
                    "tags": m.metadata.tags,
                })
        return json.dumps(results, indent=2)

    @mcp.tool(name="list_categories")
    def list_categories_tool() -> str:
        """List all categories and their module counts."""
        index = load_index(kb_path)
        if index is None:
            return json.dumps([])
        result = [
            {"category": name, "module_count": len(cat.modules), "description": cat.description}
            for name, cat in index.categories.items()
        ]
        return json.dumps(result, indent=2)

    return mcp
