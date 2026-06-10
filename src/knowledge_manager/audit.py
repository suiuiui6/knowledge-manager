import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("knowledge_manager.audit")

AUDIT_OPERATIONS = {
    "module.create", "module.update", "module.delete",
    "module.approve", "module.reject",
    "staging.submit", "staging.approve", "staging.reject",
    "config.update", "plugin.install", "plugin.uninstall",
    "auth.login", "auth.logout",
}


class AuditEvent:
    def __init__(self, user: str, operation: str, module_id: str = "",
                 category: str = "", details: str = ""):
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.user = user
        self.operation = operation
        self.module_id = module_id
        self.category = category
        self.details = details

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "user": self.user,
            "operation": self.operation,
            "module_id": self.module_id,
            "category": self.category,
            "details": self.details,
        }


def log_audit_event(kb_path: Path, event: AuditEvent) -> None:
    if event.operation not in AUDIT_OPERATIONS:
        logger.warning("Unknown audit operation: %s", event.operation)

    audit_dir = kb_path / ".audit"
    audit_dir.mkdir(exist_ok=True)

    log_path = audit_dir / "audit.jsonl"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")


def read_audit_log(kb_path: Path, since: Optional[str] = None,
                   user: Optional[str] = None,
                   operation: Optional[str] = None) -> list[dict]:
    log_path = kb_path / ".audit" / "audit.jsonl"
    if not log_path.exists():
        return []

    events = []
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue

            if since and e.get("timestamp", "") < since:
                continue
            if user and e.get("user", "") != user:
                continue
            if operation and e.get("operation", "") != operation:
                continue

            events.append(e)

    return events


def generate_compliance_report(kb_path: Path, period: str = "",
                                fmt: str = "json") -> str:
    events = read_audit_log(kb_path)

    if period:
        events = [e for e in events if e.get("timestamp", "").startswith(period)]

    ops_count: dict[str, int] = {}
    users: set[str] = set()
    modules_touched: set[str] = set()

    for e in events:
        op = e.get("operation", "unknown")
        ops_count[op] = ops_count.get(op, 0) + 1
        if e.get("user"):
            users.add(e["user"])
        if e.get("module_id"):
            modules_touched.add(e["module_id"])

    report = {
        "period": period or "all",
        "total_events": len(events),
        "unique_users": len(users),
        "modules_touched": len(modules_touched),
        "operations": ops_count,
        "events": events if fmt == "json" else None,
    }

    if fmt == "json":
        return json.dumps(report, indent=2, ensure_ascii=False)

    lines = [
        f"Compliance Report ({report['period']})",
        f"Total events: {report['total_events']}",
        f"Unique users: {report['unique_users']}",
        f"Modules touched: {report['modules_touched']}",
        "",
        "Operations breakdown:",
    ]
    for op, count in sorted(ops_count.items()):
        lines.append(f"  {op}: {count}")

    return "\n".join(lines)
