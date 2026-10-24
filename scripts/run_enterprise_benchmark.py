from __future__ import annotations

import argparse
import faulthandler
from pathlib import Path

from knowledge_manager.performance_benchmarks import BenchmarkConfig, run_enterprise_benchmark


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kb-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--module-count", type=int, default=1000)
    parser.add_argument("--tenant-count", type=int, default=10)
    parser.add_argument("--job-count", type=int, default=500)
    parser.add_argument("--migration-document-count", type=int, default=250)
    parser.add_argument("--iterations", type=int, default=20)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "benchmark-stacks.log").open("w", encoding="utf-8") as stacks:
        faulthandler.dump_traceback_later(120, repeat=True, file=stacks)
        try:
            report = run_enterprise_benchmark(
                BenchmarkConfig(
                    kb_path=args.kb_path,
                    output_dir=args.output_dir,
                    module_count=args.module_count,
                    tenant_count=args.tenant_count,
                    job_count=args.job_count,
                    migration_document_count=args.migration_document_count,
                    search_iterations=args.iterations,
                    http_iterations=args.iterations,
                    job_iterations=args.iterations,
                )
            )
        finally:
            faulthandler.cancel_dump_traceback_later()
    return 0 if report["release_verdict"]["ready_for_production"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
