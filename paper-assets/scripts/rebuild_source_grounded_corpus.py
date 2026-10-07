"""Build an isolated, extractive paper corpus from existing project sources.

This script does not call a model or network service. Source excerpts and
character spans are preserved so every module can be checked against its input.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


SOURCES = [
    ("km-readme", "documentation", "knowledge-manager/README.md"),
    ("km-blueprint", "documentation", "knowledge-manager/docs/BLUEPRINT.md"),
    ("enterprise-rollout", "operations", "knowledge-manager/docs/runbooks/enterprise-rollout.md"),
    ("migration-cutover", "operations", "knowledge-manager/docs/runbooks/migration-cutover.md"),
    ("single-node-deploy", "operations", "knowledge-manager/docs/runbooks/deploy-single-node.md"),
    ("observability", "operations", "knowledge-manager/docs/runbooks/observability-and-alerting.md"),
    ("module-schemas", "implementation", "knowledge-manager/src/knowledge_manager/schemas.py"),
    ("routing-policy", "implementation", "knowledge-manager/src/knowledge_manager/policy.py"),
    ("retrieval-metrics", "implementation", "knowledge-manager/src/knowledge_manager/retrieval_eval.py"),
    ("markdown-format", "implementation", "knowledge-manager/src/knowledge_manager/markdown.py"),
]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def markdown_units(text: str) -> list[tuple[str, int, int]]:
    """Use actual headings outside code fences; preserve exact source slices."""
    positions: list[tuple[str, int]] = []
    offset = 0
    fence: str | None = None
    for line in text.splitlines(keepends=True):
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
        elif fence is None:
            heading = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
            if heading:
                positions.append((heading.group(1), offset))
        offset += len(line)
    if not positions:
        return [("Full document", 0, len(text))]
    if positions[0][1] > 0:
        positions.insert(0, ("Document preamble", 0))
    result = []
    for index, (title, start) in enumerate(positions):
        end = positions[index + 1][1] if index + 1 < len(positions) else len(text)
        if len(text[start:end].strip()) >= 40:
            result.append((title, start, end))
    return result


def python_units(text: str) -> list[tuple[str, int, int]]:
    """Use top-level definitions without running the source being studied."""
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    result = []
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            start_line = min([node.lineno] + [d.lineno for d in node.decorator_list])
            result.append((node.name, offsets[start_line - 1], offsets[node.end_lineno]))
    return result


def build(project: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite an existing corpus: {output}")
    # Validate every source before creating any corpus output.
    inputs = []
    for doc_id, category, relative in SOURCES:
        path = (project / relative).resolve()
        if not path.is_relative_to(project):
            raise ValueError(f"Source outside project: {relative}")
        data = path.read_bytes()
        text = data.decode("utf-8-sig")
        units = python_units(text) if path.suffix == ".py" else markdown_units(text)
        if not units:
            raise ValueError(f"No extractable units: {relative}")
        inputs.append((doc_id, category, relative, data, text, units))
    created = datetime.now(timezone.utc).isoformat()
    documents, module_entries, units_ledger = [], [], []
    for doc_id, category, relative, data, text, units in inputs:
        source_path = f"sources/{doc_id}{Path(relative).suffix}"
        snapshot = output / source_path
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes(data)
        documents.append({
            "document_id": doc_id, "original_project_path": relative,
            "snapshot_path": source_path, "sha256_bytes": digest(data),
            "decoded_character_count": len(text), "decode_policy": "utf-8-sig",
            "origin": "observed project file; original authorship not inferred",
            "public_release_rights": "NOT_REVIEWED", "generated_at_utc": created,
        })
        keys = [f"{category}/{doc_id}-{i:03d}" for i in range(1, len(units) + 1)]
        for index, (heading, start, end) in enumerate(units):
            module_id = f"{doc_id}-{index + 1:03d}"
            excerpt = text[start:end]
            span_id = f"{doc_id}:chars:{start}-{end}"
            # Related modules are adjacency links, not inferred semantic links.
            neighbors = keys[max(0, index - 1):index] + keys[index + 1:index + 2]
            module = {
                "id": module_id, "category": category,
                "title": f"{doc_id}: {heading}",
                "summary": f"Extractive snapshot of {relative}, section or definition {heading}.",
                "created_at": created, "updated_at": created,
                "content": {
                    "overview": f"Verbatim project-source evidence unit: {heading}.",
                    "details": excerpt, "examples": "",
                    "references": f"{source_path}; {span_id}; source SHA-256 {digest(data)}",
                    "caveats": "Automatically extracted; no human approval recorded. The excerpt describes project documentation or code, not verified deployment or performance. Adjacency links are not semantic relevance labels.",
                },
                "metadata": {
                    "tags": ["paper-case-study", "extractive", doc_id],
                    "related_modules": neighbors, "confidence": "medium",
                    "source": f"paper-corpus://{doc_id}",
                    "source_spans": [{"external_id": doc_id, "heading_path": [heading],
                        "excerpt": excerpt, "char_start": start, "char_end": end}],
                    "extraction_run_id": "source-grounded-v1", "status": "draft",
                },
            }
            path = f"modules/{category}/{module_id}.json"
            write_json(output / path, module)
            module_entries.append({"module_key": keys[index], "path": path,
                "document_id": doc_id, "evidence_unit_id": span_id,
                "excerpt_sha256_utf8": digest(excerpt.encode("utf-8"))})
            units_ledger.append({"evidence_unit_id": span_id, "document_id": doc_id,
                "char_start": start, "char_end": end,
                "line_start": text.count("\n", 0, start) + 1,
                "line_end": text.count("\n", 0, end - 1) + 1,
                "heading": heading, "module_key": keys[index]})
    write_json(output / "manifest.json", {
        "dataset_id": "km-project-sources-v1", "created_at_utc": created,
        "generation_method": "deterministic extractive segmentation; no generative model calls",
        "script_sha256": digest(Path(__file__).read_bytes()),
        "documents": documents, "modules": module_entries,
        "case_scope": "single-project documentation and source-code case study",
        "main_experiment_ready": False, "external_api_used": False,
        "review_status": "AUTOMATIC_EXTRACTION_NOT_HUMAN_APPROVED",
        "rights_status": "NOT_REVIEWED_FOR_PUBLIC_RELEASE",
        "limitations": ["Docs and code are not independent corpora", "Selected files are not a representative sample of external teams", "Human-relevance judgments and actual system retrieval experiments not completed", "Documentation claims are not proof of operational behavior"],
    })
    write_json(output / "evidence-units.json", units_ledger)
    return verify(output, project)


def verify(output: Path, project: Path | None = None) -> dict:
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    documents = {}
    for doc in manifest["documents"]:
        raw = (output / doc["snapshot_path"]).read_bytes()
        if digest(raw) != doc["sha256_bytes"]:
            raise ValueError(f"Snapshot hash mismatch: {doc['document_id']}")
        if project and digest((project / doc["original_project_path"]).read_bytes()) != doc["sha256_bytes"]:
            raise ValueError(f"Original source changed: {doc['document_id']}")
        documents[doc["document_id"]] = raw.decode("utf-8-sig")
    keys = [m["module_key"] for m in manifest["modules"]]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate module key")
    all_keys = set(keys)
    for entry in manifest["modules"]:
        module = json.loads((output / entry["path"]).read_text(encoding="utf-8"))
        span = module["metadata"]["source_spans"][0]
        source = documents[entry["document_id"]]
        exact = source[span["char_start"]:span["char_end"]]
        if exact != module["content"]["details"] or exact != span["excerpt"]:
            raise ValueError(f"Source span mismatch: {entry['module_key']}")
        if digest(exact.encode("utf-8")) != entry["excerpt_sha256_utf8"]:
            raise ValueError("Excerpt hash mismatch")
        if not set(module["metadata"]["related_modules"]).issubset(all_keys):
            raise ValueError("Unresolvable adjacency link")
        if module["metadata"]["status"] != "draft" or module["metadata"].get("reviewed_by"):
            raise ValueError("Unexpected human approval claim")
    ledger = json.loads((output / "evidence-units.json").read_text(encoding="utf-8"))
    if set(x["evidence_unit_id"] for x in ledger) != set(x["evidence_unit_id"] for x in manifest["modules"]):
        raise ValueError("Evidence ledger mismatch")
    return {"status": "PASS", "verification_scope": "source integrity and extractive construction only",
        "source_documents": len(documents), "modules": len(keys),
        "exact_source_spans_verified": len(keys), "adjacency_links_resolvable": True,
        "original_sources_unchanged": project is not None, "human_review_completed": False,
        "retrieval_or_task_performance_measured": False, "main_experiment_ready": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    project = args.project_root.resolve()
    output = (args.output or project / "paper-assets/corpora/km-project-sources-v1").resolve()
    if not output.is_relative_to(project / "paper-assets/corpora"):
        raise ValueError("Output must be inside this project's paper-assets/corpora")
    result = verify(output, project) if args.verify_only else build(project, output)
    write_json(output / "build-verification.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
