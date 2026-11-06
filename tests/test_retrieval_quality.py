import json


def test_evaluate_golden_set_reports_quality_and_leakage():
    from knowledge_manager.retrieval_eval import evaluate_golden_set

    class Result:
        def __init__(self, key):
            self.module = type("Module", (), {"category": key.split("/")[0], "id": key.split("/")[1]})()

    def search(_query, **_kwargs):
        return [Result("ops/runbook"), Result("policy/change-approval")]

    report = evaluate_golden_set(
        [{"query": "rollback", "required_modules": ["ops/runbook"], "allowed_modules": ["ops/runbook", "policy/change-approval"]}],
        search,
    )
    assert report["case_count"] == 1
    assert report["mean_recall_at_k"] == 1.0
    assert report["tenant_leakage_cases"] == 0


def test_quality_counts_misses_separately_and_rejects_empty_suite():
    import pytest
    from knowledge_manager.retrieval_eval import evaluate_golden_set

    with pytest.raises(ValueError):
        evaluate_golden_set([], lambda *_args, **_kwargs: [])
    report = evaluate_golden_set(
        [{"id": "unknown", "query": "absent", "required_modules": []}],
        lambda *_args, **_kwargs: [],
    )
    assert report["abstention_accuracy"] == 1.0
    assert report["positive_case_count"] == 0


def test_quality_catches_scope_leaks_without_explicit_allowlist():
    from types import SimpleNamespace
    from knowledge_manager.retrieval_eval import evaluate_golden_set

    module = SimpleNamespace(category="ops", id="secret", metadata=SimpleNamespace(tenant_id="b", workspace_id="w"))
    report = evaluate_golden_set(
        [{"query": "secret", "tenant_id": "a", "required_modules": []}],
        lambda *_args, **_kwargs: [SimpleNamespace(module=module)],
    )
    assert report["tenant_leakage_cases"] == 1
    assert report["abstention_accuracy"] == 0.0


def test_quality_positive_metrics_exclude_abstention_cases():
    from types import SimpleNamespace
    from knowledge_manager.retrieval_eval import evaluate_golden_set

    module = SimpleNamespace(category="ops", id="runbook")
    report = evaluate_golden_set(
        [
            {"query": "known", "required_modules": ["ops/runbook"]},
            {"query": "unknown", "required_modules": []},
        ],
        lambda query, **kwargs: [SimpleNamespace(module=module)] if query == "known" else [],
    )
    assert report["mean_recall_at_k"] == 1.0
    assert report["mean_mrr"] == 1.0
    assert report["mean_ndcg_at_k"] == 1.0
    assert report["abstention_accuracy"] == 1.0


def test_quality_catches_workspace_leak_and_counts_case_once():
    from types import SimpleNamespace
    from knowledge_manager.retrieval_eval import evaluate_golden_set

    module = SimpleNamespace(category="ops", id="secret", metadata=SimpleNamespace(tenant_id="a", workspace_id="other"))
    report = evaluate_golden_set(
        [{"query": "secret", "tenant_id": "a", "workspace_id": "mine", "allowed_modules": ["ops/allowed"], "required_modules": []}],
        lambda *_args, **_kwargs: [SimpleNamespace(module=module)],
    )
    assert report["tenant_leakage_cases"] == 1
