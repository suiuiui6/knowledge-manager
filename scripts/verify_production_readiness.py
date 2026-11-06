import argparse
import json
from pathlib import Path

from knowledge_manager.performance_benchmarks import build_production_readiness_verdict


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kb-path", required=True)
    parser.add_argument("--matrix-summary", required=True)
    args = parser.parse_args()

    verdict = build_production_readiness_verdict(
        Path(args.kb_path),
        Path(args.matrix_summary),
    )
    print(json.dumps(verdict, ensure_ascii=False, indent=2))
    return 0 if verdict["ready_for_production"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
