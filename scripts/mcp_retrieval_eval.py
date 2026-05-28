"""Simulate how an LLM would navigate the KB via the MCP server.

For each scenario, the simulator does what a smart LLM should do:
  1. Read the index (resources/read knowledge://index)
  2. Pick a search query based on the scenario + index contents
  3. Call search_modules
  4. If results: pick the top hit, call load_module, grade against expected_modules
  5. If no results: record as "correctly abstained" or "missed" based on expected_empty

Run:
    poetry run python scripts/mcp_retrieval_eval.py
"""
import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

KB = Path(__file__).resolve().parent.parent / "examples" / "sample_knowledge_base"


@dataclass
class Scenario:
    user_question: str
    expected_modules: list[str]  # full "category/id" identifiers; empty = should abstain
    notes: str = ""
    chosen_query: str = ""
    search_hits: list[str] = field(default_factory=list)
    loaded: str = ""
    grade: str = ""  # "pass" | "partial" | "fail"


SCENARIOS: list[Scenario] = [
    Scenario(
        user_question="How do we validate JWT tokens at the API gateway?",
        expected_modules=["auth/jwt-tokens"],
        notes="Direct hit — terms match title and tags",
    ),
    Scenario(
        user_question="What's our OAuth callback URL handling for server-side web apps?",
        expected_modules=["auth/oauth-flow"],
        notes="Direct hit — OAuth in title",
    ),
    Scenario(
        user_question="How big should I size the database connection pool for Postgres?",
        expected_modules=["database/connection-pool"],
        notes="Direct hit — pool sizing in summary",
    ),
    Scenario(
        user_question="What signing algorithm do our auth tokens use and why not HS256?",
        expected_modules=["auth/jwt-tokens"],
        notes="Indirect — RS256/HS256 only in body, but 'signing' is in title",
    ),
    Scenario(
        user_question="Help me set up a Kubernetes ingress controller",
        expected_modules=[],
        notes="Should abstain — KB has nothing on this",
    ),
]


def _pick_query(question: str, index: dict) -> str:
    """Mimic what a small LLM would do: pull salient nouns from the question
    and pick terms that look like they'd be in titles/tags. Strip stopwords."""
    stop = {
        "how", "do", "we", "the", "a", "an", "what", "is", "are", "i", "should",
        "for", "to", "and", "or", "of", "in", "on", "at", "with", "our", "my",
        "help", "me", "set", "up", "use", "uses", "size", "sizing", "big",
        "controller", "handling", "url", "side", "web", "apps", "app", "not",
        "why", "validate", "callback",
    }
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9-]+", question.lower())
    keep = [w for w in words if w not in stop and len(w) > 2]
    return " ".join(keep[:3])


async def _send(proc, msg):
    proc.stdin.write((json.dumps(msg) + "\n").encode())
    await proc.stdin.drain()


async def _read(proc):
    line = await proc.stdout.readline()
    return json.loads(line.decode()) if line else None


async def _call(proc, mid, method, params=None):
    await _send(proc, {"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})
    while True:
        msg = await _read(proc)
        if msg is None:
            raise RuntimeError(f"closed before {method}")
        if msg.get("id") == mid:
            return msg


async def _notify(proc, method, params=None):
    await _send(proc, {"jsonrpc": "2.0", "method": method, "params": params or {}})


def _tool_result(rpc_response: dict):
    return json.loads(rpc_response["result"]["structuredContent"]["result"])


async def main() -> int:
    proc = await asyncio.create_subprocess_exec(
        "poetry", "run", "km", "--kb-path", str(KB), "serve",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    mid = 0

    def next_id():
        nonlocal mid
        mid += 1
        return mid

    try:
        await _call(proc, next_id(), "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "retrieval-eval", "version": "0.1"},
        })
        await _notify(proc, "notifications/initialized")

        idx_resp = await _call(proc, next_id(), "resources/read", {"uri": "knowledge://index"})
        index = json.loads(idx_resp["result"]["contents"][0]["text"])
        total = index["stats"]["total_modules"]
        print(f"Loaded index: {total} modules across {index['stats']['categories']} categories\n")

        for s in SCENARIOS:
            print(f"--- {s.user_question}")
            s.chosen_query = _pick_query(s.user_question, index)
            print(f"    query: {s.chosen_query!r}")

            search_resp = await _call(proc, next_id(), "tools/call", {
                "name": "search_modules",
                "arguments": {"query": s.chosen_query},
            })
            hits = _tool_result(search_resp)
            s.search_hits = [f"{h['category']}/{h['id']}" for h in hits]
            print(f"    hits:  {s.search_hits if s.search_hits else '[]'}")

            if not s.expected_modules:
                if not s.search_hits:
                    s.grade = "pass"
                    print(f"    grade: PASS (correctly abstained)")
                else:
                    s.grade = "fail"
                    print(f"    grade: FAIL (expected empty, got {s.search_hits})")
                continue

            if not s.search_hits:
                s.grade = "fail"
                print(f"    grade: FAIL (expected {s.expected_modules}, got nothing)")
                continue

            top = hits[0]
            s.loaded = f"{top['category']}/{top['id']}"
            load_resp = await _call(proc, next_id(), "tools/call", {
                "name": "load_module",
                "arguments": {"module_id": top["id"], "category": top["category"]},
            })
            loaded_text = load_resp["result"]["structuredContent"]["result"]
            if "Module not found" in loaded_text:
                s.grade = "fail"
                print(f"    grade: FAIL (load_module returned not-found for top hit)")
                continue

            if s.loaded in s.expected_modules:
                s.grade = "pass"
                print(f"    loaded: {s.loaded} ✓")
                print(f"    grade: PASS")
            else:
                expected_in_hits = any(h in s.expected_modules for h in s.search_hits)
                s.grade = "partial" if expected_in_hits else "fail"
                print(f"    loaded: {s.loaded} (expected {s.expected_modules})")
                print(f"    grade: {s.grade.upper()}")

        print("\n=== Summary ===")
        counts = {"pass": 0, "partial": 0, "fail": 0}
        for s in SCENARIOS:
            counts[s.grade] += 1
            print(f"  [{s.grade.upper():7}] {s.user_question}")
        n = len(SCENARIOS)
        print(f"\n  {counts['pass']}/{n} pass, {counts['partial']}/{n} partial, {counts['fail']}/{n} fail")
        return 0 if counts["fail"] == 0 else 1
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


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
