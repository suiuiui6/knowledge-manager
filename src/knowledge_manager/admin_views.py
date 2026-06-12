from __future__ import annotations

from pathlib import Path
from typing import Any

from knowledge_manager.ingestion_jobs import list_ingestion_jobs
from knowledge_manager.ops_export import (
    generate_review_backlog_export,
    generate_source_backlog_export,
)


def build_admin_dashboard(kb_path: Path) -> dict[str, Any]:
    jobs = list_ingestion_jobs(kb_path)
    return {
        "ingestion_jobs": [job.model_dump(mode="json") for job in jobs],
        "stale_sources": generate_source_backlog_export(kb_path).get("items", []),
        "review_backlog": generate_review_backlog_export(kb_path).get("items", []),
        "eval_regressions": [],
    }
