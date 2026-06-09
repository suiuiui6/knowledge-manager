"""Tests for Phase 4D: Knowledge Marketplace client."""

import json
import pytest
from pathlib import Path

from knowledge_manager.schemas import (
    InstallPlan,
    MarketplaceIndex,
    MarketplaceModule,
    Module,
    ModuleContent,
    ModuleMetadata,
)
from knowledge_manager.marketplace import (
    check_publish_gate,
    fetch_marketplace_index,
    resolve_install_plan,
    sanitize_module_text,
    search_marketplace,
)


def make_marketplace_index() -> MarketplaceIndex:
    """Build a minimal marketplace index for testing."""
    mod_a = MarketplaceModule(
        id="oauth2",
        category="auth",
        title="OAuth 2.0 Best Practices",
        summary="Security-focused OAuth 2.0 implementation guide",
        tags=["auth", "security", "oauth"],
        version="2.1.0",
        author="community",
        confidence="high",
        downloads=847,
        rating=4.7,
        ratings_count=23,
    )
    mod_b = MarketplaceModule(
        id="rate-limiting",
        category="api",
        title="API Rate Limiting Patterns",
        summary="Common rate limiting implementation patterns",
        tags=["api", "security", "rate-limit"],
        version="1.0.0",
        author="community",
        confidence="high",
        downloads=234,
        rating=4.2,
        ratings_count=11,
        dependencies=["auth/oauth2"],
    )
    return MarketplaceIndex(
        modules={
            "auth/oauth2": mod_a,
            "api/rate-limiting": mod_b,
        }
    )


def test_marketplace_module_schema():
    """MarketplaceModule should validate."""
    mod = MarketplaceModule(
        id="test", category="auth", title="Test", summary="A test module",
    )
    assert mod.version == "1.0.0"
    assert mod.author == "community"
    assert mod.downloads == 0


def test_marketplace_index_schema():
    """MarketplaceIndex should validate."""
    idx = MarketplaceIndex()
    assert idx.version == "1.0"
    assert idx.modules == {}


def test_install_plan_schema():
    """InstallPlan should track modules and dependencies."""
    plan = InstallPlan(target_category="auth")
    assert plan.modules == []
    assert plan.dependencies_installed == []
    assert plan.target_category == "auth"


def test_fetch_marketplace_index_local(tmp_path):
    """fetch_marketplace_index should load from a local directory."""
    mp_dir = tmp_path / "marketplace"
    mp_dir.mkdir()
    idx = make_marketplace_index()
    (mp_dir / "index.json").write_text(idx.model_dump_json(indent=2))

    result = fetch_marketplace_index(str(mp_dir))
    assert result is not None
    assert "auth/oauth2" in result.modules
    assert result.modules["auth/oauth2"].title == "OAuth 2.0 Best Practices"


def test_fetch_marketplace_index_missing(tmp_path):
    """fetch_marketplace_index should return None for missing index."""
    mp_dir = tmp_path / "nonexistent"
    assert fetch_marketplace_index(str(mp_dir)) is None


def test_search_marketplace():
    """search_marketplace should find modules by keyword."""
    idx = make_marketplace_index()
    results = search_marketplace("oauth", idx)
    assert len(results) == 1
    assert results[0].id == "oauth2"

    results = search_marketplace("security", idx)
    assert len(results) == 2  # Both modules have 'security' tag


def test_search_marketplace_no_match():
    """search_marketplace should return empty for no match."""
    idx = make_marketplace_index()
    assert search_marketplace("nonexistent", idx) == []


def test_resolve_install_plan_simple():
    """resolve_install_plan should find a module without dependencies."""
    idx = make_marketplace_index()
    plan = resolve_install_plan("auth/oauth2", idx)
    assert len(plan.modules) == 1
    assert plan.modules[0].id == "oauth2"
    assert plan.target_category == "auth"


def test_resolve_install_plan_with_deps():
    """resolve_install_plan should recursively resolve dependencies."""
    idx = make_marketplace_index()
    plan = resolve_install_plan("api/rate-limiting", idx)
    assert len(plan.modules) == 2  # rate-limiting + oauth2 dep
    assert "auth/oauth2" in plan.dependencies_installed
    assert plan.target_category == "api"


def test_resolve_install_plan_not_found():
    """resolve_install_plan should raise ValueError for unknown modules."""
    idx = make_marketplace_index()
    with pytest.raises(ValueError, match="not found"):
        resolve_install_plan("nonexistent/module", idx)


def test_sanitize_module_text():
    """sanitize_module_text should replace patterns with <redacted>."""
    text = "Contact admin@company.com or visit https://internal.company.com/docs"
    patterns = [r"\b[a-zA-Z0-9._%+-]+@company\.com\b", r"https://internal\.company\.com\S*"]
    result = sanitize_module_text(text, patterns)
    assert "admin@company.com" not in result
    assert "internal.company.com" not in result
    assert "<redacted>" in result


def test_sanitize_module_text_empty_patterns():
    """sanitize_module_text with empty patterns should return unchanged text."""
    text = "Some text with nothing to hide"
    assert sanitize_module_text(text, []) == text


def test_check_publish_gate_valid():
    """check_publish_gate should return empty list for valid publishable module."""
    mod = Module(
        id="test", category="auth", title="Test Module Title",
        summary="A summary for the test module",
        content=ModuleContent(
            overview="Overview that is long enough",
            details="Detailed content that is long enough to validate",
        ),
        metadata=ModuleMetadata(confidence="high", status="published"),
    )
    issues = check_publish_gate(mod.model_dump_json())
    assert issues == []


def test_check_publish_gate_low_confidence():
    """check_publish_gate should flag low confidence."""
    mod = Module(
        id="test", category="auth", title="Test Module Title",
        summary="A summary for the test module",
        content=ModuleContent(
            overview="Overview that is long enough",
            details="Detailed content that is long enough to validate",
        ),
        metadata=ModuleMetadata(confidence="low", status="published"),
    )
    issues = check_publish_gate(mod.model_dump_json())
    assert len(issues) > 0


def test_check_publish_gate_draft_status():
    """check_publish_gate should flag non-published status."""
    mod = Module(
        id="test", category="auth", title="Test Module Title",
        summary="A summary for the test module",
        content=ModuleContent(
            overview="Overview that is long enough",
            details="Detailed content that is long enough to validate",
        ),
        metadata=ModuleMetadata(confidence="high", status="draft"),
    )
    issues = check_publish_gate(mod.model_dump_json())
    assert len(issues) > 0


def test_check_publish_gate_invalid_json():
    """check_publish_gate should flag invalid JSON."""
    issues = check_publish_gate("not valid json")
    assert len(issues) > 0
