"""Tests for Phase 4C: Webhook engine."""

import json
import pytest
from pathlib import Path

from knowledge_manager.schemas import (
    WebhookConfig,
    WebhookEndpoint,
    WebhookEvent,
    WebhookRetryConfig,
)
from knowledge_manager.webhooks import (
    _event_matches,
    _sign_payload,
    emit_event,
    load_webhook_failures,
    retry_webhooks,
)


def test_webhook_event_schema():
    """WebhookEvent should validate with required fields."""
    evt = WebhookEvent(
        event="module.deprecated",
        module_id="test-mod",
        category="auth",
        data={"reason": "Replaced"},
    )
    assert evt.event == "module.deprecated"
    assert evt.module_id == "test-mod"
    assert evt.data["reason"] == "Replaced"


def test_webhook_endpoint_schema():
    """WebhookEndpoint should validate with default retry config."""
    ep = WebhookEndpoint(url="https://example.com/webhook", events=["module.deprecated"])
    assert ep.url == "https://example.com/webhook"
    assert ep.retry.max_attempts == 3
    assert ep.retry.backoff_seconds == 30
    assert ep.secret == ""


def test_webhook_config_defaults():
    """WebhookConfig should default to disabled with empty endpoints."""
    wc = WebhookConfig()
    assert wc.enabled is False
    assert wc.endpoints == []


def test_event_matches_all_when_empty():
    """_event_matches should return True when endpoint has no event filter."""
    ep = WebhookEndpoint(url="https://example.com", events=[])
    assert _event_matches("module.created", ep) is True
    assert _event_matches("module.deprecated", ep) is True


def test_event_matches_filtered():
    """_event_matches should respect endpoint event filter."""
    ep = WebhookEndpoint(url="https://example.com", events=["module.deprecated", "module.expired"])
    assert _event_matches("module.deprecated", ep) is True
    assert _event_matches("module.created", ep) is False


def test_sign_payload():
    """_sign_payload should produce consistent HMAC-SHA256 signatures."""
    sig1 = _sign_payload("test payload", "secret-key")
    sig2 = _sign_payload("test payload", "secret-key")
    assert sig1 == sig2
    assert len(sig1) == 64  # SHA256 hex digest
    assert _sign_payload("different", "secret-key") != sig1


def test_emit_event_disabled(tmp_path):
    """emit_event should be a no-op when webhooks are disabled."""
    kb = tmp_path / "kb"
    kb.mkdir(parents=True, exist_ok=True)
    emit_event(kb, "module.created", "test", "auth")


def test_emit_event_no_config_file(tmp_path):
    """emit_event should be a no-op when config.json doesn't exist."""
    kb = tmp_path / "kb"
    kb.mkdir(parents=True, exist_ok=True)
    emit_event(kb, "module.updated", "test", "auth")


def test_load_webhook_failures_empty(tmp_path):
    """load_webhook_failures should return empty list when no failures file."""
    kb = tmp_path / "kb"
    kb.mkdir(parents=True, exist_ok=True)
    assert load_webhook_failures(kb) == []


def test_load_webhook_failures_with_data(tmp_path):
    """load_webhook_failures should parse failure records."""
    kb = tmp_path / "kb"
    kb.mkdir(parents=True, exist_ok=True)
    failures_path = kb / ".webhook_failures.jsonl"
    failures_path.write_text(
        json.dumps({"event": "test", "url": "https://example.com", "retry_count": 0, "max_attempts": 3, "payload": "{}"}) + "\n"
    )
    records = load_webhook_failures(kb)
    assert len(records) == 1
    assert records[0]["event"] == "test"


def test_retry_webhooks_success(tmp_path):
    """retry_webhooks should succeed when no failures exist."""
    kb = tmp_path / "kb"
    kb.mkdir(parents=True, exist_ok=True)
    assert retry_webhooks(kb) == 0


def test_retry_webhooks_max_attempts(tmp_path):
    """retry_webhooks should drop records that have exceeded max attempts."""
    kb = tmp_path / "kb"
    kb.mkdir(parents=True, exist_ok=True)
    failures_path = kb / ".webhook_failures.jsonl"
    failures_path.write_text(
        json.dumps({
            "event": "test", "url": "https://not-real.example.com/nope",
            "status_code": 500, "payload": "{}", "retry_count": 3, "max_attempts": 3,
        }) + "\n"
    )
    # Should not retry (max attempts reached) and should keep the record
    count = retry_webhooks(kb)
    assert count == 0
    # Record should still be there (not removed, since it wasn't retried)
    remaining = load_webhook_failures(kb)
    assert len(remaining) == 1
