#!/usr/bin/env python
"""Run a guarded candidate baseline evaluation for Knowledge Manager paper work.

This script is intentionally conservative. It can evaluate candidate queries
against approved module files and chunk baselines, but it marks outputs as
candidate-only unless every query has been author-labeled or double-checked.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_ROOT = Path(r"D:\tyh")
DEFAULT_QUERY_PATH = DEFAULT_ROOT / "paper-assets" / "eval" / "judged-queries.candidate.jsonl"
DEFAULT_RESULTS_JSON = DEFAULT_ROOT / "paper-assets" / "results" / "candidate-baseline-eval-result.json"
DEFAULT_RESULTS_MD = DEFAULT_ROOT / "paper-assets" / "results" / "candidate-baseline-eval-result.md"
DEFAULT_KB_ROOTS = [
    DEFAULT_ROOT / "knowledge-manager" / "kb",
    DEFAULT_ROOT / "knowledge_base",
]

WORD_RE = re.compile(r"[a-z0-9_]+|[\u4e00-\u9fff]", re.IGNORECASE)
SKIP_PARTS = {".staging", ".cache", ".telemetry", ".tmp", "test_docs", "__pycache__"}
SKIP_NAMES = {"index.json", "config.json", "config.local.json"}


@dataclass(frozen=True)
class ModuleRecord:
    module_id: str
    category: str
    title: str
    text: str


@dataclass(frozen=True)
class QueryRecord:
    query_id: str
    corpus_id: str
    query: str
    required_modules: list[str]
    status: str


@dataclass(frozen=True)
class RetrievalDocument:
    doc_id: str
    source_module_id: str
    text: str


def _should_skip_file(path: Path) -> bool:
    if path.name in SKIP_NAMES:
        return True
    if path.name.endswith(".meta.json"):
        return True
    return any(part in SKIP_PARTS for part in path.parts)


def _content_text(raw: dict) -> str:
    content = raw.get("content", {})
    if not isinstance(content, dict):
        content = {}
    fields = [
        raw.get("title", ""),
        raw.get("summary", ""),
        content.get("overview", raw.get("overview", "")),
        content.get("details", raw.get("details", "")),
        content.get("examples", raw.get("examples", "")),
        content.get("references", raw.get("references", "")),
        content.get("caveats", raw.get("caveats", "")),
    ]
    return "\n".join(str(field) for field in fields if field)


def load_modules(kb_roots: Iterable[Path]) -> dict[str, ModuleRecord]:
    modules: dict[str, ModuleRecord] = {}
    for root in kb_roots:
        if not root.exists():
            continue
        for path in root.rglob("*.json"):
            if _should_skip_file(path):
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            category = raw.get("category")
            short_id = raw.get("id") or raw.get("module_id")
            if not category or not short_id:
                continue
            module_id = f"{category}/{short_id}"
            text = _content_text(raw)
            if not text.strip():
                continue
            modules[module_id] = ModuleRecord(
                module_id=module_id,
                category=str(category),
                title=str(raw.get("title", short_id)),
                text=text,
            )
    return modules


def load_queries(path: Path) -> list[QueryRecord]:
    queries: list[QueryRecord] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        raw = json.loads(line)
        queries.append(
            QueryRecord(
                query_id=str(raw["query_id"]),
                corpus_id=str(raw["corpus_id"]),
                query=str(raw["query"]),
                required_modules=[str(item) for item in raw.get("required_modules", [])],
                status=str(raw["status"]),
            )
        )
    return queries


def validate_required_modules(queries: list[QueryRecord], modules: dict[str, ModuleRecord]) -> list[str]:
    known = set(modules)
    missing: set[str] = set()
    for query in queries:
        for module_id in query.required_modules:
            if module_id not in known:
                missing.add(module_id)
    return sorted(missing)


def tokenize(text: str) -> list[str]:
    raw_tokens = [match.group(0).lower() for match in WORD_RE.finditer(text)]
    tokens: list[str] = []
    cjk_buffer: list[str] = []
    for token in raw_tokens:
        if len(token) == 1 and "\u4e00" <= token <= "\u9fff":
            cjk_buffer.append(token)
            tokens.append(token)
            continue
        if cjk_buffer:
            tokens.extend("".join(cjk_buffer[i : i + 2]) for i in range(len(cjk_buffer) - 1))
            cjk_buffer = []
        tokens.append(token)
    if cjk_buffer:
        tokens.extend("".join(cjk_buffer[i : i + 2]) for i in range(len(cjk_buffer) - 1))
    return tokens


def build_module_documents(modules: dict[str, ModuleRecord]) -> list[RetrievalDocument]:
    return [
        RetrievalDocument(doc_id=module_id, source_module_id=module_id, text=module.text)
        for module_id, module in sorted(modules.items())
    ]


def build_chunk_documents(
    modules: dict[str, ModuleRecord],
    chunk_size: int = 900,
    chunk_overlap: int = 150,
) -> list[RetrievalDocument]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be >= 0 and smaller than chunk_size")
    step = chunk_size - chunk_overlap
    documents: list[RetrievalDocument] = []
    for module_id, module in sorted(modules.items()):
        text = module.text
        if len(text) <= chunk_size:
            documents.append(RetrievalDocument(f"{module_id}#chunk-000", module_id, text))
            continue
        chunk_index = 0
        for start in range(0, len(text), step):
            chunk = text[start : start + chunk_size]
            if not chunk.strip():
                continue
            documents.append(
                RetrievalDocument(f"{module_id}#chunk-{chunk_index:03d}", module_id, chunk)
            )
            chunk_index += 1
            if start + chunk_size >= len(text):
                break
    return documents


class BM25Index:
    def __init__(self, documents: list[RetrievalDocument], k1: float = 1.5, b: float = 0.75):
        self.documents = documents
        self.k1 = k1
        self.b = b
        self.doc_tokens = [tokenize(document.text) for document in documents]
        self.doc_lengths = [len(tokens) for tokens in self.doc_tokens]
        self.avgdl = statistics.mean(self.doc_lengths) if self.doc_lengths else 0.0
        self.term_freqs = [Counter(tokens) for tokens in self.doc_tokens]
        document_frequency: Counter[str] = Counter()
        for tokens in self.doc_tokens:
            document_frequency.update(set(tokens))
        self.idf = {
            term: math.log(1 + (len(documents) - freq + 0.5) / (freq + 0.5))
            for term, freq in document_frequency.items()
        }

    def rank(self, query: str, top_k: int) -> list[tuple[RetrievalDocument, float]]:
        query_terms = tokenize(query)
        scores: list[tuple[RetrievalDocument, float]] = []
        for idx, document in enumerate(self.documents):
            score = 0.0
            length = self.doc_lengths[idx] or 1
            freqs = self.term_freqs[idx]
            for term in query_terms:
                tf = freqs.get(term, 0)
                if not tf:
                    continue
                denom = tf + self.k1 * (1 - self.b + self.b * length / (self.avgdl or 1))
                score += self.idf.get(term, 0.0) * (tf * (self.k1 + 1)) / denom
            if score > 0:
                scores.append((document, score))
        return sorted(scores, key=lambda item: (-item[1], item[0].doc_id))[:top_k]


class KeywordOverlapIndex:
    def __init__(self, documents: list[RetrievalDocument]):
        self.documents = documents
        self.doc_terms = [set(tokenize(document.text)) for document in documents]

    def rank(self, query: str, top_k: int) -> list[tuple[RetrievalDocument, float]]:
        query_terms = set(tokenize(query))
        scores: list[tuple[RetrievalDocument, float]] = []
        for document, doc_terms in zip(self.documents, self.doc_terms):
            if not query_terms or not doc_terms:
                continue
            overlap = len(query_terms & doc_terms)
            if not overlap:
                continue
            score = overlap / math.sqrt(len(query_terms) * len(doc_terms))
            scores.append((document, score))
        return sorted(scores, key=lambda item: (-item[1], item[0].doc_id))[:top_k]


def _ndcg_at_k(ranked_module_ids: list[str], required_modules: set[str], k: int) -> float | None:
    if not required_modules:
        return None
    dcg = 0.0
    for index, module_id in enumerate(ranked_module_ids[:k], start=1):
        if module_id in required_modules:
            dcg += 1.0 / math.log2(index + 1)
    ideal_hits = min(len(required_modules), k)
    idcg = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_hits + 1))
    return dcg / idcg if idcg else 0.0


def _first_hit_rank(ranked_module_ids: list[str], required_modules: set[str]) -> int | None:
    for index, module_id in enumerate(ranked_module_ids, start=1):
        if module_id in required_modules:
            return index
    return None


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = math.ceil(0.95 * len(ordered)) - 1
    return ordered[max(0, min(index, len(ordered) - 1))]


def evaluate_system(
    system_name: str,
    queries: list[QueryRecord],
    documents: list[RetrievalDocument],
    top_k: int,
    scorer: str = "bm25",
) -> dict:
    index = BM25Index(documents) if scorer == "bm25" else KeywordOverlapIndex(documents)
    per_query: list[dict] = []
    latencies: list[float] = []
    evaluable = 0
    reciprocal_ranks: list[float] = []
    ndcgs: list[float] = []
    recalls: list[float] = []
    precisions: list[float] = []
    first_hits: list[int] = []
    loaded_units: list[int] = []
    miss_count = 0

    for query in queries:
        started = time.perf_counter()
        ranked = index.rank(query.query, top_k)
        elapsed_ms = (time.perf_counter() - started) * 1000
        latencies.append(elapsed_ms)
        loaded_units.append(len(ranked))
        ranked_module_ids = [document.source_module_id for document, _score in ranked]
        unique_ranked_module_ids = list(dict.fromkeys(ranked_module_ids))
        required = set(query.required_modules)
        rank = _first_hit_rank(ranked_module_ids, required)
        recall = None
        precision = None
        ndcg = _ndcg_at_k(ranked_module_ids, required, top_k)
        if required:
            evaluable += 1
            hits = sum(1 for module_id in set(ranked_module_ids[:top_k]) if module_id in required)
            recall = hits / len(required)
            precision = sum(1 for module_id in ranked_module_ids[:top_k] if module_id in required) / top_k
            recalls.append(recall)
            precisions.append(precision)
            ndcgs.append(ndcg or 0.0)
            if rank is None:
                reciprocal_ranks.append(0.0)
                miss_count += 1
            else:
                reciprocal_ranks.append(1.0 / rank)
                first_hits.append(rank)
        per_query.append(
            {
                "query_id": query.query_id,
                "status": query.status,
                "required_modules": sorted(required),
                "ranked_modules": unique_ranked_module_ids[:top_k],
                "first_hit_rank": rank,
                "recall_at_k": recall,
                "precision_at_k": precision,
                "nDCG_at_k": ndcg,
                "latency_ms": round(elapsed_ms, 3),
            }
        )

    return {
        "system": system_name,
        "query_count": len(queries),
        "evaluable_query_count": evaluable,
        "top_k": top_k,
        "MRR": round(statistics.mean(reciprocal_ranks), 4) if reciprocal_ranks else None,
        "nDCG_at_5": round(statistics.mean(ndcgs), 4) if ndcgs else None,
        "recall_at_5": round(statistics.mean(recalls), 4) if recalls else None,
        "precision_at_5": round(statistics.mean(precisions), 4) if precisions else None,
        "mean_latency_ms": round(statistics.mean(latencies), 3) if latencies else 0.0,
        "p95_latency_ms": round(_p95(latencies), 3),
        "avg_loaded_units": round(statistics.mean(loaded_units), 3) if loaded_units else 0.0,
        "first_hit_rank_mean": round(statistics.mean(first_hits), 4) if first_hits else None,
        "miss_count": miss_count,
        "per_query": per_query,
    }


def _status_counts(queries: list[QueryRecord]) -> dict[str, int]:
    counts: defaultdict[str, int] = defaultdict(int)
    for query in queries:
        counts[query.status] += 1
    return dict(sorted(counts.items()))


def build_report_payload(
    query_path: Path,
    query_status_counts: dict[str, int],
    system_results: list[dict],
) -> dict:
    eligible = set(query_status_counts).issubset({"author_labeled", "double_checked"})
    return {
        "status": "main_comparison_ready" if eligible else "candidate_not_main_result",
        "eligible_for_main_comparison": eligible,
        "eligibility_reason": (
            "All evaluated queries are author_labeled or double_checked."
            if eligible
            else "Results are exploratory until every query is author_labeled or double_checked."
        ),
        "query_path": str(query_path),
        "query_status_counts": query_status_counts,
        "system_results": system_results,
    }


def write_markdown_report(payload: dict, path: Path) -> None:
    lines = [
        "# Candidate Baseline Evaluation Result",
        "",
        f"Status: `{payload['status']}`",
        "",
        payload["eligibility_reason"],
        "",
        "These numbers must not be copied into the manuscript main comparison table unless the query labels are author-reviewed.",
        "",
        "## Query Label Status",
        "",
        "| status | count |",
        "|---|---:|",
    ]
    for status, count in payload["query_status_counts"].items():
        lines.append(f"| `{status}` | {count} |")
    lines.extend(
        [
            "",
            "## System Summary",
            "",
            "| system | queries | evaluable | MRR | nDCG@5 | recall@5 | precision@5 | mean latency ms | p95 latency ms | misses |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for result in payload["system_results"]:
        lines.append(
            "| {system} | {query_count} | {evaluable_query_count} | {MRR} | {nDCG_at_5} | {recall_at_5} | {precision_at_5} | {mean_latency_ms} | {p95_latency_ms} | {miss_count} |".format(
                **result
            )
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def run(
    query_path: Path,
    kb_roots: list[Path],
    out_json: Path,
    out_md: Path,
    top_k: int,
    chunk_size: int,
    chunk_overlap: int,
) -> dict:
    modules = load_modules(kb_roots)
    queries = load_queries(query_path)
    missing = validate_required_modules(queries, modules)
    if missing:
        raise SystemExit("Missing required modules: " + ", ".join(missing))

    module_documents = build_module_documents(modules)
    chunk_documents = build_chunk_documents(modules, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    system_results = [
        evaluate_system("structured_module_keyword", queries, module_documents, top_k, scorer="bm25"),
        evaluate_system("bm25_keyword_chunk_baseline", queries, chunk_documents, top_k, scorer="bm25"),
        evaluate_system("chunk_only_keyword_baseline", queries, chunk_documents, top_k, scorer="overlap"),
    ]
    payload = build_report_payload(query_path, _status_counts(queries), system_results)
    payload["module_count"] = len(modules)
    payload["chunk_count"] = len(chunk_documents)
    payload["chunk_size"] = chunk_size
    payload["chunk_overlap"] = chunk_overlap
    payload["top_k"] = top_k

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown_report(payload, out_md)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERY_PATH)
    parser.add_argument("--kb-root", type=Path, action="append", dest="kb_roots")
    parser.add_argument("--out-json", type=Path, default=DEFAULT_RESULTS_JSON)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_RESULTS_MD)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--chunk-size", type=int, default=900)
    parser.add_argument("--chunk-overlap", type=int, default=150)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = run(
        query_path=args.queries,
        kb_roots=args.kb_roots or DEFAULT_KB_ROOTS,
        out_json=args.out_json,
        out_md=args.out_md,
        top_k=args.top_k,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )
    print(f"status: {payload['status']}")
    print(f"eligible_for_main_comparison: {payload['eligible_for_main_comparison']}")
    print(f"wrote: {args.out_json}")
    print(f"wrote: {args.out_md}")


if __name__ == "__main__":
    main()
