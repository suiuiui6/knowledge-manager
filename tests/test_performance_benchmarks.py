import json
import tracemalloc
from pathlib import Path

from knowledge_manager.performance_benchmarks import (
    BenchmarkConfig,
    _extract_mcp_payload_text,
    _stabilize_benchmark_kb,
    _warm_benchmark_runtime,
    evaluate_matrix_summary,
    run_enterprise_benchmark,
)


def test_benchmark_report_includes_hotspot_breakdown(tmp_path):
    result = run_enterprise_benchmark(
        BenchmarkConfig(
            kb_path=tmp_path / "kb",
            output_dir=tmp_path / "reports",
            module_count=16,
            tenant_count=2,
            job_count=6,
            search_iterations=1,
            http_iterations=1,
            job_iterations=1,
            top_k=3,
        )
    )

    assert "hotspots" in result
    assert set(result["hotspots"]) >= {
        "search",
        "module_crud",
        "recommendations",
        "admin_dashboard",
    }
    for hotspot_name in ("search", "module_crud", "recommendations", "admin_dashboard"):
        hotspot = result["hotspots"][hotspot_name]
        assert hotspot["count"] >= 1
        assert hotspot["mean_ms"] >= 0.0
        assert hotspot["max_ms"] >= hotspot["mean_ms"]


def test_benchmark_records_errors_and_resource_sections(tmp_path):
    result = run_enterprise_benchmark(
        BenchmarkConfig(
            kb_path=tmp_path / "kb",
            output_dir=tmp_path / "reports",
            module_count=12,
            tenant_count=2,
            job_count=6,
            search_iterations=1,
            http_iterations=1,
            job_iterations=1,
            top_k=3,
        )
    )

    assert "resources" in result
    assert "benchmarks" in result
    assert "external_provider" in result["benchmarks"]
    assert "enabled" in result["benchmarks"]["external_provider"]
    assert "kb_disk_bytes" in result["resources"]
    assert "python_heap_peak_bytes" in result["resources"]


def test_run_enterprise_benchmark_emits_core_sections_and_reports(tmp_path):
    output_dir = tmp_path / "reports"
    config = BenchmarkConfig(
        kb_path=tmp_path / "kb",
        output_dir=output_dir,
        module_count=24,
        tenant_count=4,
        job_count=12,
        search_iterations=2,
        http_iterations=2,
        job_iterations=2,
        top_k=5,
    )

    result = run_enterprise_benchmark(config)

    assert result["dataset"]["module_count"] == 24
    assert result["dataset"]["tenant_count"] == 4
    assert result["dataset"]["job_count"] == 12
    assert "retrieval" in result["benchmarks"]
    assert "http" in result["benchmarks"]
    assert "job_operations" in result["benchmarks"]
    assert "control_plane" in result["benchmarks"]
    assert "mcp" in result["benchmarks"]
    assert "external_provider" in result["benchmarks"]
    assert "write_operations" in result["benchmarks"]
    assert "search_lexical" in result["benchmarks"]["retrieval"]
    assert "search_http" in result["benchmarks"]["http"]
    assert "create_claim_complete" in result["benchmarks"]["job_operations"]
    assert "health_http" in result["benchmarks"]["control_plane"]
    assert "migrate_dry_run_http" in result["benchmarks"]["control_plane"]
    assert "access_explain_http" in result["benchmarks"]["control_plane"]
    assert "module_crud_http" in result["benchmarks"]["write_operations"]
    assert "staging_review_http" in result["benchmarks"]["write_operations"]
    assert "mcp_search_modules" in result["benchmarks"]["mcp"]
    assert "mcp_load_module" in result["benchmarks"]["mcp"]
    assert "enabled" in result["benchmarks"]["external_provider"]
    assert "resources" in result
    assert "kb_disk_bytes" in result["resources"]
    assert "python_heap_peak_bytes" in result["resources"]
    assert Path(result["artifacts"]["json"]).exists()
    assert Path(result["artifacts"]["markdown"]).exists()


def test_benchmark_summary_exposes_enterprise_gate_verdict(tmp_path):
    result = run_enterprise_benchmark(
        BenchmarkConfig(
            kb_path=tmp_path / "kb",
            output_dir=tmp_path / "reports",
            module_count=20,
            tenant_count=4,
            job_count=8,
            search_iterations=1,
            http_iterations=1,
            job_iterations=1,
            top_k=5,
        )
    )

    assert "gate_summary" in result
    assert "search_http" in result["gate_summary"]
    assert "recommendations_http" in result["gate_summary"]
    assert "admin_dashboard_http" in result["gate_summary"]
    assert "release_verdict" in result
    assert "ready_for_production" in result["release_verdict"]
    assert "failed_gates" in result["release_verdict"]


def test_benchmark_release_verdict_exposes_hotspot_blockers_and_sections(tmp_path):
    result = run_enterprise_benchmark(
        BenchmarkConfig(
            kb_path=tmp_path / "kb",
            output_dir=tmp_path / "reports",
            module_count=20,
            tenant_count=4,
            job_count=8,
            search_iterations=1,
            http_iterations=1,
            job_iterations=1,
            top_k=5,
        )
    )

    verdict = result["release_verdict"]
    assert "blockers" in verdict
    assert "hotspot_sections" in verdict
    assert set(verdict["hotspot_sections"]) >= {"search", "module_crud", "recommendations", "admin_dashboard"}

    markdown = Path(result["artifacts"]["markdown"]).read_text(encoding="utf-8")
    assert "## Hotspots" in markdown


def test_stabilize_benchmark_kb_refreshes_indexes_and_running_job_leases(tmp_path):
    from datetime import datetime, timedelta, timezone

    from knowledge_manager.ingestion_jobs import create_ingestion_job, load_ingestion_job
    from knowledge_manager.recommendation_index import load_recommendation_index
    from knowledge_manager.schemas import Index, Module, ModuleContent
    from knowledge_manager.search_projection import load_search_projection
    from knowledge_manager.storage import save_index, save_module

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="benchmark stabilize"), kb)
    save_module(
        Module(
            id="rollback-guide",
            category="ops",
            title="Rollback Guide",
            summary="Rollback guidance.",
            content=ModuleContent(
                overview="Rollback overview.",
                details="Rollback details long enough for validation.",
            ),
        ),
        kb,
        defer_noncritical=False,
    )

    job = create_ingestion_job(kb, source_id="source-1", trigger="benchmark")
    stale = load_ingestion_job(kb, job.job_id).model_copy(
        update={
            "status": "running",
            "stage": "running",
            "worker_id": "seed-worker",
            "lease_expires_at": datetime.now(timezone.utc) - timedelta(seconds=5),
            "heartbeat_at": datetime.now(timezone.utc) - timedelta(seconds=5),
        }
    )
    (kb / ".jobs" / "ingestion" / f"{job.job_id}.json").write_text(
        stale.model_dump_json(indent=2),
        encoding="utf-8",
    )

    _stabilize_benchmark_kb(kb)

    projection = load_search_projection(kb)
    recommendation_index = load_recommendation_index(kb)
    refreshed_job = load_ingestion_job(kb, job.job_id)

    assert projection is not None
    assert "ops/rollback-guide" in projection["documents"]
    assert recommendation_index is not None
    assert "ops/rollback-guide" in recommendation_index["modules"]
    assert refreshed_job is not None
    assert refreshed_job.lease_expires_at is not None
    assert refreshed_job.lease_expires_at > datetime.now(timezone.utc)


def test_extract_mcp_payload_text_reads_text_segments_without_list_repr():
    class FakeTextContent:
        def __init__(self, text: str):
            self.text = text

        def __repr__(self) -> str:
            raise AssertionError("text extraction should not stringify the wrapper list")

    payload = ([FakeTextContent("alpha"), FakeTextContent("beta")], {"result": "alpha\nbeta"})

    assert _extract_mcp_payload_text(payload) == "alpha\nbeta"


def test_warm_benchmark_runtime_primes_admin_snapshot(tmp_path):
    from fastapi.testclient import TestClient

    from knowledge_manager.http_server import create_app
    from knowledge_manager.mcp_server import create_server
    from knowledge_manager.performance_benchmarks import (
        _seed_config,
        _seed_jobs,
        _seed_modules,
        _seed_sources_and_events,
    )

    config = BenchmarkConfig(
        kb_path=tmp_path / "kb",
        output_dir=tmp_path / "reports",
        module_count=24,
        tenant_count=4,
        job_count=12,
        migration_document_count=20,
        search_iterations=1,
        http_iterations=1,
        job_iterations=1,
        top_k=5,
    )
    _seed_modules(config)
    _seed_jobs(config)
    _seed_sources_and_events(config)
    _seed_config(config)

    client = TestClient(create_app(config.kb_path))
    server = create_server(config.kb_path)

    _warm_benchmark_runtime(config, client, server, "rollback tenant incident")

    snapshot_path = config.kb_path / ".cache" / "views" / "admin_dashboard.snapshot.json"
    assert snapshot_path.exists()
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert payload["payload"]["review_backlog"][0]["module_id"] == "pending-review"


def test_run_enterprise_benchmark_disables_tracemalloc_before_timed_sections(tmp_path, monkeypatch):
    import knowledge_manager.performance_benchmarks as perf

    seen_measure_states: list[bool] = []

    def fake_measure(name, iterations, fn):
        seen_measure_states.append(tracemalloc.is_tracing())
        return {
            "name": name,
            "iterations": iterations,
            "mean_ms": 0.0,
            "median_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
            "min_ms": 0.0,
            "max_ms": 0.0,
            "throughput_per_sec": 0.0,
            "last_result_size": 0,
        }

    monkeypatch.setattr(perf, "_measure", fake_measure)
    monkeypatch.setattr(perf, "_measure_with_hotspot", lambda name, iterations, fn, hotspot_timer=None, hotspot_name=None: fake_measure(name, iterations, fn))

    result = perf.run_enterprise_benchmark(
        BenchmarkConfig(
            kb_path=tmp_path / "kb",
            output_dir=tmp_path / "reports",
            module_count=12,
            tenant_count=2,
            job_count=6,
            migration_document_count=10,
            search_iterations=1,
            http_iterations=1,
            job_iterations=1,
            top_k=3,
        )
    )

    assert seen_measure_states
    assert all(state is False for state in seen_measure_states)
    assert result["resources"]["python_heap_peak_bytes"] >= 0


def test_evaluate_matrix_summary_requires_all_configured_scales(tmp_path):
    summary_path = tmp_path / "matrix-summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "xs": {"release_verdict": {"ready_for_production": True}},
                "s": {"release_verdict": {"ready_for_production": False}},
                "m": {"release_verdict": {"ready_for_production": True}},
            }
        ),
        encoding="utf-8",
    )

    verdict = evaluate_matrix_summary(summary_path, ["xs", "s", "m"])

    assert verdict["required_scales"] == ["xs", "s", "m"]
    assert verdict["failed_scales"] == ["s"]
    assert verdict["ready_for_production"] is False


def test_evaluate_matrix_summary_flags_missing_required_scale(tmp_path):
    summary_path = tmp_path / "matrix-summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "xs": {"release_verdict": {"ready_for_production": True}},
                "s": {"release_verdict": {"ready_for_production": True}},
            }
        ),
        encoding="utf-8",
    )

    verdict = evaluate_matrix_summary(summary_path, ["xs", "s", "m"])

    assert verdict["failed_scales"] == ["m"]
    assert verdict["ready_for_production"] is False
