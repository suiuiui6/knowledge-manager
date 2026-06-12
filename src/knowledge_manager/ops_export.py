from __future__ import annotations

from pathlib import Path
from typing import Any

from knowledge_manager.storage import generate_ops_report, list_staging_meta, load_search_events


def generate_review_backlog_export(kb_path: Path) -> dict[str, Any]:
    staging = kb_path / ".staging"
    metas = list_staging_meta(staging)
    report = generate_ops_report(kb_path)
    items = [
        {
            "module_id": meta.module_id,
            "status": meta.status,
            "submitted_by": meta.submitted_by,
            "submitted_at": meta.submitted_at.isoformat(),
            "review_count": len(meta.reviews),
        }
        for meta in metas
    ]
    return {
        "total": len(items),
        "items": items,
        "stale_sources": [entry.model_dump(mode="json") for entry in report.source_backlog],
    }


def generate_risky_miss_export(kb_path: Path) -> dict[str, Any]:
    events = load_search_events(kb_path)
    items = []
    for event in events:
        if event.get("type") != "search":
            continue
        if event.get("results_shown"):
            continue
        items.append(
            {
                "query_hash": event.get("query_hash", ""),
                "query_terms": event.get("query_terms", []),
                "timestamp": event.get("timestamp", ""),
            }
        )
    return {"total": len(items), "items": items}


def generate_source_backlog_export(kb_path: Path) -> dict[str, Any]:
    report = generate_ops_report(kb_path)
    return {
        "total": len(report.source_backlog),
        "items": [entry.model_dump(mode="json") for entry in report.source_backlog],
    }
