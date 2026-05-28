"""Drive the stdio MCP server with raw JSON-RPC and print results.

Run from the project root:
    poetry run python scripts/mcp_smoke.py
"""
import asyncio
import json
import sys
from pathlib import Path

KB = Path(__file__).resolve().parent.parent / "examples" / "sample_knowledge_base"


async def _send(proc, msg: dict) -> None:
    line = json.dumps(msg) + "\n"
    proc.stdin.write(line.encode("utf-8"))
    await proc.stdin.drain()


async def _read(proc) -> dict | None:
    line = await proc.stdout.readline()
    if not line:
        return None
    return json.loads(line.decode("utf-8"))


async def _call(proc, mid: int, method: str, params: dict | None = None) -> dict:
    await _send(proc, {"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})
    while True:
        msg = await _read(proc)
        if msg is None:
            raise RuntimeError(f"server closed before responding to {method}")
        if msg.get("id") == mid:
            return msg


async def _notify(proc, method: str, params: dict | None = None) -> None:
    await _send(proc, {"jsonrpc": "2.0", "method": method, "params": params or {}})


def _pretty(label: str, payload) -> None:
    print(f"\n=== {label} ===")
    print(json.dumps(payload, indent=2, ensure_ascii=False)[:2000])


async def main() -> int:
    print(f"Launching: km --kb-path {KB} serve")
    proc = await asyncio.create_subprocess_exec(
        "poetry", "run", "km", "--kb-path", str(KB), "serve",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        init = await _call(proc, 1, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "smoke-test", "version": "0.1"},
        })
        _pretty("initialize result", init.get("result"))

        await _notify(proc, "notifications/initialized")

        tools = await _call(proc, 2, "tools/list")
        _pretty("tools/list", tools.get("result"))

        resources = await _call(proc, 3, "resources/list")
        _pretty("resources/list", resources.get("result"))

        index_read = await _call(proc, 4, "resources/read", {"uri": "knowledge://index"})
        _pretty("resources/read knowledge://index", index_read.get("result"))

        list_cats = await _call(proc, 5, "tools/call", {
            "name": "list_categories",
            "arguments": {},
        })
        _pretty("call list_categories", list_cats.get("result"))

        search_jwt = await _call(proc, 6, "tools/call", {
            "name": "search_modules",
            "arguments": {"query": "jwt signing"},
        })
        _pretty('call search_modules "jwt signing"', search_jwt.get("result"))

        search_pool = await _call(proc, 7, "tools/call", {
            "name": "search_modules",
            "arguments": {"query": "postgres connection pool sizing"},
        })
        _pretty('call search_modules "postgres connection pool sizing"', search_pool.get("result"))

        search_miss = await _call(proc, 8, "tools/call", {
            "name": "search_modules",
            "arguments": {"query": "kubernetes networking"},
        })
        _pretty('call search_modules "kubernetes networking" (should be empty)', search_miss.get("result"))

        load = await _call(proc, 9, "tools/call", {
            "name": "load_module",
            "arguments": {"module_id": "jwt-tokens", "category": "auth"},
        })
        _pretty("call load_module jwt-tokens/auth", load.get("result"))

        load_miss = await _call(proc, 10, "tools/call", {
            "name": "load_module",
            "arguments": {"module_id": "nonexistent", "category": "auth"},
        })
        _pretty("call load_module nonexistent/auth (should report not found)", load_miss.get("result"))

        return 0
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        err = await proc.stderr.read()
        if err:
            print("\n=== stderr ===")
            print(err.decode("utf-8", errors="replace"))


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
