"""Webhook engine for Phase 4C: structured event dispatch, HMAC signing, retry."""

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from knowledge_manager.schemas import WebhookConfig, WebhookEndpoint, WebhookEvent

_logger = logging.getLogger("knowledge_manager.webhooks")

FAILURES_FILE = ".webhook_failures.jsonl"


def _load_webhook_config(kb_path: Path) -> WebhookConfig | None:
    """Load webhook config from KB config, returning None if disabled or absent."""
    from knowledge_manager.storage import _load_config_safe
    cfg = _load_config_safe(kb_path)
    if cfg is None or not cfg.webhooks.enabled or not cfg.webhooks.endpoints:
        return None
    return cfg.webhooks


def _sign_payload(payload: str, secret: str) -> str:
    """Compute HMAC-SHA256 signature for a payload string."""
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _event_matches(event_name: str, endpoint: WebhookEndpoint) -> bool:
    """Check if an event matches the endpoint's subscription. Empty list = all events."""
    if not endpoint.events:
        return True
    return event_name in endpoint.events


def emit_event(
    kb_path: Path,
    event_name: str,
    module_id: str,
    category: str,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    """Emit a webhook event to all matching endpoints. Non-blocking — failures are logged."""
    wc = _load_webhook_config(kb_path)
    if wc is None:
        return

    event = WebhookEvent(
        event=event_name,
        kb_path=str(kb_path),
        module_id=module_id,
        category=category,
        data=data or {},
    )

    payload = event.model_dump_json()
    import asyncio

    for endpoint in wc.endpoints:
        if not _event_matches(event_name, endpoint):
            continue

        headers = dict(endpoint.headers)
        if endpoint.secret:
            headers["X-KM-Signature"] = f"sha256={_sign_payload(payload, endpoint.secret)}"

        try:
            import httpx
            # Fire-and-forget: try once synchronously, log failure if it fails
            try:
                resp = httpx.post(
                    endpoint.url,
                    content=payload,
                    headers=headers,
                    timeout=httpx.Timeout(10.0),
                )
                if resp.status_code >= 400:
                    _log_failure(kb_path, event_name, endpoint, payload, resp.status_code)
            except Exception:
                _log_failure(kb_path, event_name, endpoint, payload, 0)
        except ImportError:
            _logger.warning("httpx not installed, webhook skipped")
            return


def _log_failure(
    kb_path: Path,
    event_name: str,
    endpoint: WebhookEndpoint,
    payload: str,
    status_code: int,
) -> None:
    """Append a failure record to .webhook_failures.jsonl."""
    failures_path = kb_path / FAILURES_FILE
    failures_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event_name,
        "url": str(endpoint.url),
        "status_code": status_code,
        "payload": payload,
        "retry_count": 0,
        "max_attempts": endpoint.retry.max_attempts,
    }
    with open(failures_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_webhook_failures(kb_path: Path) -> List[dict]:
    """Load webhook failure records from disk."""
    failures_path = kb_path / FAILURES_FILE
    if not failures_path.exists():
        return []
    records = []
    for line in failures_path.read_text(encoding="utf-8").strip().split("\n"):
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records


def retry_webhooks(kb_path: Path) -> int:
    """Retry failed webhook deliveries. Returns count of successfully retried events."""
    records = load_webhook_failures(kb_path)
    if not records:
        return 0

    import httpx
    retried = 0
    remaining: list[dict] = []

    for record in records:
        if record["retry_count"] >= record["max_attempts"]:
            remaining.append(record)
            continue

        try:
            resp = httpx.post(
                record["url"],
                content=record["payload"],
                timeout=httpx.Timeout(10.0),
            )
            if resp.status_code < 400:
                retried += 1
                continue
            record["retry_count"] += 1
            record["status_code"] = resp.status_code
        except Exception:
            record["retry_count"] += 1
            record["status_code"] = 0

        remaining.append(record)

    # Rewrite failures file with remaining records
    if remaining:
        failures_path = kb_path / FAILURES_FILE
        with open(failures_path, "w", encoding="utf-8") as f:
            for r in remaining:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    else:
        # All succeeded — remove the failures file
        failures_path = kb_path / FAILURES_FILE
        if failures_path.exists():
            failures_path.unlink()

    return retried
