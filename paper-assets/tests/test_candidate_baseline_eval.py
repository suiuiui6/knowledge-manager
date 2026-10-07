import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_candidate_baseline_eval as eval_script


class CandidateBaselineEvalTests(unittest.TestCase):
    def test_module_ids_use_category_and_id(self):
        root = Path(__file__).resolve().parent / "fixtures" / "kb"
        modules = eval_script.load_modules([root])

        self.assertIn("architecture/git-native-storage", modules)
        self.assertEqual(modules["architecture/git-native-storage"].category, "architecture")

    def test_structured_module_ranking_reports_first_hit(self):
        modules = {
            "architecture/git-native-storage": eval_script.ModuleRecord(
                module_id="architecture/git-native-storage",
                category="architecture",
                title="Git native storage",
                text="Knowledge Manager stores JSON module files in Git for review audit and versioning.",
            ),
            "search/chinese-segmentation": eval_script.ModuleRecord(
                module_id="search/chinese-segmentation",
                category="search",
                title="Chinese segmentation",
                text="Search uses jieba segmentation for Chinese query tokenization.",
            ),
        }
        query = eval_script.QueryRecord(
            query_id="Q1",
            corpus_id="km_methodology",
            query="为什么使用 Git JSON 存储知识模块",
            required_modules=["architecture/git-native-storage"],
            status="candidate_needs_author_review",
        )

        result = eval_script.evaluate_system(
            system_name="structured_module_keyword",
            queries=[query],
            documents=eval_script.build_module_documents(modules),
            top_k=5,
        )

        self.assertEqual(result["query_count"], 1)
        self.assertEqual(result["MRR"], 1.0)
        self.assertEqual(result["first_hit_rank_mean"], 1.0)
        self.assertEqual(result["recall_at_5"], 1.0)

    def test_report_marks_candidate_results_as_not_main_results(self):
        payload = eval_script.build_report_payload(
            query_path=Path("judged-queries.candidate.jsonl"),
            query_status_counts={"candidate_needs_author_review": 30},
            system_results=[
                {
                    "system": "structured_module_keyword",
                    "query_count": 30,
                    "top_k": 5,
                    "MRR": 0.5,
                    "nDCG_at_5": 0.5,
                    "recall_at_5": 0.5,
                    "precision_at_5": 0.1,
                    "mean_latency_ms": 1.0,
                    "p95_latency_ms": 2.0,
                    "avg_loaded_units": 5.0,
                    "first_hit_rank_mean": 2.0,
                    "miss_count": 10,
                }
            ],
        )

        self.assertEqual(payload["status"], "candidate_not_main_result")
        self.assertFalse(payload["eligible_for_main_comparison"])
        self.assertIn("author_labeled", payload["eligibility_reason"])


if __name__ == "__main__":
    unittest.main()
