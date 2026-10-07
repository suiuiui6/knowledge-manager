#!/usr/bin/env python
"""Build an author-review packet for candidate judged queries.

The packet is a labeling aid, not an experiment result. It keeps candidate
query labels separate from author-confirmed judged queries.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import TextIO

import run_candidate_baseline_eval as eval_script


DEFAULT_ROOT = Path(r"D:\tyh")
DEFAULT_QUERY_PATH = DEFAULT_ROOT / "paper-assets" / "eval" / "judged-queries.candidate.jsonl"
DEFAULT_OUT_CSV = DEFAULT_ROOT / "paper-assets" / "eval" / "judged-queries.author-review.csv"
DEFAULT_OUT_MD = DEFAULT_ROOT / "paper-assets" / "eval" / "judged-queries.author-review.md"
DEFAULT_OUT_JSON = DEFAULT_ROOT / "paper-assets" / "eval" / "judged-queries.author-review.json"

REVIEW_COLUMNS = [
    "query_id",
    "corpus_id",
    "query",
    "task_type",
    "scope_type",
    "difficulty",
    "required_modules",
    "required_module_titles",
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


def load_raw_queries(path: Path) -> list[dict]:
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _join(values: object) -> str:
    if isinstance(values, list):
        return "; ".join(str(value) for value in values)
    if values is None:
        return ""
    return str(values)


def _module_titles(module_ids: list[str], modules: dict[str, eval_script.ModuleRecord]) -> str:
    labels: list[str] = []
    for module_id in module_ids:
        module = modules.get(module_id)
        if module:
            labels.append(f"{module_id} :: {module.title}")
        else:
            labels.append(f"{module_id} :: [missing module]")
    return "; ".join(labels)


def build_review_rows(
    raw_queries: list[dict],
    modules: dict[str, eval_script.ModuleRecord],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for raw in raw_queries:
        required_modules = [str(item) for item in raw.get("required_modules", [])]
        row = {
            "query_id": str(raw.get("query_id", "")),
            "corpus_id": str(raw.get("corpus_id", "")),
            "query": str(raw.get("query", "")),
            "task_type": str(raw.get("task_type", "")),
            "scope_type": str(raw.get("scope_type", "")),
            "difficulty": str(raw.get("difficulty", "")),
            "required_modules": _join(required_modules),
            "required_module_titles": _module_titles(required_modules, modules),
            "nice_to_have_modules": _join(raw.get("nice_to_have_modules", [])),
            "should_refuse_or_boundary_note": str(raw.get("should_refuse_or_boundary_note", "")),
            "expected_boundary": str(raw.get("expected_boundary", "")),
            "edge_case_tags": _join(raw.get("edge_case_tags", [])),
            "gold_evidence_spans": _join(raw.get("gold_evidence_spans", [])),
            "status": str(raw.get("status", "")),
            "judge_notes": str(raw.get("judge_notes", "")),
            "author_decision": "",
            "author_corrected_required_modules": "",
            "author_boundary_revision": "",
            "author_notes": "",
        }
        rows.append(row)
    return rows


def write_review_csv(rows: list[dict[str, str]], sink: TextIO) -> None:
    writer = csv.DictWriter(sink, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in REVIEW_COLUMNS})


def render_markdown(rows: list[dict[str, str]]) -> str:
    lines = [
        "# Knowledge Manager judged queries 作者审阅包",
        "",
        "本文件用于逐条确认 candidate judged queries。它不是实验结果，也不能替代正式 baseline 结果表。",
        "",
        "作者审阅时建议填写 `author_decision`：`accept`、`revise`、`exclude` 或 `needs_discussion`。",
        "",
        "## 汇总",
        "",
        "| 项目 | 数量 |",
        "|---|---:|",
        f"| 待审阅 query | {len(rows)} |",
        "",
        "## 审阅清单",
        "",
    ]
    for index, row in enumerate(rows, start=1):
        lines.extend(
            [
                f"### {index}. {row['query_id']}",
                "",
                f"- corpus_id: `{row['corpus_id']}`",
                f"- query: {row['query']}",
                f"- task_type / scope_type / difficulty: `{row['task_type']}` / `{row['scope_type']}` / `{row['difficulty']}`",
                f"- required_modules: `{row['required_modules']}`",
                f"- required_module_titles: {row['required_module_titles']}",
                f"- nice_to_have_modules: `{row['nice_to_have_modules']}`",
                f"- should_refuse_or_boundary_note: `{row['should_refuse_or_boundary_note']}`",
                f"- expected_boundary: {row['expected_boundary']}",
                f"- gold_evidence_spans: {row['gold_evidence_spans']}",
                f"- judge_notes: {row['judge_notes']}",
                "- author_decision: ",
                "- author_corrected_required_modules: ",
                "- author_boundary_revision: ",
                "- author_notes: ",
                "",
            ]
        )
    return "\n".join(lines)


def write_packet(
    query_path: Path,
    kb_roots: list[Path],
    out_csv: Path,
    out_md: Path,
    out_json: Path,
) -> dict:
    modules = eval_script.load_modules(kb_roots)
    raw_queries = load_raw_queries(query_path)
    rows = build_review_rows(raw_queries, modules)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", encoding="utf-8-sig", newline="") as sink:
        write_review_csv(rows, sink)
    out_md.write_text(render_markdown(rows), encoding="utf-8")
    out_json.write_text(json.dumps({"status": "author_review_packet", "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "status": "author_review_packet",
        "query_count": len(rows),
        "out_csv": str(out_csv),
        "out_md": str(out_md),
        "out_json": str(out_json),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERY_PATH)
    parser.add_argument("--kb-root", type=Path, action="append", dest="kb_roots")
    parser.add_argument("--out-csv", type=Path, default=DEFAULT_OUT_CSV)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = write_packet(
        query_path=args.queries,
        kb_roots=args.kb_roots or eval_script.DEFAULT_KB_ROOTS,
        out_csv=args.out_csv,
        out_md=args.out_md,
        out_json=args.out_json,
    )
    print(f"status: {result['status']}")
    print(f"query_count: {result['query_count']}")
    print(f"wrote: {result['out_csv']}")
    print(f"wrote: {result['out_md']}")
    print(f"wrote: {result['out_json']}")


if __name__ == "__main__":
    main()
