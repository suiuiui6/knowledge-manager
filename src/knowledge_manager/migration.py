from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


class ImportSummary(BaseModel):
    source_kind: str
    total_documents: int = 0
    creates: int = 0
    updates: int = 0
    skips: int = 0
    errors: list[str] = Field(default_factory=list)


def dry_run_import(source_path: Path, source_kind: str) -> ImportSummary:
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return ImportSummary(
            source_kind=source_kind,
            errors=["source payload must be a JSON array"],
        )

    creates = 0
    errors: list[str] = []
    for idx, item in enumerate(payload):
        if not isinstance(item, dict):
            errors.append(f"item {idx} must be an object")
            continue
        if not item.get("id"):
            errors.append(f"item {idx} missing id")
            continue
        creates += 1

    return ImportSummary(
        source_kind=source_kind,
        total_documents=len(payload),
        creates=creates,
        errors=errors,
    )
