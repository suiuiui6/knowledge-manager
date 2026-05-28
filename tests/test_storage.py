import json
import pytest
from pathlib import Path
from datetime import datetime
from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata, Index
from knowledge_manager.storage import (
    save_module, load_module, delete_module, list_modules,
    save_index, load_index, rebuild_index,
    save_to_staging, list_staging, load_from_staging, approve_from_staging,
)


def make_module(id="test-module", category="general") -> Module:
    return Module(
        id=id,
        category=category,
        title="Test Module Title",
        summary="A summary of this test module for testing purposes",
        content=ModuleContent(
            overview="This is the overview of the module",
            details="These are the detailed notes about the module content",
        ),
    )


@pytest.fixture
def kb_path(tmp_path):
    return tmp_path / "kb"


@pytest.fixture
def staging_path(tmp_path):
    return tmp_path / ".staging"


def test_save_and_load_module(kb_path):
    module = make_module()
    save_module(module, kb_path)
    loaded = load_module("test-module", "general", kb_path)
    assert loaded.id == module.id
    assert loaded.title == module.title
    assert loaded.content.overview == module.content.overview


def test_save_creates_category_dir(kb_path):
    module = make_module(category="auth")
    save_module(module, kb_path)
    assert (kb_path / "auth" / "test-module.json").exists()


def test_save_is_atomic(kb_path, monkeypatch):
    # Verify no partial file left if replace fails
    import os
    module = make_module()
    original_replace = os.replace

    call_count = [0]
    def fail_replace(src, dst):
        call_count[0] += 1
        if call_count[0] == 1:
            raise OSError("simulated failure")
        return original_replace(src, dst)

    monkeypatch.setattr("knowledge_manager.storage.os.replace", fail_replace)
    with pytest.raises(OSError):
        save_module(module, kb_path)
    # No partial file should remain at final path
    assert not (kb_path / "general" / "test-module.json").exists()


def test_load_nonexistent_module(kb_path):
    result = load_module("missing", "general", kb_path)
    assert result is None


def test_delete_module(kb_path):
    module = make_module()
    save_module(module, kb_path)
    assert delete_module("test-module", "general", kb_path) is True
    assert load_module("test-module", "general", kb_path) is None


def test_delete_nonexistent_module(kb_path):
    assert delete_module("missing", "general", kb_path) is False


def test_list_modules(kb_path):
    save_module(make_module("mod-a", "cat1"), kb_path)
    save_module(make_module("mod-b", "cat1"), kb_path)
    save_module(make_module("mod-c", "cat2"), kb_path)
    modules = list_modules(kb_path)
    ids = {m.id for m in modules}
    assert ids == {"mod-a", "mod-b", "mod-c"}


def test_save_and_load_index(kb_path):
    index = Index(description="Test KB")
    save_index(index, kb_path)
    loaded = load_index(kb_path)
    assert loaded.description == "Test KB"


def test_load_index_missing(kb_path):
    result = load_index(kb_path)
    assert result is None


def test_rebuild_index(kb_path):
    save_module(make_module("mod-a", "cat1"), kb_path)
    save_module(make_module("mod-b", "cat2"), kb_path)
    index = rebuild_index(kb_path)
    assert index.stats.total_modules == 2
    assert "cat1" in index.categories
    assert "cat2" in index.categories


def test_staging_save_and_load(staging_path):
    module = make_module()
    save_to_staging(module, staging_path)
    loaded = load_from_staging("test-module", staging_path)
    assert loaded.id == module.id


def test_list_staging(staging_path):
    save_to_staging(make_module("s1"), staging_path)
    save_to_staging(make_module("s2"), staging_path)
    ids = {m.id for m in list_staging(staging_path)}
    assert ids == {"s1", "s2"}


def test_approve_from_staging(staging_path, kb_path):
    module = make_module()
    save_to_staging(module, staging_path)
    approve_from_staging("test-module", staging_path, kb_path)
    assert load_module("test-module", "general", kb_path) is not None
    assert load_from_staging("test-module", staging_path) is None
