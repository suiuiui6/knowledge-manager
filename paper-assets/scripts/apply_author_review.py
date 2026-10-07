#!/usr/bin/env python
"""Convert an author-reviewed query CSV into judged-query JSONL.

The converter refuses to produce an author-labeled file while any row has a
blank or unresolved author decision.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path


DEFAULT_ROOT = Path(r"D:\tyh")
DEFAULT_REVIEW_CSV = DEFAULT_ROOT / "paper-assets" / "eval" / "judged-queries.author-review.csv"
DEFAULT_OUT_JSONL = DEFAULT_ROOT / "paper-assets" / "eval" / "judged-queries.author-labeled.jsonl"
DEFAULT_OUT_EXCLUDED = DEFAULT_ROOT / "paper-assets" / "eval" / "judged-queries.excluded.jsonl"
DEFAULT_OUT_SUMMARY = DEFAULT_ROOT / "paper-assets" / "eval" / "judged-queries.author-labeled.summary.json"

VALID_DECISIONS = {"accept", "revise", "exclude", "needs_discussion"}
UNRESOLVED_DECISIONS = {"", "needs_discussion"}


@dataclass(frozen=True)
class ConversionResult:
    accepted_records: list[dict]
    excluded_records: list[dict]
    summary: dict


def _split(value: str | None) -> list[str]:
    if not value:
        return []
    normalized = value.replace(",", ";")
    return [part.strip() for part in normalized.split(";") if part.strip()]


def _bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def _record_from_row(row: dict[str, str], status: str) -> dict:
    decision = (row.get("author_decision") or "").strip().lower()
    required_modules = _split(row.get("required_modules"))
    expected_boundary = row.get("expected_boundary", "")
    if decision == "revise":
        corrected = _split(row.get("author_corrected_required_modules"))
        if corrected:
            required_modules = corrected
        boundary_revision = (row.get("author_boundary_revision") or "").strip()
        if boundary_revision:
            expected_boundary = boundary_revision

    author_notes = (row.get("author_notes") or "").strip()
    judge_notes = row.get("judge_notes", "")
    if author_notes:
        judge_notes = f"{judge_notes} Author review: {author_notes}".strip()

    record = {
        "query_id": row.get("query_id", ""),
        "corpus_id": row.get("corpus_id", ""),
        "query": row.get("query", ""),
        "task_type": row.get("task_type", ""),
        "scope_type": row.get("scope_type", ""),
        "difficulty": row.get("difficulty", ""),
        "required_modules": required_modules,
        "nice_to_have_modules": _split(row.get("nice_to_have_modules")),
        "should_refuse_or_boundary_note": _bool(row.get("should_refuse_or_boundary_note")),
        "expected_boundary": expected_boundary,
        "judge_notes": judge_notes,
        "edge_case_tags": _split(row.get("edge_case_tags")),
        "status": status,
    }
    source_doc_ids = _split(row.get("source_doc_ids"))
    gold_evidence_spans = _split(row.get("gold_evidence_spans"))
    relevance_grade = (row.get("relevance_grade") or "").strip()
    if source_doc_ids:
        record["source_doc_ids"] = source_doc_ids
    if gold_evidence_spans:
        record["gold_evidence_spans"] = gold_evidence_spans
    if relevance_grade:
        record["relevance_grade"] = relevance_grade
    elif gold_evidence_spans:
        record["relevance_grade"] = "binary"
    return record


def convert_review_rows(rows: list[dict[str, str]]) -> ConversionResult:
    accepted_records: list[dict] = []
    excluded_records: list[dict] = []
    unresolved: list[str] = []
    invalid: list[str] = []
    revised = 0

    for row in rows:
        query_id = row.get("query_id", "")
        decision = (row.get("author_decision") or "").strip().lower()
        if decision == "":
            unresolved.append(query_id or "<missing query_id>")
            continue
        if decision not in VALID_DECISIONS:
            invalid.append(query_id or "<missing query_id>")
            continue
        if decision in UNRESOLVED_DECISIONS:
            unresolved.append(query_id or "<missing query_id>")
            continue
        if decision == "exclude":
            excluded_records.append(_record_from_row(row, "excluded"))
            continue
        if decision == "revise":
            revised += 1
        accepted_records.append(_record_from_row(row, "author_labeled"))

    if invalid:
        raise ValueError("invalid author_decision for: " + ", ".join(invalid))
    if unresolved:
        missing = "missing author_decision" if any(not (row.get("author_decision") or "").strip() for row in rows) else "unresolved author_decision"
        raise ValueError(f"{missing} for: " + ", ".join(unresolved))

    return ConversionResult(
        accepted_records=accepted_records,
        excluded_records=excluded_records,
        summary={
            "status": "author_labeled_ready",
            "input_rows": len(rows),
            "accepted": len(accepted_records),
            "revised": revised,
            "excluded": len(excluded_records),
        },
    )


def load_review_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def write_jsonl(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def convert_file(review_csv: Path, out_jsonl: Path, out_excluded: Path, out_summary: Path) -> ConversionResult:
    rows = load_review_csv(review_csv)
    result = convert_review_rows(rows)
    write_jsonl(result.accepted_records, out_jsonl)
    write_jsonl(result.excluded_records, out_excluded)
    out_summary.write_text(json.dumps(result.summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-csv", type=Path, default=DEFAULT_REVIEW_CSV)
    parser.add_argument("--out-jsonl", type=Path, default=DEFAULT_OUT_JSONL)
    parser.add_argument("--out-excluded", type=Path, default=DEFAULT_OUT_EXCLUDED)
    parser.add_argument("--out-summary", type=Path, default=DEFAULT_OUT_SUMMARY)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        result = convert_file(args.review_csv, args.out_jsonl, args.out_excluded, args.out_summary)
    except ValueError as error:
        raise SystemExit(f"author review is not ready: {error}") from error
    print(f"status: {result.summary['status']}")
    print(f"accepted: {result.summary['accepted']}")
    print(f"excluded: {result.summary['excluded']}")
    print(f"wrote: {args.out_jsonl}")
    print(f"wrote: {args.out_excluded}")
    print(f"wrote: {args.out_summary}")


if __name__ == "__main__":
    main()
