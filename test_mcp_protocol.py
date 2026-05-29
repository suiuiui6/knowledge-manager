#!/usr/bin/env python3
"""Test MCP server via JSON-RPC stdio protocol."""
import json
import subprocess
import sys

def send_request(proc, method, params=None):
    """Send a JSON-RPC request and get response."""
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
    }
    if params:
        request["params"] = params

    request_str = json.dumps(request) + "\n"
    proc.stdin.write(request_str)
    proc.stdin.flush()

    response_line = proc.stdout.readline()
    return json.loads(response_line)

def main():
    print("Starting MCP server...")
    proc = subprocess.Popen(
        ["poetry", "run", "km", "--kb-path", "D:/tyh/knowledge_base", "serve"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd="D:/tyh/knowledge-manager"
    )

    try:
        print("\n=== Initializing ===")
        resp = send_request(proc, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"}
        })
        print(f"✓ Server initialized: {resp['result']['serverInfo']['name']}")

        print("\n=== Listing resources ===")
        resp = send_request(proc, "resources/list")
        resources = resp['result']['resources']
        print(f"✓ Found {len(resources)} resources")
        for r in resources:
            print(f"  - {r['uri']}: {r['name']}")

        print("\n=== Reading knowledge://index ===")
        resp = send_request(proc, "resources/read", {"uri": "knowledge://index"})
        index_text = resp['result']['contents'][0]['text']
        index = json.loads(index_text)
        print(f"✓ Index: {index['stats']['total_modules']} modules, {index['stats']['categories']} categories")

        print("\n=== Listing tools ===")
        resp = send_request(proc, "tools/list")
        tools = resp['result']['tools']
        print(f"✓ Found {len(tools)} tools")
        for t in tools:
            print(f"  - {t['name']}: {t['description'][:60]}...")

        print("\n=== Calling search_modules ===")
        resp = send_request(proc, "tools/call", {
            "name": "search_modules",
            "arguments": {"query": "oauth token"}
        })
        results = json.loads(resp['result']['content'][0]['text'])
        print(f"✓ Search returned {len(results)} results")
        if results:
            print(f"  Top: {results[0]['id']} - {results[0]['title']}")

        print("\n=== Calling load_module ===")
        resp = send_request(proc, "tools/call", {
            "name": "load_module",
            "arguments": {"module_id": "authorization-code-flow", "category": "auth"}
        })
        module = json.loads(resp['result']['content'][0]['text'])
        print(f"✓ Loaded: {module['title']}")
        print(f"  Tags: {', '.join(module['metadata']['tags'])}")

        print("\n✅ All MCP protocol tests passed!")

    finally:
        proc.terminate()
        proc.wait()

if __name__ == "__main__":
    main()
