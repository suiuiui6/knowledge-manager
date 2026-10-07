import csv
import sys
import unittest
from io import StringIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import apply_author_review as review


def _csv_rows(rows):
    sink = StringIO()
    fieldnames = [
        "query_id",
        "corpus_id",
        "query",
        "task_type",
        "scope_type",
        "difficulty",
        "required_modules",
        "nice_to_have_modules",
        "should_refuse_or_boundary_note",
        "expected_boundary",
        "edge_case_tags",
        "gold_evidence_spans",
        "status",
        "judge_notes",
        "author_decision",
        "author_corrected_required_modules",
        "author_boundary_revision",
        "author_notes",
    ]
    writer = csv.DictWriter(sink, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return list(csv.DictReader(StringIO(sink.getvalue())))


class ApplyAuthorReviewTests(unittest.TestCase):
    def test_blank_author_decisions_block_output(self):
        rows = _csv_rows([
            {
                "query_id": "Q1",
                "corpus_id": "km_methodology",
                "query": "query",
                "task_type": "decision",
                "scope_type": "in_scope",
                "difficulty": "medium",
                "required_modules": "architecture/git-native-storage",
                "nice_to_have_modules": "",
                "should_refuse_or_boundary_note": "False",
                "expected_boundary": "",
                "edge_case_tags": "",
                "gold_evidence_spans": "span",
                "status": "candidate_needs_author_review",
                "judge_notes": "note",
                "author_decision": "",
                "author_corrected_required_modules": "",
                "author_boundary_revision": "",
                "author_notes": "",
            }
        ])

        with self.assertRaisesRegex(ValueError, "missing author_decision"):
            review.convert_review_rows(rows)

    def test_accept_emits_author_labeled_record(self):
        rows = _csv_rows([
            {
                "query_id": "Q1",
                "corpus_id": "km_methodology",
                "query": "query",
                "task_type": "decision",
                "scope_type": "in_scope",
                "difficulty": "medium",
                "required_modules": "architecture/git-native-storage",
                "nice_to_have_modules": "architecture/design-boundaries",
                "should_refuse_or_boundary_note": "False",
                "expected_boundary": "",
                "edge_case_tags": "broad_query",
                "gold_evidence_spans": "span",
                "status": "candidate_needs_author_review",
                "judge_notes": "note",
                "author_decision": "accept",
                "author_corrected_required_modules": "",
                "author_boundary_revision": "",
                "author_notes": "checked",
            }
        ])

        result = review.convert_review_rows(rows)

        self.assertEqual(len(result.accepted_records), 1)
        self.assertEqual(result.accepted_records[0]["status"], "author_labeled")
        self.assertEqual(result.accepted_records[0]["required_modules"], ["architecture/git-native-storage"])
        self.assertEqual(result.summary["accepted"], 1)

    def test_revise_uses_corrected_modules_and_boundary(self):
        rows = _csv_rows([
            {
                "query_id": "Q2",
                "corpus_id": "safety_hse",
                "query": "query",
                "task_type": "boundary",
                "scope_type": "partial_scope",
                "difficulty": "hard",
                "required_modules": "safety/confined-space-gas-control",
                "nice_to_have_modules": "",
                "should_refuse_or_boundary_note": "True",
                "expected_boundary": "old boundary",
                "edge_case_tags": "boundary_confusion; broad_query",
                "gold_evidence_spans": "span one; span two",
                "status": "candidate_needs_author_review",
                "judge_notes": "note",
                "author_decision": "revise",
                "author_corrected_required_modules": "safety/confined-space-gas-control; safety/confined-space-gas-monitoring",
                "author_boundary_revision": "revised boundary",
                "author_notes": "needs both gas modules",
            }
        ])

        result = review.convert_review_rows(rows)

        record = result.accepted_records[0]
        self.assertEqual(
            record["required_modules"],
            ["safety/confined-space-gas-control", "safety/confined-space-gas-monitoring"],
        )
        self.assertEqual(record["expected_boundary"], "revised boundary")
        self.assertIn("needs both gas modules", record["judge_notes"])

    def test_exclude_is_reported_but_not_written_to_accepted_jsonl(self):
        rows = _csv_rows([
            {
                "query_id": "Q3",
                "corpus_id": "software_engineering",
                "query": "query",
                "task_type": "boundary",
                "scope_type": "out_of_scope",
                "difficulty": "medium",
                "required_modules": "",
                "nice_to_have_modules": "",
                "should_refuse_or_boundary_note": "True",
                "expected_boundary": "outside",
                "edge_case_tags": "boundary_confusion",
                "gold_evidence_spans": "",
                "status": "candidate_needs_author_review",
                "judge_notes": "note",
                "author_decision": "exclude",
                "author_corrected_required_modules": "",
                "author_boundary_revision": "",
                "author_notes": "duplicate",
            }
        ])

        result = review.convert_review_rows(rows)

        self.assertEqual(result.accepted_records, [])
        self.assertEqual(result.excluded_records[0]["status"], "excluded")
        self.assertEqual(result.summary["excluded"], 1)


if __name__ == "__main__":
    unittest.main()
