import csv
import sys
import unittest
from io import StringIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_query_review_packet as packet
import run_candidate_baseline_eval as eval_script


class QueryReviewPacketTests(unittest.TestCase):
    def test_review_rows_include_module_titles_and_author_blank_fields(self):
        modules = {
            "architecture/git-native-storage": eval_script.ModuleRecord(
                module_id="architecture/git-native-storage",
                category="architecture",
                title="Git native storage",
                text="Knowledge modules are JSON files tracked in Git for review and audit.",
            )
        }
        raw_query = {
            "query_id": "Q1",
            "corpus_id": "km_methodology",
            "query": "为什么使用 Git JSON 存储知识模块？",
            "task_type": "decision",
            "scope_type": "in_scope",
            "difficulty": "medium",
            "required_modules": ["architecture/git-native-storage"],
            "nice_to_have_modules": [],
            "should_refuse_or_boundary_note": False,
            "expected_boundary": "",
            "judge_notes": "Candidate derived from module.",
            "edge_case_tags": [],
            "gold_evidence_spans": ["JSON files tracked in Git"],
            "status": "candidate_needs_author_review",
        }

        rows = packet.build_review_rows([raw_query], modules)

        self.assertEqual(rows[0]["query_id"], "Q1")
        self.assertIn("architecture/git-native-storage :: Git native storage", rows[0]["required_module_titles"])
        self.assertEqual(rows[0]["author_decision"], "")
        self.assertEqual(rows[0]["author_notes"], "")

    def test_csv_writer_outputs_review_columns(self):
        rows = [
            {
                "query_id": "Q1",
                "corpus_id": "km_methodology",
                "query": "query text",
                "task_type": "decision",
                "scope_type": "in_scope",
                "difficulty": "medium",
                "required_modules": "architecture/git-native-storage",
                "required_module_titles": "architecture/git-native-storage :: Git native storage",
                "nice_to_have_modules": "",
                "should_refuse_or_boundary_note": "False",
                "expected_boundary": "",
                "edge_case_tags": "",
                "gold_evidence_spans": "JSON files tracked in Git",
                "status": "candidate_needs_author_review",
                "judge_notes": "Candidate derived from module.",
                "author_decision": "",
                "author_corrected_required_modules": "",
                "author_boundary_revision": "",
                "author_notes": "",
            }
        ]
        sink = StringIO()

        packet.write_review_csv(rows, sink)
        parsed = list(csv.DictReader(StringIO(sink.getvalue())))

        self.assertEqual(parsed[0]["author_decision"], "")
        self.assertIn("author_corrected_required_modules", parsed[0])

    def test_markdown_summary_marks_packet_as_not_experiment_result(self):
        text = packet.render_markdown(
            rows=[
                {
                    "query_id": "Q1",
                    "corpus_id": "km_methodology",
                    "query": "query text",
                    "task_type": "decision",
                    "scope_type": "in_scope",
                    "difficulty": "medium",
                    "required_modules": "architecture/git-native-storage",
                    "required_module_titles": "architecture/git-native-storage :: Git native storage",
                    "nice_to_have_modules": "",
                    "should_refuse_or_boundary_note": "False",
                    "expected_boundary": "",
                    "edge_case_tags": "",
                    "gold_evidence_spans": "JSON files tracked in Git",
                    "status": "candidate_needs_author_review",
                    "judge_notes": "Candidate derived from module.",
                    "author_decision": "",
                    "author_corrected_required_modules": "",
                    "author_boundary_revision": "",
                    "author_notes": "",
                }
            ]
        )

        self.assertIn("不是实验结果", text)
        self.assertIn("author_decision", text)


if __name__ == "__main__":
    unittest.main()
