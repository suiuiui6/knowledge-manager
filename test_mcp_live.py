#!/usr/bin/env python3
"""Test the MCP server with the real knowledge base."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from knowledge_manager.mcp_server import create_server

async def main():
    kb_path = Path("D:/tyh/knowledge_base")

    print("Creating MCP server...")
    server = create_server(kb_path)

    print("\n=== Testing knowledge://index resource ===")
    try:
        # Get the index resource
        index_data = server._resources["knowledge://index"]()
        index = json.loads(index_data)
        print(f"✓ Index loaded: {index['stats']['total_modules']} modules, {index['stats']['categories']} categories")
        print(f"  Categories: {', '.join(index['categories'].keys())}")

        # Show first module
        if index['categories']:
            first_cat = list(index['categories'].values())[0]
            if first_cat['modules']:
                first_mod = first_cat['modules'][0]
                print(f"  Sample module: {first_mod['id']} - {first_mod['title']}")
    except Exception as e:
        print(f"✗ Index resource failed: {e}")
        return

    print("\n=== Testing search_modules tool ===")
    try:
        # Test search
        search_tool = server._tools["search_modules"]
        result = search_tool(query="oauth token")
        results = json.loads(result)
        print(f"✓ Search 'oauth token' returned {len(results)} results")
        if results:
            print(f"  Top result: {results[0]['id']} - {results[0]['title']}")
    except Exception as e:
        print(f"✗ Search tool failed: {e}")
        return

    print("\n=== Testing load_module tool ===")
    try:
        load_tool = server._tools["load_module"]
        result = load_tool(module_id="authorization-code-flow", category="auth")
        module = json.loads(result)
        print(f"✓ Loaded module: {module['title']}")
        print(f"  Summary: {module['summary']}")
        print(f"  Word count: {len(module['content']['overview'].split()) + len(module['content']['details'].split())}")
    except Exception as e:
        print(f"✗ Load module tool failed: {e}")
        return

    print("\n=== Testing list_categories tool ===")
    try:
        list_tool = server._tools["list_categories"]
        result = list_tool()
        categories = json.loads(result)
        print(f"✓ Listed {len(categories)} categories")
        for cat in categories:
            print(f"  - {cat['name']}: {cat['module_count']} modules")
    except Exception as e:
        print(f"✗ List categories tool failed: {e}")
        return

    print("\n✅ All MCP server tests passed!")

if __name__ == "__main__":
    asyncio.run(main())
