from knowledge_manager.retrieval_eval import score_ranked_case


def test_score_ranked_case_reports_mrr_ndcg_and_hit_position():
    summary = score_ranked_case(
        required_modules=["ops/runbook", "policy/change-approval"],
        found_modules=["auth/jwt", "ops/runbook", "policy/change-approval"],
    )

    assert summary.first_hit_rank == 2
    assert round(summary.mrr, 3) == 0.5
    assert round(summary.ndcg_at_k, 3) == 0.693
    assert summary.recall_at_k == 1.0
