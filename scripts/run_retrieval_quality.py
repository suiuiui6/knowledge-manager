from __future__ import annotations

import argparse
import json
import hashlib
import platform
import subprocess
from datetime import datetime, timezone
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

        tenant = (
            TenantContext(tenant_id=tenant_id, workspace_id=workspace_id)
            if tenant_id or workspace_id
            else None
        )
        return search_modules(query, args.kb_path, limit=top_k, tenant=tenant)

    report = evaluate_golden_set(load_golden_set(args.golden_set), search)
    report.update(
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "platform": platform.platform(),
            "commit": subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
            ).stdout.strip(),
            "golden_set_sha256": hashlib.sha256(args.golden_set.read_bytes()).hexdigest(),
            "kb_path": str(args.kb_path.resolve()),
            "quality_scope": "checked-in sample corpus; lexical retrieval; no external LLM",
            "ok": report["tenant_leakage_cases"] == 0
            and report["mean_recall_at_k"] >= 0.8
            and report["mean_mrr"] >= 0.8
            and report["mean_ndcg_at_k"] >= 0.8
            and report["abstention_accuracy"] == 1.0,
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
