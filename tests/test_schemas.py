# tests/test_schemas.py
import pytest
from pydantic import ValidationError
from knowledge_manager.schemas import ModuleContent, ModuleMetadata


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


def test_module_metadata_invalid_confidence():
    with pytest.raises(ValidationError):
        ModuleMetadata(confidence="invalid")
