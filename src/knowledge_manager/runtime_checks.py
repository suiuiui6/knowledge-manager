from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from knowledge_manager.auth import load_auth_config
from knowledge_manager.http_authz import SUPPORTED_AUTH_PROVIDERS
from knowledge_manager.ingestion_jobs import list_ingestion_jobs
from knowledge_manager.storage import _load_config_safe, list_modules, load_index, rebuild_index


def evaluate_readiness(kb_path: Path) -> dict[str, Any]:
    reasons: list[str] = []
    warnings: list[str] = []
    cfg = _load_config_safe(kb_path)
    if cfg is None:
        reasons.append("config missing or invalid")
    elif not cfg.llm_providers:
        reasons.append("default provider not configured")
    else:
        try:
            cfg.get_default_provider()
        except Exception:
            reasons.append("default provider not configured")
        if cfg.security.production_mode:
            auth_cfg = load_auth_config(kb_path)
            if auth_cfg is None or not auth_cfg.provider:
                reasons.append("authentication must be configured in production_mode")
            elif auth_cfg.provider not in SUPPORTED_AUTH_PROVIDERS:
                reasons.append(f"unsupported authentication provider: {auth_cfg.provider}")

    if load_index(kb_path) is None:
        reasons.append("index missing")

    failed_jobs = [job for job in list_ingestion_jobs(kb_path) if job.status == "failed"]
    if failed_jobs:
        reasons.append(f"failed ingestion jobs present: {len(failed_jobs)}")
    stale_running_jobs = []
    now = datetime.now(timezone.utc)
    for job in list_ingestion_jobs(kb_path):
        if job.status != "running" or job.lease_expires_at is None:
            continue
        lease = job.lease_expires_at
        if lease.tzinfo is None:
            lease = lease.replace(tzinfo=timezone.utc)
        if lease < now:
            stale_running_jobs.append(job)
    if stale_running_jobs:
        reasons.append(f"stale running ingestion jobs present: {len(stale_running_jobs)}")

    queued_maintenance = len(list((kb_path / ".cache" / "maintenance").glob("*.queued.json")))
    if cfg is not None:
        if queued_maintenance >= cfg.security.maintenance_backlog_fail:
            reasons.append(f"maintenance backlog above fail threshold: {queued_maintenance}")
        elif queued_maintenance >= cfg.security.maintenance_backlog_warn:
            warnings.append(f"maintenance backlog above warning threshold: {queued_maintenance}")

    integrity = run_integrity_check(kb_path)
    if not integrity["ok"]:
        reasons.append("integrity check failed")

    status = "ready" if not reasons and not warnings else ("degraded" if not reasons else "fail")
    return {
        "ready": not reasons,
        "status": status,
        "reasons": reasons,
        "warnings": warnings,
        "integrity_ok": integrity["ok"],
    }


def _actual_module_keys(kb_path: Path) -> set[str]:
    keys: set[str] = set()
    if not kb_path.exists():
        return keys
    for path in kb_path.rglob("*.json"):
        rel = path.relative_to(kb_path)
        if path.name in {"index.json", "config.json"} or path.name.endswith(".meta.json"):
            continue
        if any(part.startswith(".") for part in rel.parts[:-1]):
            continue
        if len(rel.parts) != 2:
            continue
        keys.add(f"{rel.parts[0]}/{path.stem}")
    return keys


def run_integrity_check(kb_path: Path) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    actual_modules = _actual_module_keys(kb_path)
    index = load_index(kb_path)
    index_modules: set[str] = set()

    if index is None:
        if actual_modules:
            issues.append(
                {
                    "kind": "missing_index",
                    "message": "index missing while module files exist",
                    "modules": sorted(actual_modules),
                }
            )
    else:
        for category, data in index.categories.items():
            for module in data.modules:
                index_modules.add(f"{category}/{module.id}")
        missing_in_index = sorted(actual_modules - index_modules)
        missing_on_disk = sorted(index_modules - actual_modules)
        if missing_in_index:
            issues.append(
                {
                    "kind": "index_missing_modules",
                    "message": "module files are missing from index",
                    "modules": missing_in_index,
                }
            )
        if missing_on_disk:
            issues.append(
                {
                    "kind": "index_dangling_modules",
                    "message": "index references modules missing on disk",
                    "modules": missing_on_disk,
                }
            )

    try:
        from knowledge_manager.search_projection import load_search_projection

        projection = load_search_projection(kb_path)
        if projection is not None:
            projection_keys = set(projection.get("documents", {}).keys())
            if projection_keys != actual_modules:
                issues.append(
                    {
                        "kind": "search_projection_drift",
                        "message": "search projection does not match module files",
                        "missing": sorted(actual_modules - projection_keys),
                        "extra": sorted(projection_keys - actual_modules),
                    }
                )
    except Exception:
        pass

    try:
        from knowledge_manager.recommendation_index import load_recommendation_index

        rec_index = load_recommendation_index(kb_path)
        if rec_index is not None:
            rec_keys = set(rec_index.get("modules", {}).keys())
            if rec_keys != actual_modules:
                issues.append(
                    {
                        "kind": "recommendation_index_drift",
                        "message": "recommendation index does not match module files",
                        "missing": sorted(actual_modules - rec_keys),
                        "extra": sorted(rec_keys - actual_modules),
                    }
                )
    except Exception:
        pass

    return {
        "ok": not issues,
        "module_count": len(actual_modules),
        "issues": issues,
    }


def collect_runtime_metrics(kb_path: Path) -> str:
    modules_total = len(list_modules(kb_path))
    index = load_index(kb_path)
    categories_total = len(index.categories) if index is not None else 0
    jobs = list_ingestion_jobs(kb_path)

    lines = [
        "# HELP knowledge_manager_modules_total Total visible modules on disk",
        "# TYPE knowledge_manager_modules_total gauge",
        f"knowledge_manager_modules_total {modules_total}",
        "# HELP knowledge_manager_categories_total Total index categories",
        "# TYPE knowledge_manager_categories_total gauge",
        f"knowledge_manager_categories_total {categories_total}",
    ]

    counts: dict[str, int] = {}
    for job in jobs:
        counts[job.status] = counts.get(job.status, 0) + 1
    for status in sorted(counts):
        lines.append(
            f'knowledge_manager_ingestion_jobs_total{{status="{status}"}} {counts[status]}'
        )
    if not counts:
        lines.append('knowledge_manager_ingestion_jobs_total{status="queued"} 0')
    return "\n".join(lines) + "\n"


def repair_runtime_artifacts(kb_path: Path) -> dict[str, Any]:
    rebuilt = rebuild_index(kb_path)
    repaired = ["index"]
    try:
        from knowledge_manager.lexical_index import build_lexical_index

        build_lexical_index(kb_path)
        repaired.append("lexical_index")
    except Exception:
        pass
    try:
        from knowledge_manager.search_projection import build_search_projection

        build_search_projection(kb_path)
        repaired.append("search_projection")
    except Exception:
        pass
    try:
        from knowledge_manager.recommendation_index import build_recommendation_index

        build_recommendation_index(kb_path)
        repaired.append("recommendation_index")
    except Exception:
        pass
    return {
        "ok": True,
        "repaired": repaired,
        "module_count": rebuilt.stats.total_modules,
    }
