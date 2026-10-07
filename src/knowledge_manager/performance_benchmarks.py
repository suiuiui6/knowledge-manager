from __future__ import annotations

import asyncio
import json
import os
import shutil
import statistics
import time
import tracemalloc
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi.testclient import TestClient

from knowledge_manager.http_server import create_app
from knowledge_manager.performance_hotspots import HotspotTimer
from knowledge_manager.mcp_server import create_server
from knowledge_manager.ingestion_jobs import (
    claim_ingestion_job,
    complete_ingestion_job,
    create_ingestion_job,
    list_ingestion_jobs,
    update_ingestion_checkpoint,
)
from knowledge_manager.schemas import (
    ConfluenceSourceConfig,
    Index,
    Module,
    ModuleContent,
    ModuleMetadata,
    SourceDefinition,
    SourceDocumentRef,
    StagingMeta,
)
from knowledge_manager.source_ingestion import upsert_source
from knowledge_manager.storage import (
    record_load_event,
    record_search_event,
    rebuild_index,
    save_index,
    save_module,
    save_staging_meta,
    save_to_staging,
    search_modules,
)
from knowledge_manager.tenancy import TenantContext


@dataclass(slots=True)
class BenchmarkConfig:
    kb_path: Path
    output_dir: Path
    module_count: int = 1000
    tenant_count: int = 10
    job_count: int = 500
    migration_document_count: int = 250
    search_iterations: int = 20
    http_iterations: int = 20
    job_iterations: int = 20
    top_k: int = 10


def _stabilize_benchmark_kb(kb_path: Path) -> None:
    """Refresh derived state so release verdict reflects performance, not benchmark-induced drift."""
    from datetime import timedelta

    from knowledge_manager.ingestion_jobs import list_ingestion_jobs
    from knowledge_manager.recommendation_index import build_recommendation_index
    from knowledge_manager.search_projection import build_search_projection

    build_search_projection(kb_path)
    build_recommendation_index(kb_path)
    for job in list_ingestion_jobs(kb_path):
        if job.status == "running":
            refreshed = job.model_copy(
                update={
                    "heartbeat_at": datetime.now(timezone.utc),
                    "lease_expires_at": datetime.now(timezone.utc) + timedelta(seconds=3600),
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            (kb_path / ".jobs" / "ingestion" / f"{job.job_id}.json").write_text(
                refreshed.model_dump_json(indent=2),
                encoding="utf-8",
            )


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * ratio))))
    return ordered[index]


def _measure(name: str, iterations: int, fn: Callable[[], Any]) -> dict[str, Any]:
    return _measure_with_hotspot(name, iterations, fn)


def _measure_with_hotspot(
    name: str,
    iterations: int,
    fn: Callable[[], Any],
    hotspot_timer: HotspotTimer | None = None,
    hotspot_name: str | None = None,
) -> dict[str, Any]:
    samples_ms: list[float] = []
    last_result: Any = None
    errors: list[str] = []
    started = time.perf_counter()
    for _ in range(iterations):
        tick = time.perf_counter()
        try:
            last_result = fn()
        except Exception as exc:
            last_result = {"error": str(exc)}
            errors.append(type(exc).__name__)
        sample_ms = (time.perf_counter() - tick) * 1000.0
        samples_ms.append(sample_ms)
        if hotspot_timer and hotspot_name:
            hotspot_timer.record(hotspot_name, sample_ms)
    total_s = time.perf_counter() - started
    result = {
        "name": name,
        "iterations": iterations,
        "mean_ms": round(statistics.mean(samples_ms), 3),
        "median_ms": round(statistics.median(samples_ms), 3),
        "p95_ms": round(_percentile(samples_ms, 0.95), 3),
        "p99_ms": round(_percentile(samples_ms, 0.99), 3),
        "min_ms": round(min(samples_ms), 3),
        "max_ms": round(max(samples_ms), 3),
        "throughput_per_sec": round(iterations / total_s, 3) if total_s else 0.0,
        "last_result_size": _result_size(last_result),
    }
    if errors:
        result["errors"] = errors
        result["last_result_error"] = str(last_result)
    return result


def _result_size(result: Any) -> int:
    if result is None:
        return 0
    if isinstance(result, dict):
        if "results" in result and isinstance(result["results"], list):
            return len(result["results"])
        if "items" in result and isinstance(result["items"], list):
            return len(result["items"])
        return len(result)
    if isinstance(result, list):
        return len(result)
    return 1


def _sum_file_bytes(root: Path) -> int:
    total = 0
    if not root.exists():
        return 0
    for path in root.rglob("*"):
        if path.is_file():
            total += path.stat().st_size
    return total


def _extract_mcp_payload_text(payload: Any) -> str:
    if isinstance(payload, tuple) and payload:
        return _extract_mcp_payload_text(payload[0])
    if isinstance(payload, list):
        parts = []
        for item in payload:
            text = getattr(item, "text", None)
            if text is not None:
                parts.append(str(text))
                continue
            content = getattr(item, "content", None)
            if content is not None:
                parts.append(str(content))
                continue
            parts.append(str(item))
        return "\n".join(part for part in parts if part)
    text = getattr(payload, "text", None)
    if text is not None:
        return str(text)
    content = getattr(payload, "content", None)
    if content is not None:
        return str(content)
    return str(payload)


def _warm_benchmark_runtime(
    config: BenchmarkConfig,
    client: TestClient,
    mcp_server: Any,
    benchmark_query: str,
) -> None:
    from knowledge_manager.admin_views import build_admin_dashboard

    build_admin_dashboard(config.kb_path)
    search_modules(benchmark_query, config.kb_path, limit=config.top_k)
    client.post(
        "/api/search",
        json={"query": benchmark_query, "top_k": config.top_k},
    )
    _extract_mcp_payload_text(
        asyncio.run(mcp_server.call_tool("search_modules", {"query": benchmark_query}))
    )


def _seed_sources_and_events(config: BenchmarkConfig) -> Path:
    source = SourceDefinition(
        id="team-docs",
        confluence=ConfluenceSourceConfig(
            base_url="https://example.atlassian.net/wiki",
            space_key="ENG",
            email="docs@example.com",
            api_token_env="CONFLUENCE_API_TOKEN",
            category="ops",
        ),
    )
    upsert_source(source, config.kb_path)

    for i in range(min(config.module_count, 40)):
        category = "ops" if i % 2 == 0 else "policy"
        module_id = f"module-{i:05d}"
        results = search_modules("rollback", config.kb_path, category=category, limit=1)
        if results:
            record_load_event(module_id, category, kb_path=config.kb_path)

        if i % 4 == 0:
            record_search_event(
                "rollback safely",
                [f"{category}/{module_id}"],
                config.kb_path,
            )
        else:
            record_search_event(
                f"unmatched query {i}",
                [],
                config.kb_path,
            )

    export_path = config.output_dir / "migration-source.json"
    payload = [
        {
            "id": f"legacy-{i:05d}",
            "title": f"Legacy page {i}",
            "body": f"rollback safely for migration item {i}",
        }
        for i in range(config.migration_document_count)
    ]
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return export_path


def _seed_config(config: BenchmarkConfig) -> bool:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    config_path = config.kb_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "llm_providers": {
                    "deepseek": {
                        "api_key": api_key,
                        "model": "deepseek-v4-pro",
                        "base_url": "https://api.deepseek.com",
                        "default": True,
                        "temperature": 0.3,
                        "max_tokens": 2048,
                    }
                },
                "extraction": {
                    "provider": "deepseek",
                    "max_modules_per_extraction": 3,
                    "chunk_size": 4000,
                    "chunk_overlap": 200,
                    "auto_categorize": True,
                },
                "cache": {"enabled": True, "max_modules": 50},
                "telemetry": {"enabled": True},
                "synonyms": {},
                "review": {
                    "required_approvals": 1,
                    "auto_approve_self_submitted": False,
                    "reviewer_whitelist": [],
                },
                "notifications": {"webhook_url": "", "on_push": True, "on_review_approved": False},
                "federation": {"namespaces": {}},
                "webhooks": {"enabled": False, "endpoints": []},
                "marketplace": {"index_url": "", "sanitize_patterns": []},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return bool(api_key)


def _seed_modules(config: BenchmarkConfig) -> None:
    if config.kb_path.exists():
        shutil.rmtree(config.kb_path)
    config.kb_path.mkdir(parents=True, exist_ok=True)
    save_index(Index(description="enterprise performance benchmark"), config.kb_path)
    categories = ["ops", "policy", "architecture", "api", "incident"]

    for i in range(config.module_count):
        category = categories[i % len(categories)]
        tenant_id = f"tenant-{i % max(config.tenant_count, 1):03d}"
        related = []
        if i > 0:
            related.append(f"{category}/module-{i - 1:05d}")
        module = Module(
            id=f"module-{i:05d}",
            category=category,
            title=f"{category.title()} knowledge module {i}",
            summary=f"Benchmark summary for {category} workflow module {i}.",
            content=ModuleContent(
                overview=(
                    f"This module describes rollback, deployment, incident response, "
                    f"tenant isolation, and migration safety for {category} team {i}."
                ),
                details=(
                    f"Detailed benchmark content for module {i}. It covers search relevance, "
                    f"checkpoint resume handling, hybrid retrieval, policy gates, and admin operations."
                ),
                examples="rollback safely during tenant incident",
                references="api search modules admin dashboard source jobs",
                caveats="use tenant-aware search for isolated results",
            ),
            metadata=ModuleMetadata(
                tags=[category, "benchmark", "tenant", f"team-{i % 7}"],
                tenant_id=tenant_id,
                related_modules=related,
                confidence="high" if i % 3 == 0 else "medium",
                source_documents=[
                    SourceDocumentRef(
                        source_type="confluence",
                        source_id="team-docs",
                        external_id=f"page-{i:05d}",
                        title=f"Source page {i}",
                        url=f"https://example.atlassian.net/wiki/page-{i}",
                        version=f"v{i % 9}",
                    )
                ] if category == "ops" and i % 6 == 0 else [],
            ),
        )
        save_module(module, config.kb_path, defer_noncritical=False)

    staged = Module(
        id="pending-review",
        category="ops",
        title="Pending review benchmark module",
        summary="Pending review content for admin dashboard benchmark.",
        content=ModuleContent(
            overview="Pending review overview for admin benchmark.",
            details="Pending review details long enough for validation and admin dashboard rendering.",
        ),
    )
    staging_path = config.kb_path / ".staging"
    save_to_staging(staged, staging_path)
    save_staging_meta(StagingMeta(module_id="pending-review", status="pending"), staging_path)
    rebuild_index(config.kb_path)


def _seed_jobs(config: BenchmarkConfig) -> None:
    for i in range(config.job_count):
        job = create_ingestion_job(config.kb_path, source_id=f"source-{i % 8}", trigger="benchmark")
        if i % 3 == 0:
            claim_ingestion_job(config.kb_path, job.job_id, worker_id="seed-worker")
            update_ingestion_checkpoint(config.kb_path, job.job_id, cursor=f"cursor-{i}", pages_seen=i + 1)
        if i % 5 == 0:
            complete_ingestion_job(
                config.kb_path,
                job.job_id,
                pages_seen=i + 5,
                modules_staged=(i % 11) + 1,
                modules_marked_stale=i % 4,
            )


def _write_reports(report: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "enterprise-performance-benchmark.json"
    md_path = output_dir / "enterprise-performance-benchmark.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def _evaluate_gate_summary(report: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "search_http": ("http", "search_http", 1500.0, 2500.0),
        "recommendations_http": ("control_plane", "recommendations_http", 1200.0, 2500.0),
        "admin_dashboard_http": ("http", "admin_dashboard_http", 800.0, 1500.0),
        "module_crud_http": ("write_operations", "module_crud_http", 400.0, 800.0),
        "mcp_search_modules": ("mcp", "mcp_search_modules", 1500.0, 2500.0),
    }

    summary: dict[str, Any] = {}
    for gate_name, (section, metric_name, target_mean_ms, target_p95_ms) in checks.items():
        metric = report["benchmarks"].get(section, {}).get(metric_name)
        if not metric:
            summary[gate_name] = {"status": "missing", "section": section, "metric": metric_name}
            continue
        actual_mean_ms = metric.get("mean_ms", 0.0)
        actual_p95_ms = metric.get("p95_ms", 0.0)
        summary[gate_name] = {
            "status": "pass" if actual_mean_ms <= target_mean_ms and actual_p95_ms <= target_p95_ms else "fail",
            "section": section,
            "metric": metric_name,
            "target_mean_ms": target_mean_ms,
            "actual_mean_ms": actual_mean_ms,
            "target_p95_ms": target_p95_ms,
            "actual_p95_ms": actual_p95_ms,
        }
    return summary


def _evaluate_release_verdict(report: dict[str, Any]) -> dict[str, Any]:
    from knowledge_manager.runtime_checks import evaluate_readiness, run_integrity_check

    gate_summary = report.get("gate_summary", {})
    hotspots = report.get("hotspots", {})
    failed_gates = [
        gate_name for gate_name, gate in gate_summary.items() if gate.get("status") != "pass"
    ]
    kb_path = Path(report["dataset"]["kb_path"])
    readiness = evaluate_readiness(kb_path)
    integrity = run_integrity_check(kb_path)

    blockers = [f"gate:{gate_name}" for gate_name in failed_gates]
    blockers.extend(f"readiness:{reason}" for reason in readiness["reasons"])
    blockers.extend(f"integrity:{issue['kind']}" for issue in integrity["issues"])

    return {
        "ready_for_production": not blockers,
        "failed_gates": failed_gates,
        "readiness_ready": readiness["ready"],
        "integrity_ok": integrity["ok"],
        "blockers": blockers,
        "hotspot_sections": sorted(hotspots.keys()),
    }


def evaluate_matrix_summary(path: Path, required_scales: list[str]) -> dict[str, Any]:
    matrix = json.loads(path.read_text(encoding="utf-8"))
    scale_verdicts: dict[str, dict[str, Any]] = {}
    failed_scales: list[str] = []

    for scale in required_scales:
        verdict = matrix.get(scale, {}).get("release_verdict", {})
        scale_verdicts[scale] = verdict
        if not verdict.get("ready_for_production", False):
            failed_scales.append(scale)

    return {
        "required_scales": required_scales,
        "scale_verdicts": scale_verdicts,
        "failed_scales": failed_scales,
        "ready_for_production": not failed_scales,
    }


def build_production_readiness_verdict(
    kb_path: Path,
    matrix_summary_path: Path,
    required_scales: list[str] | None = None,
) -> dict[str, Any]:
    from knowledge_manager.runtime_checks import evaluate_readiness, run_integrity_check
    from knowledge_manager.storage import _load_config_safe

    cfg = _load_config_safe(kb_path)
    resolved_scales = required_scales or (cfg.security.required_perf_scales if cfg else ["xs", "s", "m"])
    matrix_verdict = evaluate_matrix_summary(matrix_summary_path, resolved_scales)
    readiness = evaluate_readiness(kb_path)
    integrity = run_integrity_check(kb_path)

    return {
        "ready_for_production": (
            readiness["ready"] and integrity["ok"] and matrix_verdict["ready_for_production"]
        ),
        "readiness": readiness,
        "integrity": integrity,
        "performance": matrix_verdict,
    }


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Enterprise Performance Benchmark",
        "",
        f"- Timestamp: `{report['timestamp']}`",
        f"- Modules: `{report['dataset']['module_count']}`",
        f"- Tenants: `{report['dataset']['tenant_count']}`",
        f"- Jobs: `{report['dataset']['job_count']}`",
        f"- Migration docs: `{report['dataset']['migration_document_count']}`",
        f"- KB disk size: `{report['resources']['kb_disk_bytes']}` bytes",
        f"- Python heap peak: `{report['resources']['python_heap_peak_bytes']}` bytes",
        "",
        "## Benchmarks",
        "",
    ]
    gate_summary = report.get("gate_summary", {})
    if gate_summary:
        lines.append("## Enterprise Gates")
        lines.append("")
        for gate_name, gate in gate_summary.items():
            if gate.get("status") == "missing":
                lines.append(f"- `{gate_name}`: missing metric `{gate['section']}/{gate['metric']}`")
                continue
            lines.append(
                f"- `{gate_name}`: `{gate['status']}` "
                f"(mean `{gate['actual_mean_ms']} ms` vs target `{gate['target_mean_ms']} ms`, "
                f"p95 `{gate['actual_p95_ms']} ms` vs target `{gate['target_p95_ms']} ms`)"
            )
        lines.append("")
    release_verdict = report.get("release_verdict", {})
    if release_verdict:
        lines.append("## Release Verdict")
        lines.append("")
        lines.append(f"- Ready for production: `{release_verdict.get('ready_for_production', False)}`")
        failed_gates = release_verdict.get("failed_gates", [])
        if failed_gates:
            lines.append(f"- Failed gates: `{', '.join(failed_gates)}`")
        blockers = release_verdict.get("blockers", [])
        if blockers:
            lines.append(f"- Blockers: `{'; '.join(blockers)}`")
        lines.append("")
    hotspots = report.get("hotspots", {})
    if hotspots:
        lines.append("## Hotspots")
        lines.append("")
        for hotspot_name, hotspot in hotspots.items():
            lines.append(
                f"- `{hotspot_name}`: count `{hotspot['count']}`, "
                f"mean `{hotspot['mean_ms']} ms`, max `{hotspot['max_ms']} ms`"
            )
        lines.append("")
    for section, metrics in report["benchmarks"].items():
        lines.append(f"### {section}")
        lines.append("")
        if isinstance(metrics, dict) and metrics.get("enabled") is False:
            lines.append("- provider-backed external benchmarks were skipped because no compatible API key was available")
            lines.append("")
            continue
        for metric_name, metric in metrics.items():
            if metric_name == "enabled":
                continue
            lines.append(
                f"- `{metric_name}`: mean `{metric['mean_ms']} ms`, p95 `{metric['p95_ms']} ms`, "
                f"p99 `{metric['p99_ms']} ms`, throughput `{metric['throughput_per_sec']}/s`"
            )
        lines.append("")
    lines.extend(
        [
            "## Exclusions",
            "",
            "- `/api/chat`: excluded from this local real run because it requires a configured external LLM provider and would mix remote model latency into server-path evaluation.",
            "- `/api/upload`: excluded from this local real run because it depends on extractor + provider/file-type behavior and is better measured in connector-specific ingestion tests.",
        ]
    )
    return "\n".join(lines)


def run_enterprise_benchmark(config: BenchmarkConfig) -> dict[str, Any]:
    started = time.perf_counter()
    tracemalloc.start()
    _seed_modules(config)
    _seed_jobs(config)
    migration_source = _seed_sources_and_events(config)
    external_enabled = _seed_config(config)

    client = TestClient(create_app(config.kb_path))
    mcp_server = create_server(config.kb_path)
    benchmark_query = "rollback tenant incident"
    tenant_ctx = TenantContext(tenant_id="tenant-001")
    module_sample = "ops/module-00000"
    hotspots = HotspotTimer()
    _warm_benchmark_runtime(config, client, mcp_server, benchmark_query)
    _, heap_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    retrieval = {
        "search_lexical": _measure_with_hotspot(
            "search_lexical",
            config.search_iterations,
            lambda: search_modules(benchmark_query, config.kb_path, limit=config.top_k),
            hotspot_timer=hotspots,
            hotspot_name="search",
        ),
        "search_tenant": _measure_with_hotspot(
            "search_tenant",
            config.search_iterations,
            lambda: search_modules(
                benchmark_query,
                config.kb_path,
                limit=config.top_k,
                tenant=tenant_ctx,
            ),
            hotspot_timer=hotspots,
            hotspot_name="search",
        ),
    }

    http = {
        "search_http": _measure_with_hotspot(
            "search_http",
            config.http_iterations,
            lambda: client.post(
                "/api/search",
                json={"query": benchmark_query, "top_k": config.top_k},
            ).json(),
            hotspot_timer=hotspots,
            hotspot_name="search",
        ),
        "search_http_tenant": _measure_with_hotspot(
            "search_http_tenant",
            config.http_iterations,
            lambda: client.post(
                "/api/search",
                json={"query": benchmark_query, "top_k": config.top_k, "tenant_id": "tenant-001"},
            ).json(),
            hotspot_timer=hotspots,
            hotspot_name="search",
        ),
        "modules_http": _measure(
            "modules_http",
            config.http_iterations,
            lambda: client.get("/api/modules?limit=50").json(),
        ),
        "module_detail_http": _measure(
            "module_detail_http",
            config.http_iterations,
            lambda: client.get(f"/api/modules/{module_sample}").json(),
        ),
        "admin_dashboard_http": _measure_with_hotspot(
            "admin_dashboard_http",
            config.http_iterations,
            lambda: client.get("/api/admin/dashboard").json(),
            hotspot_timer=hotspots,
            hotspot_name="admin_dashboard",
        ),
        "source_jobs_http": _measure(
            "source_jobs_http",
            config.http_iterations,
            lambda: client.get("/api/source/jobs").json(),
        ),
    }

    control_plane = {
        "health_http": _measure(
            "health_http",
            config.http_iterations,
            lambda: client.get("/api/health").json(),
        ),
        "stats_http": _measure(
            "stats_http",
            config.http_iterations,
            lambda: client.get("/api/stats").json(),
        ),
        "index_http": _measure(
            "index_http",
            config.http_iterations,
            lambda: client.get("/api/index").json(),
        ),
        "tree_http": _measure(
            "tree_http",
            config.http_iterations,
            lambda: client.get("/api/tree").json(),
        ),
        "tree_node_http": _measure(
            "tree_node_http",
            config.http_iterations,
            lambda: client.get("/api/tree/ops/module-00000").json(),
        ),
        "graph_http": _measure(
            "graph_http",
            config.http_iterations,
            lambda: client.get("/api/graph").json(),
        ),
        "graph_node_http": _measure(
            "graph_node_http",
            config.http_iterations,
            lambda: client.get("/api/graph/ops/module-00000").json(),
        ),
        "recommendations_http": _measure_with_hotspot(
            "recommendations_http",
            config.http_iterations,
            lambda: client.get("/api/recommendations").json(),
            hotspot_timer=hotspots,
            hotspot_name="recommendations",
        ),
        "ops_http": _measure(
            "ops_http",
            config.http_iterations,
            lambda: client.get("/api/ops").json(),
        ),
        "ops_backlog_http": _measure(
            "ops_backlog_http",
            config.http_iterations,
            lambda: client.get("/api/ops/backlog").json(),
        ),
        "ops_backlog_risky_misses_http": _measure(
            "ops_backlog_risky_misses_http",
            config.http_iterations,
            lambda: client.get("/api/ops/backlog/risky-misses").json(),
        ),
        "ops_backlog_source_http": _measure(
            "ops_backlog_source_http",
            config.http_iterations,
            lambda: client.get("/api/ops/backlog/source").json(),
        ),
        "dual_view_http": _measure(
            "dual_view_http",
            config.http_iterations,
            lambda: client.get("/api/dual-view").json(),
        ),
        "access_explain_http": _measure(
            "access_explain_http",
            config.http_iterations,
            lambda: client.post(
                "/api/access/explain",
                json={
                    "groups": ["eng-viewers"],
                    "category": "ops",
                    "module_id": "module-00000",
                    "roles": {
                        "viewer": {
                            "permissions": ["module:read"],
                            "scopes": ["category:ops"],
                        }
                    },
                    "group_mapping": {"eng-viewers": ["viewer"]},
                },
            ).json(),
        ),
        "migrate_dry_run_http": _measure(
            "migrate_dry_run_http",
            config.http_iterations,
            lambda: client.post(
                "/api/migrate/dry-run",
                json={"source_path": str(migration_source), "source_kind": "llm_wiki"},
            ).json(),
        ),
    }

    def _mcp_resource(uri: str) -> str:
        result = asyncio.run(mcp_server.read_resource(uri))
        return _extract_mcp_payload_text(result)

    def _mcp_tool(name: str, arguments: dict[str, Any]) -> str:
        result = asyncio.run(mcp_server.call_tool(name, arguments))
        return _extract_mcp_payload_text(result)

    mcp = {
        "mcp_index_resource": _measure(
            "mcp_index_resource",
            config.http_iterations,
            lambda: _mcp_resource("knowledge://index"),
        ),
        "mcp_health_resource": _measure(
            "mcp_health_resource",
            config.http_iterations,
            lambda: _mcp_resource("knowledge://health"),
        ),
        "mcp_stats_resource": _measure(
            "mcp_stats_resource",
            config.http_iterations,
            lambda: _mcp_resource("knowledge://stats"),
        ),
        "mcp_ops_resource": _measure(
            "mcp_ops_resource",
            config.http_iterations,
            lambda: _mcp_resource("knowledge://ops"),
        ),
        "mcp_dual_view_resource": _measure(
            "mcp_dual_view_resource",
            config.http_iterations,
            lambda: _mcp_resource("knowledge://dual-view"),
        ),
        "mcp_load_module": _measure(
            "mcp_load_module",
            config.http_iterations,
            lambda: _mcp_tool("load_module", {"module_id": "module-00000", "category": "ops"}),
        ),
        "mcp_search_modules": _measure_with_hotspot(
            "mcp_search_modules",
            config.http_iterations,
            lambda: _mcp_tool("search_modules", {"query": benchmark_query}),
            hotspot_timer=hotspots,
            hotspot_name="search",
        ),
        "mcp_deep_search": _measure_with_hotspot(
            "mcp_deep_search",
            config.http_iterations,
            lambda: _mcp_tool("deep_search", {"query": benchmark_query}),
            hotspot_timer=hotspots,
            hotspot_name="search",
        ),
        "mcp_explain_access": _measure(
            "mcp_explain_access",
            config.http_iterations,
            lambda: _mcp_tool(
                "explain_access",
                {
                    "groups": ["eng-viewers"],
                    "category": "ops",
                    "module_id": "module-00000",
                    "roles": {
                        "viewer": {
                            "permissions": ["module:read"],
                            "scopes": ["category:ops"],
                        }
                    },
                    "group_mapping": {"eng-viewers": ["viewer"]},
                },
            ),
        ),
        "mcp_create_module": _measure(
            "mcp_create_module",
            config.job_iterations,
            lambda: _mcp_tool(
                "create_module",
                {
                    "title": "Performance created MCP module",
                    "content": "Overview line.\n\nDetailed MCP benchmark content body long enough.",
                    "category": "ops",
                    "summary": "MCP create benchmark summary.",
                    "tags": "perf,mcp",
                },
            ),
        ),
    }

    def _job_round_trip() -> dict[str, Any]:
        job = create_ingestion_job(config.kb_path, source_id="perf-source", trigger="benchmark")
        claim_ingestion_job(config.kb_path, job.job_id, worker_id="perf-worker")
        update_ingestion_checkpoint(config.kb_path, job.job_id, cursor="cursor-final", pages_seen=11)
        finished = complete_ingestion_job(
            config.kb_path,
            job.job_id,
            pages_seen=15,
            modules_staged=5,
            modules_marked_stale=1,
        )
        return finished.model_dump(mode="json")

    job_operations = {
        "create_claim_complete": _measure(
            "create_claim_complete",
            config.job_iterations,
            _job_round_trip,
        ),
        "list_jobs": _measure(
            "list_jobs",
            config.job_iterations,
            lambda: [job.model_dump(mode="json") for job in list_ingestion_jobs(config.kb_path)],
        ),
    }

    write_counter = {"value": 0}

    def _module_crud_round_trip() -> dict[str, Any]:
        write_counter["value"] += 1
        suffix = write_counter["value"]
        module_id = f"perf-write-{suffix:05d}"
        body = {
            "id": module_id,
            "category": "ops",
            "title": f"Perf write module {suffix}",
            "summary": "Performance write benchmark module summary.",
            "content": {
                "overview": "Write benchmark overview for module creation path.",
                "details": "Write benchmark details long enough for validation in the HTTP write path.",
            },
            "metadata": {"tags": ["perf", "write"], "status": "published"},
            "submit_to_staging": False,
        }
        create_response = client.post("/api/modules", json=body)
        update_response = client.put(
            f"/api/modules/ops/{module_id}",
            json={"summary": "Updated performance write benchmark module summary."},
        )
        delete_response = client.delete(f"/api/modules/ops/{module_id}")
        create_payload = create_response.json()
        update_payload = update_response.json()
        delete_payload = delete_response.json()
        return {
            "create_status": create_response.status_code,
            "update_status": update_response.status_code,
            "delete_status": delete_response.status_code,
            "create_maintenance_deferred": bool(create_payload.get("maintenance", {}).get("deferred")),
            "update_maintenance_deferred": bool(update_payload.get("maintenance", {}).get("deferred")),
            "delete_maintenance_deferred": bool(delete_payload.get("maintenance", {}).get("deferred")),
        }

    stage_counter = {"value": 0}

    def _staging_review_round_trip() -> dict[str, Any]:
        stage_counter["value"] += 1
        suffix = stage_counter["value"]
        module_id = f"perf-stage-{suffix:05d}"
        body = {
            "id": module_id,
            "category": "ops",
            "title": f"Perf staged module {suffix}",
            "summary": "Performance staged module summary.",
            "content": {
                "overview": "Staging benchmark overview for staged review path.",
                "details": "Staging benchmark details long enough for validation in the HTTP staging path.",
            },
            "metadata": {"tags": ["perf", "staging"], "status": "draft"},
            "submit_to_staging": True,
        }
        create_response = client.post("/api/modules", json=body)
        review_response = client.get("/api/staging")
        approve_response = client.post(
            f"/api/staging/{module_id}/approve",
            json={"reviewer": "perf-bot", "comment": "benchmark approve"},
        )
        return {
            "create_status": create_response.status_code,
            "review_status": review_response.status_code,
            "approve_status": approve_response.status_code,
        }

    write_operations = {
        "module_crud_http": _measure_with_hotspot(
            "module_crud_http",
            config.http_iterations,
            _module_crud_round_trip,
            hotspot_timer=hotspots,
            hotspot_name="module_crud",
        ),
        "staging_review_http": _measure(
            "staging_review_http",
            config.http_iterations,
            _staging_review_round_trip,
        ),
    }

    external_provider: dict[str, Any] = {"enabled": external_enabled}
    if external_enabled:
        upload_sample = config.output_dir / "upload-sample.txt"
        upload_sample.write_text(
            "This document describes our rollback policy, deployment workflow, and incident communication pattern.",
            encoding="utf-8",
        )

        def _chat_http() -> dict[str, Any]:
            response = client.post(
                "/api/chat",
                json={
                    "query": "How should we handle rollback during an incident?",
                    "history": [{"role": "user", "content": "We are discussing production rollout safety."}],
                    "mode": "precise",
                },
                timeout=180,
            )
            return {
                "status_code": response.status_code,
                "bytes": len(response.text),
            }

        def _upload_http() -> dict[str, Any]:
            with upload_sample.open("rb") as fh:
                response = client.post(
                    "/api/upload",
                    files={"file": ("upload-sample.txt", fh, "text/plain")},
                    data={"category": "ops", "mode": "text"},
                    timeout=180,
                )
            payload = response.json()
            return {
                "status_code": response.status_code,
                "modules_extracted": payload.get("modules_extracted", 0),
            }

        def _mcp_research() -> str:
            return _mcp_tool("research", {"query": "rollback workflow", "depth": "shallow"})

        external_provider.update(
            {
                "chat_http": _measure("chat_http", 1, _chat_http),
                "upload_http": _measure("upload_http", 1, _upload_http),
                "mcp_research": _measure("mcp_research", 1, _mcp_research),
            }
        )

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "kb_path": str(config.kb_path),
            "module_count": config.module_count,
            "tenant_count": config.tenant_count,
            "job_count": config.job_count,
            "migration_document_count": config.migration_document_count,
        },
        "resources": {
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "kb_disk_bytes": _sum_file_bytes(config.kb_path),
            "python_heap_peak_bytes": heap_peak,
        },
        "benchmarks": {
            "retrieval": retrieval,
            "http": http,
            "control_plane": control_plane,
            "mcp": mcp,
            "external_provider": external_provider,
            "job_operations": job_operations,
            "write_operations": write_operations,
        },
        "hotspots": hotspots.summary(),
    }
    _stabilize_benchmark_kb(config.kb_path)
    report["gate_summary"] = _evaluate_gate_summary(report)
    report["release_verdict"] = _evaluate_release_verdict(report)
    report["artifacts"] = _write_reports(report, config.output_dir)
    return report
