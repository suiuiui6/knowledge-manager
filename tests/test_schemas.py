# tests/test_schemas.py
from datetime import timezone

import pytest
from pydantic import ValidationError
from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata


def test_module_content_valid():
    content = ModuleContent(
        overview="This is an overview",
        details="These are detailed technical notes"
    )
    assert content.overview == "This is an overview"
    assert content.details == "These are detailed technical notes"
    assert content.examples == ""
    assert content.references == ""
    assert content.caveats == ""


def test_module_content_with_all_fields():
    content = ModuleContent(
        overview="Overview text",
        details="Details text with more content",
        examples="Example code",
        references="https://example.com",
        caveats="Known issues"
    )
    assert content.examples == "Example code"
    assert content.references == "https://example.com"
    assert content.caveats == "Known issues"


def test_module_content_missing_required_fields():
    with pytest.raises(ValidationError):
        ModuleContent(overview="Only overview")


def test_module_content_too_short():
    with pytest.raises(ValidationError):
        ModuleContent(overview="Short", details="Also short")


def test_module_metadata_defaults():
    metadata = ModuleMetadata()
    assert metadata.tags == []
    assert metadata.related_modules == []
    assert metadata.confidence == "medium"
    assert metadata.source == ""


def test_module_metadata_with_values():
    metadata = ModuleMetadata(
        tags=["auth", "security"],
        related_modules=["auth/jwt-tokens"],
        confidence="high",
        source="team documentation"
    )
    assert metadata.tags == ["auth", "security"]
    assert metadata.related_modules == ["auth/jwt-tokens"]
    assert metadata.confidence == "high"
    assert metadata.source == "team documentation"


def test_default_timestamps_are_timezone_aware():
    module = Module(
        id="auth-jwt",
        category="auth",
        title="JWT authentication module",
        summary="Summary text that is long enough for validation.",
        content=ModuleContent(
            overview="Overview text that is long enough",
            details="Detailed notes that are definitely long enough to pass validation",
        ),
    )
    index = Index()

    assert module.created_at.tzinfo == timezone.utc
    assert module.updated_at.tzinfo == timezone.utc
    assert index.updated_at.tzinfo == timezone.utc
    assert index.stats.last_updated.tzinfo == timezone.utc


def test_extraction_config_auto_categorize_default():
    from knowledge_manager.schemas import ExtractionConfig
    cfg = ExtractionConfig()
    assert cfg.auto_categorize is False


def test_extraction_config_auto_categorize_explicit():
    from knowledge_manager.schemas import ExtractionConfig
    cfg = ExtractionConfig(auto_categorize=True)
    assert cfg.auto_categorize is True
