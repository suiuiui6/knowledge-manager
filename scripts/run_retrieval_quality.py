from __future__ import annotations

import argparse
import json
from pathlib import Path

from knowledge_manager.retrieval_eval import evaluate_golden_set, load_golden_set
from knowledge_manager.storage import search_modules


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kb-path", type=Path, required=True)
    parser.add_argument("--golden-set", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    def search(query: str, *, tenant_id: str = "", workspace_id: str = "", top_k: int = 10):
        from knowledge_manager.tenancy import TenantContext

        tenant = TenantContext(tenant_id=tenant_id, workspace_id=workspace_id) if tenant_id or workspace_id else None
        return search_modules(query, args.kb_path, limit=top_k, tenant=tenant)

    report = evaluate_golden_set(load_golden_set(args.golden_set), search)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["tenant_leakage_cases"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
