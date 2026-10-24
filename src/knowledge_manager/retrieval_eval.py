from __future__ import annotations

import math
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class RankedCaseSummary(BaseModel):
    first_hit_rank: int | None = None
    mrr: float = 0.0
    ndcg_at_k: float = 0.0
    recall_at_k: float = 0.0


def score_ranked_case(required_modules: list[str], found_modules: list[str]) -> RankedCaseSummary:
    required_set = set(required_modules)
    hit_positions = [
        idx + 1 for idx, module_key in enumerate(found_modules) if module_key in required_set
    ]
    first_hit_rank = hit_positions[0] if hit_positions else None
    mrr = 1.0 / first_hit_rank if first_hit_rank else 0.0

    hits = [1 if module_key in required_set else 0 for module_key in found_modules]
    dcg = sum(rel / math.log2(idx + 2) for idx, rel in enumerate(hits))
    ideal_hits = [1] * min(len(required_modules), len(found_modules))
    idcg = sum(rel / math.log2(idx + 2) for idx, rel in enumerate(ideal_hits))
    recall = len(required_set & set(found_modules)) / len(required_set) if required_set else 0.0

    return RankedCaseSummary(
        first_hit_rank=first_hit_rank,
        mrr=mrr,
        ndcg_at_k=(dcg / idcg) if idcg else 0.0,
        recall_at_k=recall,
    )


def evaluate_golden_set(
    cases: list[dict[str, Any]],
    search,
    *,
    top_k: int = 10,
) -> dict[str, Any]:
    """Evaluate deterministic retrieval cases and report quality plus isolation."""
    if not cases:
        raise ValueError("golden set must contain at least one case")
    summaries: list[dict[str, Any]] = []
    leakage = 0
    abstention_hits = 0
    positive_cases = 0
    for case in cases:
        tenant = case.get("tenant_id")
        workspace = case.get("workspace_id")
        results = search(
            str(case["query"]),
            tenant_id=tenant,
            workspace_id=workspace,
            top_k=int(case.get("top_k", top_k)),
        )
        found = [f"{item.module.category}/{item.module.id}" for item in results]
        allowed = set(case.get("allowed_modules", []))
        case_leak = bool(allowed and any(key not in allowed for key in found))
        for item in results:
            metadata = getattr(item.module, "metadata", None)
            if metadata is None:
                continue
            if tenant is not None and metadata.tenant_id not in {"", tenant}:
                case_leak = True
            if workspace is not None and metadata.workspace_id not in {"", workspace}:
                case_leak = True
        if case_leak:
            leakage += 1
        required = case.get("required_modules", [])
        if required:
            positive_cases += 1
        elif not found:
            abstention_hits += 1
        score = score_ranked_case(case.get("required_modules", []), found)
        summaries.append({"query": case["query"], "found_modules": found, **score.model_dump()})
    count = len(summaries)
    positive_summaries = [
        item for item, case in zip(summaries, cases) if case.get("required_modules", [])
    ]
    quality_count = len(positive_summaries)
    return {
        "case_count": count,
        "positive_case_count": positive_cases,
        "quality_case_count": quality_count,
        "mean_recall_at_k": (
            sum(item["recall_at_k"] for item in positive_summaries) / quality_count
            if quality_count
            else 0.0
        ),
        "mean_mrr": (
            sum(item["mrr"] for item in positive_summaries) / quality_count
            if quality_count
            else 0.0
        ),
        "mean_ndcg_at_k": (
            sum(item["ndcg_at_k"] for item in positive_summaries) / quality_count
            if quality_count
            else 0.0
        ),
        "tenant_leakage_cases": leakage,
        "positive_case_count": positive_cases,
        "abstention_accuracy": (
            abstention_hits / (count - positive_cases) if count != positive_cases else 1.0
        ),
        "cases": summaries,
    }


def load_golden_set(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases", payload) if isinstance(payload, dict) else payload
    if not isinstance(cases, list):
        raise ValueError("golden set must contain a cases list")
    return cases
