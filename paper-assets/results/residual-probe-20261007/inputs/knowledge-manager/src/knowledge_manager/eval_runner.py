from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import BaseModel, Field

from knowledge_manager.retrieval_eval import score_ranked_case
from knowledge_manager.storage import search_modules


class EvalCase(BaseModel):
    case_id: str = Field(alias="id")
    query: str
    required_modules: List[str] = Field(default_factory=list)
    category: str = ""
    agent_id: str = ""
    task_type: str = ""
    risk_level: str = ""
    top_k: int = 5


class EvalSuite(BaseModel):
    name: str = "eval-suite"
    cases: List[EvalCase] = Field(default_factory=list)


class EvalCaseResult(BaseModel):
    case_id: str
    query: str
    required_modules: List[str]
    found_modules: List[str]
    missing_modules: List[str]
    policy_suppressed_modules: List[str] = Field(default_factory=list)
    baseline_found_modules: List[str] = Field(default_factory=list)
    context_tokens: int = 0
    first_hit_rank: int | None = None
    mrr: float = 0.0
    ndcg_at_k: float = 0.0
    recall_at_k: float = 0.0
    failure_type: str = "none"
    passed: bool


class EvalDimensionSummary(BaseModel):
    total_cases: int = 0
    passed_cases: int = 0
    suppressed_failures: int = 0


class EvalRunResult(BaseModel):
    name: str
    total_cases: int
    passed_cases: int
    top_k: int
    hit_rate: float
    suppression_failure_rate: float
    baseline_win_rate: float = 0.0
    false_positive_rate: float = 0.0
    false_negative_rate: float = 0.0
    avg_context_tokens: int = 0
    avg_first_hit_rank: float = 0.0
    avg_mrr: float = 0.0
    avg_ndcg_at_k: float = 0.0
    avg_recall_at_k: float = 0.0
    policy_failure_rate: float = 0.0
    retrieval_failure_rate: float = 0.0
    risk_level_summary: dict[str, EvalDimensionSummary] = Field(default_factory=dict)
    task_type_summary: dict[str, EvalDimensionSummary] = Field(default_factory=dict)
    results: List[EvalCaseResult] = Field(default_factory=list)


def load_eval_suite(path: Path) -> EvalSuite:
    return EvalSuite.model_validate_json(path.read_text(encoding="utf-8"))


def classify_eval_failure(missing: list[str], policy_suppressed_modules: list[str]) -> str:
    if not missing:
        return "none"
    if policy_suppressed_modules:
        return "policy"
    return "retrieval"


def run_eval_suite(
    suite: EvalSuite,
    kb_path: Path,
    top_k: int = 5,
    baseline_results: dict[str, dict] | None = None,
) -> EvalRunResult:
    results: List[EvalCaseResult] = []
    passed = 0
    suppressed_failures = 0
    baseline_wins = 0
    false_positives = 0
    false_negatives = 0
    policy_failures = 0
    retrieval_failures = 0
    total_context_tokens = 0
    total_first_hit_rank = 0
    cases_with_first_hit = 0
    total_mrr = 0.0
    total_ndcg_at_k = 0.0
    total_recall_at_k = 0.0
    risk_level_summary: dict[str, EvalDimensionSummary] = {}
    task_type_summary: dict[str, EvalDimensionSummary] = {}
    for case in suite.cases:
        effective_top_k = case.top_k or top_k
        baseline_found = [
            f"{item.module.category}/{item.module.id}"
            for item in search_modules(
                case.query,
                kb_path,
                category=case.category or None,
                limit=effective_top_k,
            )
        ]
        full_results = search_modules(
            case.query,
            kb_path,
            category=case.category or None,
            limit=effective_top_k,
            agent_id=case.agent_id or None,
            task_type=case.task_type or None,
            risk_level=case.risk_level or None,
        )
        found = [f"{item.module.category}/{item.module.id}" for item in full_results]
        ranking = score_ranked_case(case.required_modules, found)
        missing = [required for required in case.required_modules if required not in found]
        suppressed = [module_key for module_key in baseline_found if module_key not in found]
        case_passed = len(missing) == 0
        context_tokens = sum(max(1, item.module.word_count()) for item in full_results)
        failure_type = classify_eval_failure(missing, suppressed)
        suppression_driven_failure = (not case_passed) and bool(suppressed)
        if case_passed:
            passed += 1
        if suppression_driven_failure:
            suppressed_failures += 1
        if failure_type == "policy":
            policy_failures += 1
        elif failure_type == "retrieval":
            retrieval_failures += 1
        if found and not any(required in found for required in case.required_modules):
            false_positives += 1
        if missing:
            false_negatives += 1
        total_context_tokens += context_tokens
        if ranking.first_hit_rank is not None:
            total_first_hit_rank += ranking.first_hit_rank
            cases_with_first_hit += 1
        total_mrr += ranking.mrr
        total_ndcg_at_k += ranking.ndcg_at_k
        total_recall_at_k += ranking.recall_at_k
        baseline_case = (baseline_results or {}).get(case.case_id)
        if baseline_case is not None:
            baseline_required_hit = baseline_case.get("required_hit", False)
            if case_passed and not baseline_required_hit:
                baseline_wins += 1

        risk_key = case.risk_level or "unspecified"
        if risk_key not in risk_level_summary:
            risk_level_summary[risk_key] = EvalDimensionSummary()
        risk_level_summary[risk_key].total_cases += 1
        if case_passed:
            risk_level_summary[risk_key].passed_cases += 1
        if suppression_driven_failure:
            risk_level_summary[risk_key].suppressed_failures += 1

        task_key = case.task_type or "unspecified"
        if task_key not in task_type_summary:
            task_type_summary[task_key] = EvalDimensionSummary()
        task_type_summary[task_key].total_cases += 1
        if case_passed:
            task_type_summary[task_key].passed_cases += 1
        if suppression_driven_failure:
            task_type_summary[task_key].suppressed_failures += 1

        results.append(
            EvalCaseResult(
                case_id=case.case_id,
                query=case.query,
                required_modules=case.required_modules,
                found_modules=found,
                missing_modules=missing,
                policy_suppressed_modules=suppressed,
                baseline_found_modules=baseline_found,
                context_tokens=context_tokens,
                first_hit_rank=ranking.first_hit_rank,
                mrr=ranking.mrr,
                ndcg_at_k=ranking.ndcg_at_k,
                recall_at_k=ranking.recall_at_k,
                failure_type=failure_type,
                passed=case_passed,
            )
        )
    total = len(suite.cases)
    hit_rate = round((passed / total) * 100, 1) if total else 0.0
    failed_cases = total - passed
    suppression_failure_rate = round((suppressed_failures / failed_cases) * 100, 1) if failed_cases else 0.0
    baseline_case_count = len(baseline_results or {})
    return EvalRunResult(
        name=suite.name,
        total_cases=total,
        passed_cases=passed,
        top_k=top_k,
        hit_rate=hit_rate,
        suppression_failure_rate=suppression_failure_rate,
        baseline_win_rate=round((baseline_wins / baseline_case_count) * 100, 1) if baseline_case_count else 0.0,
        false_positive_rate=round((false_positives / total) * 100, 1) if total else 0.0,
        false_negative_rate=round((false_negatives / total) * 100, 1) if total else 0.0,
        avg_context_tokens=round(total_context_tokens / total) if total else 0,
        avg_first_hit_rank=round(total_first_hit_rank / cases_with_first_hit, 2) if cases_with_first_hit else 0.0,
        avg_mrr=round(total_mrr / total, 4) if total else 0.0,
        avg_ndcg_at_k=round(total_ndcg_at_k / total, 4) if total else 0.0,
        avg_recall_at_k=round(total_recall_at_k / total, 4) if total else 0.0,
        policy_failure_rate=round((policy_failures / failed_cases) * 100, 1) if failed_cases else 0.0,
        retrieval_failure_rate=round((retrieval_failures / failed_cases) * 100, 1) if failed_cases else 0.0,
        risk_level_summary=risk_level_summary,
        task_type_summary=task_type_summary,
        results=results,
    )
