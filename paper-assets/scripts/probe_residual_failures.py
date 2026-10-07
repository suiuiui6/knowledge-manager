"""Exploratory source-grounded diagnostics; no model calls or product edits."""
from __future__ import annotations

import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT / "knowledge-manager"
CORPUS = ROOT / "paper-assets/corpora/km-project-sources-v1"
OUT = ROOT / "paper-assets/results/residual-probe-20261007"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], check=True,
                          capture_output=True, encoding="utf-8").stdout


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


def bm25(query: str, docs: list[dict]) -> list[dict]:
    bags = [Counter(tokens(d["text"])) for d in docs]
    avg = sum(sum(b.values()) for b in bags) / max(len(bags), 1)
    df = Counter(t for b in bags for t in b)
    rows = []
    for d, b in zip(docs, bags):
        score = 0.0
        for t in set(tokens(query)):
            tf = b.get(t, 0)
            if tf:
                idf = math.log(1 + (len(docs) - df[t] + 0.5) / (df[t] + 0.5))
                score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * sum(b.values()) / avg))
        rows.append({"id": d["id"], "score": score})
    return sorted(rows, key=lambda r: (-r["score"], r["id"]))


def snapshot_inputs() -> list[dict]:
    records = []
    paths = list((REPO / "src/knowledge_manager").glob("*.py")) + [REPO / "pyproject.toml"]
    paths += [CORPUS / "sources/single-node-deploy.md", CORPUS / "manifest.json"]
    paths += sorted((CORPUS / "modules/operations").glob("single-node-deploy-*.json"))
    for p in paths:
        rel = p.relative_to(ROOT)
        dst = OUT / "inputs" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        data = p.read_bytes()
        dst.write_bytes(data)
        records.append({"original": rel.as_posix(), "snapshot": dst.relative_to(ROOT).as_posix(),
                        "sha256": sha(data), "byte_count": len(data)})
    return records


def version_probe() -> dict:
    path = "src/knowledge_manager/storage.py"
    commits = git("log", "--first-parent", "--reverse", "--format=%H", "--", path).splitlines()
    documents: dict[str, dict] = {}
    tasks = []
    skipped = []
    for revision in commits:
        text = git("show", f"{revision}:{path}")
        dst = OUT / "inputs/history" / revision / "storage.py"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(text, encoding="utf-8")
        node = next((n for n in ast.parse(text).body
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "search_modules"), None)
        if node is None:
            skipped.append({"revision": revision, "reason": "search_modules absent"})
            continue
        excerpt = "\n".join(text.splitlines()[node.lineno - 1:node.end_lineno])
        key = sha(excerpt.encode("utf-8"))
        d = documents.setdefault(key, {"id": key, "text": excerpt, "valid_revisions": [],
                                      "first_revision": revision, "locators": []})
        d["valid_revisions"].append(revision)
        d["locators"].append({"revision": revision, "line_start": node.lineno,
                               "line_end": node.end_lineno, "source_sha256": sha(text.encode("utf-8"))})
        tasks.append({"revision": revision, "expected_hash": key})
    docs = list(documents.values())
    query = "search_modules routing policy mandatory companion stale sources limit"
    mixed = bm25(query, docs)[0]["id"]
    latest = tasks[-1]["expected_hash"]
    for t in tasks:
        eligible = [d for d in docs if t["revision"] in d["valid_revisions"]]
        chosen = bm25(query, eligible)[0]["id"]
        t.update({"query": query, "symbol_given": "search_modules", "mixed_bm25_hash": mixed,
                  "latest_only_hash": latest, "version_filter_bm25_hash": chosen,
                  "mixed_correct": mixed == t["expected_hash"],
                  "latest_correct": latest == t["expected_hash"],
                  "version_filter_correct": chosen == t["expected_hash"]})
    write_json(OUT / "history-candidates.json", docs)
    return {"status": "EXECUTED_LOCAL", "changed_file_commits_examined": len(commits),
            "distinct_function_versions": len(docs), "query_conditions": len(tasks),
            "labels": "Exact historical source-function hashes; revision and symbol given, not semantic QA gold",
            "counts": {m: sum(t[m] for t in tasks) for m in
                       ("mixed_correct", "latest_correct", "version_filter_correct")},
            "tasks": tasks, "skipped": skipped,
            "limitation": "Known revision membership makes filtering trivial; correlated versions of one symbol, not independent tasks"}


def runtime_probes() -> tuple[dict, dict]:
    sys.path.insert(0, str(OUT / "inputs/knowledge-manager/src"))
    from knowledge_manager.schemas import Module, SourceDefinition, ConfluenceSourceConfig
    from knowledge_manager.storage import save_module, search_modules
    from knowledge_manager.source_ingestion import _stamp_module
    from knowledge_manager.confluence import ConfluencePage

    fixture_root = OUT / "isolated-kb" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")

    snapshot_corpus = OUT / "inputs/paper-assets/corpora/km-project-sources-v1"
    modules = [Module.model_validate_json(p.read_text(encoding="utf-8-sig"))
               for p in sorted((snapshot_corpus / "modules/operations").glob("single-node-deploy-*.json"))]
    companion = "operations/single-node-deploy-001"
    rows = []
    for qi, query in enumerate(["single-node-deploy install", "systemctl install", "install service deployment"]):
        for limit in [1, 2, 3, 6]:
            kb = fixture_root / f"q{qi}-limit{limit}"
            kb.mkdir(parents=True, exist_ok=True)
            write_json(kb / "config.json", {"routing_policy": {
                "mandatory_companions": {"operations": [companion]}}})
            for module in modules:
                save_module(module, kb)
            retrieved = search_modules(query, kb, limit=limit, enable_vector_fallback=False)
            current = [f"{r.module.category}/{r.module.id}" for r in retrieved]
            # Audit control: explicit declared companion kept before quantity truncation.
            # Ranking comes from actual KM; no oracle dependency inference is claimed.
            wide = search_modules(query, kb, limit=len(modules), enable_vector_fallback=False)
            ranked = [f"{r.module.category}/{r.module.id}" for r in wide]
            primary = next((k for k in ranked if k != companion), None)
            group = [primary, companion] if primary else []
            control = group + [k for k in ranked if k not in group] if limit >= len(group) else []
            control = control[:limit]
            rows.append({"query": query, "limit_modules": limit, "actual_km": current,
                         "actual_has_companion": companion in current,
                         "actual_sources": [{"key": f"{r.module.category}/{r.module.id}", "source": r.source,
                                             "reasons": r.reasons} for r in retrieved],
                         "wide_ranking": ranked, "simple_declared_group_control": control,
                         "control_has_complete_pair": bool(group) and all(k in control for k in group),
                         "control_abstained_due_to_capacity": bool(group) and limit < len(group)})
    companion_result = {"status": "EXECUTED_LOCAL", "label_status": "Controlled config derived from explicit Prerequisites section",
                        "fixture_root": fixture_root.relative_to(ROOT).as_posix(),
                        "search_function_source": str(Path(sys.modules[search_modules.__module__].__file__).relative_to(ROOT)),
                        "corpus_module_count": len(modules), "declared_companion": companion,
                        "capacity_unit": "module count, not reader tokens", "conditions": rows,
                        "network_model_calls": 0,
                        "limitation": "One document; declared rule is analyst configured; no deployment or agent execution"}

    body = (snapshot_corpus / "sources/single-node-deploy.md").read_text(encoding="utf-8-sig")
    source = SourceDefinition(id="local-controlled-page", confluence=ConfluenceSourceConfig(
        base_url="https://example.invalid", email="no-network@example.invalid", api_token_env="UNUSED",
        space_key="LOCAL", category="operations"))
    page = ConfluencePage(page_id="local-runbook", title="Single-Node Deployment", url="",
                         version=sha(body.encode("utf-8")), body_text=body,
                         heading_path=["Single-Node Deployment"], checksum=sha(body.encode("utf-8")))
    stamps = []
    for module in modules:
        stamped = _stamp_module(module, source, page, "local-diagnostic-no-model")
        unit = module.content.details
        start = body.find(unit)
        assert start >= 0, "Source-grounded input excerpt missing from source"
        span = stamped.metadata.source_spans[0]
        end = start + len(unit)
        stamps.append({"key": f"{module.category}/{module.id}", "original_unit_start": start,
                       "original_unit_end": end, "stamped_start": span.char_start,
                       "stamped_end": span.char_end,
                       "stamped_excerpt_is_valid_page_slice": body[span.char_start:span.char_end] == span.excerpt,
                       "stamped_span_covers_entire_unit": span.char_start <= start and span.char_end >= end,
                       "exact_substring_control_covers_unit": body[start:end] == unit})
    stamp_result = {"status": "EXECUTED_LOCAL", "conditions": stamps,
                    "stamp_function_source": str(Path(sys.modules[_stamp_module.__module__].__file__).relative_to(ROOT)),
                    "limitation": "Controlled local page wrapper, no live ingestion; literal full-unit containment, not entailment",
                    "stamped_complete_count": sum(r["stamped_span_covers_entire_unit"] for r in stamps),
                    "exact_substring_complete_count": sum(r["exact_substring_control_covers_unit"] for r in stamps)}
    return companion_result, stamp_result


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    inputs = snapshot_inputs()
    environment = {"python": sys.version, "platform": platform.platform(), "executable": sys.executable,
                   "packages": {p: importlib.metadata.version(p) for p in
                                ["pydantic", "snowballstemmer", "jieba", "mcp", "httpx"]},
                   "repo_head": git("rev-parse", "HEAD").strip(),
                   "repo_commit_count": int(git("rev-list", "--count", "HEAD")),
                   "worktree_status": git("status", "--short", "--untracked-files=no")}
    write_json(OUT / "input-manifest.json", {"files": inputs, "script_sha256": sha(Path(__file__).read_bytes())})
    write_json(OUT / "environment.json", environment)
    history = version_probe()
    companion, spans = runtime_probes()
    results = {"execution_status": "EXECUTED_LOCAL", "executed_at_utc": datetime.now(timezone.utc).isoformat(),
               "study_type": "Exploratory controlled mechanism diagnostics, not publication efficacy evaluation",
               "historical_version_selection": history, "mandatory_companion_truncation": companion,
               "source_span_stamping": spans, "independent_scope": "One repository / one runbook",
               "formal_inference": "None; no p values or general performance claims"}
    write_json(OUT / "results.json", results)
    print(json.dumps({"output": str(OUT), "historical_counts": history["counts"],
                      "historical_conditions": history["query_conditions"],
                      "missing_companion_conditions": sum(not r["actual_has_companion"] for r in companion["conditions"]),
                      "feasible_missing_companion_conditions": sum(not r["actual_has_companion"] and r["limit_modules"] >= 2
                                                                     for r in companion["conditions"]),
                      "stamped_complete": spans["stamped_complete_count"],
                      "exact_substring_complete": spans["exact_substring_complete_count"]}, indent=2))


if __name__ == "__main__":
    main()
