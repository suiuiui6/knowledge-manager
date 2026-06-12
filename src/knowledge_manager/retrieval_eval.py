from __future__ import annotations

import math

from pydantic import BaseModel


class RankedCaseSummary(BaseModel):
    first_hit_rank: int | None = None
    mrr: float = 0.0
    ndcg_at_k: float = 0.0
    recall_at_k: float = 0.0


def score_ranked_case(required_modules: list[str], found_modules: list[str]) -> RankedCaseSummary:
    required_set = set(required_modules)
    hit_positions = [idx + 1 for idx, module_key in enumerate(found_modules) if module_key in required_set]
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
