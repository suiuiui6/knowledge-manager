from pathlib import Path

from knowledge_manager.eval_runner import EvalSuite, load_eval_suite, run_eval_suite
from knowledge_manager.schemas import Module, ModuleContent
from knowledge_manager.storage import save_module


def test_run_eval_suite_checks_required_modules_in_top_k(tmp_path):
    kb_path = tmp_path / "kb"
    save_module(
        Module(
            id="jwt-playbook",
            category="auth",
            title="JWT Playbook",
            summary="JWT production guide for auth flows.",
            content=ModuleContent(
                overview="JWT auth production overview for the team.",
                details="JWT auth production details and refresh token rotation guidance.",
            ),
        ),
        kb_path,
    )

    result = run_eval_suite(
        EvalSuite.model_validate(
            {
                "name": "smoke",
                "cases": [
                    {
                        "id": "jwt-hit",
                        "query": "jwt auth production",
                        "required_modules": ["auth/jwt-playbook"],
                        "top_k": 3,
                    }
                ],
            }
        ),
        kb_path,
    )

    assert result.total_cases == 1
    assert result.passed_cases == 1
    assert result.hit_rate == 100.0
    assert result.results[0].case_id == "jwt-hit"
    assert result.results[0].passed is True


def test_load_eval_suite_preserves_case_options(tmp_path):
    suite_path = tmp_path / "eval-suite.json"
    suite_path.write_text(
        """
        {
          "name": "smoke",
          "cases": [
            {
              "id": "jwt-hit",
              "query": "jwt auth production",
              "required_modules": ["auth/jwt-playbook"],
              "category": "auth",
              "top_k": 3
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    suite = load_eval_suite(Path(suite_path))
    assert suite.cases[0].case_id == "jwt-hit"
    assert suite.cases[0].category == "auth"
    assert suite.cases[0].top_k == 3


def test_run_eval_suite_reports_policy_suppressed_modules_and_missing_companions(tmp_path):
    kb_path = tmp_path / "kb"
    kb_path.mkdir()
    (kb_path / "config.json").write_text(
        """
        {
          "routing_policy": {
            "risk_level_allowed_statuses": {"high": ["published"]},
            "risk_level_companions": {"high": ["policy/change-approval"]}
          }
        }
        """,
        encoding="utf-8",
    )
    save_module(
        Module(
            id="draft-runbook",
            category="ops",
            title="Sensitive rollout draft",
            summary="Sensitive rollout draft guidance.",
            content=ModuleContent(
                overview="Sensitive rollout draft overview.",
                details="Sensitive rollout draft details with enough length for validation.",
            ),
            metadata={"status": "draft"},
        ),
        kb_path,
    )
    save_module(
        Module(
            id="published-runbook",
            category="ops",
            title="Sensitive rollout published",
            summary="Sensitive rollout published guidance.",
            content=ModuleContent(
                overview="Sensitive rollout published overview.",
                details="Sensitive rollout published details with enough length for validation.",
            ),
        ),
        kb_path,
    )

    result = run_eval_suite(
        EvalSuite.model_validate(
            {
                "name": "policy-smoke",
                "cases": [
                    {
                        "id": "high-risk-rollout",
                        "query": "sensitive rollout",
                        "required_modules": ["ops/published-runbook", "policy/change-approval"],
                        "risk_level": "high",
                        "top_k": 5
                    }
                ],
            }
        ),
        kb_path,
    )

    case = result.results[0]
    assert "policy/change-approval" in case.missing_modules
    assert "ops/draft-runbook" in case.policy_suppressed_modules


def test_load_eval_suite_preserves_policy_options(tmp_path):
    suite_path = tmp_path / "eval-suite.json"
    suite_path.write_text(
        """
        {
          "name": "policy-smoke",
          "cases": [
            {
              "id": "high-risk-rollout",
              "query": "sensitive rollout",
              "required_modules": ["ops/published-runbook"],
              "task_type": "production-change",
              "risk_level": "high",
              "agent_id": "incident-agent",
              "top_k": 5
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    suite = load_eval_suite(Path(suite_path))
    assert suite.cases[0].task_type == "production-change"
    assert suite.cases[0].risk_level == "high"
    assert suite.cases[0].agent_id == "incident-agent"


def test_run_eval_suite_computes_summary_and_suppression_failure_rate(tmp_path):
    kb_path = tmp_path / "kb"
    kb_path.mkdir()
    (kb_path / "config.json").write_text(
        """
        {
          "routing_policy": {
            "risk_level_allowed_statuses": {"high": ["published"]}
          }
        }
        """,
        encoding="utf-8",
    )
    save_module(
        Module(
            id="draft-runbook",
            category="ops",
            title="Sensitive rollout draft",
            summary="Sensitive rollout draft guidance.",
            content=ModuleContent(
                overview="Sensitive rollout draft overview.",
                details="Sensitive rollout draft details with enough length for validation.",
            ),
            metadata={"status": "draft"},
        ),
        kb_path,
    )
    save_module(
        Module(
            id="published-runbook",
            category="ops",
            title="Sensitive rollout published",
            summary="Sensitive rollout published guidance.",
            content=ModuleContent(
                overview="Sensitive rollout published overview.",
                details="Sensitive rollout published details with enough length for validation.",
            ),
        ),
        kb_path,
    )
    save_module(
        Module(
            id="safe-guide",
            category="ops",
            title="Safe rollout published",
            summary="Safe rollout guidance.",
            content=ModuleContent(
                overview="Safe rollout overview.",
                details="Safe rollout details with enough length for validation.",
            ),
        ),
        kb_path,
    )

    result = run_eval_suite(
        EvalSuite.model_validate(
            {
                "name": "summary-smoke",
                "cases": [
                    {
                        "id": "high-risk-fail",
                        "query": "sensitive rollout",
                        "required_modules": ["ops/published-runbook", "ops/draft-runbook"],
                        "risk_level": "high",
                        "task_type": "production-change",
                        "top_k": 5
                    },
                    {
                        "id": "low-risk-pass",
                        "query": "safe rollout",
                        "required_modules": ["ops/safe-guide"],
                        "risk_level": "low",
                        "task_type": "documentation",
                        "top_k": 5
                    }
                ],
            }
        ),
        kb_path,
    )

    assert result.suppression_failure_rate == 100.0
    assert result.risk_level_summary["high"].passed_cases == 0
    assert result.risk_level_summary["high"].suppressed_failures == 1
    assert result.risk_level_summary["low"].passed_cases == 1
    assert result.task_type_summary["production-change"].total_cases == 1
    assert result.task_type_summary["production-change"].suppressed_failures == 1


def test_run_eval_suite_reports_baseline_delta_and_failure_decomposition(tmp_path):
    kb_path = tmp_path / "kb"
    save_module(
        Module(
            id="jwt-playbook",
            category="auth",
            title="JWT Playbook",
            summary="JWT production guide for auth flows.",
            content=ModuleContent(
                overview="JWT auth production overview for the team.",
                details="JWT auth production details and refresh token rotation guidance.",
            ),
        ),
        kb_path,
    )

    result = run_eval_suite(
        EvalSuite.model_validate(
            {
                "name": "baseline-smoke",
                "cases": [
                    {
                        "id": "jwt-hit",
                        "query": "jwt auth production",
                        "required_modules": ["auth/jwt-playbook"],
                        "top_k": 3,
                    }
                ],
            }
        ),
        kb_path,
        baseline_results={"jwt-hit": {"required_hit": False, "tokens": 1800}},
    )

    assert result.baseline_win_rate == 100.0
    assert result.false_negative_rate == 0.0
    assert result.policy_failure_rate == 0.0
    assert result.retrieval_failure_rate == 0.0
    assert result.avg_context_tokens > 0
    assert result.results[0].failure_type == "none"
    assert result.false_positive_rate == 0.0


def test_run_eval_suite_does_not_count_extra_relevant_results_as_false_positives(tmp_path):
    kb_path = tmp_path / "kb"
    save_module(
        Module(
            id="jwt-playbook",
            category="auth",
            title="JWT Playbook",
            summary="JWT production guide for auth flows.",
            content=ModuleContent(
                overview="JWT auth production overview for the team.",
                details="JWT auth production details and refresh token rotation guidance.",
            ),
        ),
        kb_path,
    )
    save_module(
        Module(
            id="jwt-checklist",
            category="auth",
            title="JWT Checklist",
            summary="JWT production checklist for auth flows.",
            content=ModuleContent(
                overview="JWT checklist overview for the team.",
                details="JWT checklist details with refresh token guidance.",
            ),
        ),
        kb_path,
    )

    result = run_eval_suite(
        EvalSuite.model_validate(
            {
                "name": "precision-smoke",
                "cases": [
                    {
                        "id": "jwt-hit",
                        "query": "jwt production",
                        "required_modules": ["auth/jwt-playbook"],
                        "top_k": 5,
                    }
                ],
            }
        ),
        kb_path,
    )

    assert result.passed_cases == 1
    assert result.false_positive_rate == 0.0
    assert result.results[0].first_hit_rank == 1
    assert result.results[0].mrr == 1.0
    assert result.results[0].ndcg_at_k > 0.5
    assert result.avg_first_hit_rank == 1.0
    assert result.avg_mrr == 1.0
    assert result.avg_ndcg_at_k > 0.5
    assert result.avg_recall_at_k == 1.0
