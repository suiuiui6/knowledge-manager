import pytest
from knowledge_manager.schemas import Module, ModuleContent
from knowledge_manager.cache import ModuleCache


def make_module(id="mod-a") -> Module:
    return Module(
        id=id, category="general", title="Test Module Title",
        summary="A summary of this test module for testing purposes",
        content=ModuleContent(
            overview="This is the overview of the module",
            details="These are the detailed notes about the module content",
        ),
    )


def test_cache_put_and_get():
    cache = ModuleCache(max_size=10)
    module = make_module()
    cache.put(module)
    result = cache.get("mod-a")
    assert result is not None
    assert result.id == "mod-a"


def test_cache_miss_returns_none():
    cache = ModuleCache(max_size=10)
    assert cache.get("missing") is None


def test_cache_evicts_lru():
    cache = ModuleCache(max_size=3)
    for i in range(3):
        cache.put(make_module(f"mod-{i}"))
    # Access mod-0 to make it recently used
    cache.get("mod-0")
    # Add a 4th item — mod-1 should be evicted (LRU)
    cache.put(make_module("mod-3"))
    assert cache.get("mod-1") is None
    assert cache.get("mod-0") is not None
    assert cache.get("mod-3") is not None


def test_cache_invalidate():
    cache = ModuleCache(max_size=10)
    cache.put(make_module())
    cache.invalidate("mod-a")
    assert cache.get("mod-a") is None


def test_cache_clear():
    cache = ModuleCache(max_size=10)
    cache.put(make_module("mod-a"))
    cache.put(make_module("mod-b"))
    cache.clear()
    assert cache.get("mod-a") is None
    assert cache.get("mod-b") is None


def test_cache_disabled():
    cache = ModuleCache(max_size=10, enabled=False)
    cache.put(make_module())
    assert cache.get("mod-a") is None


def test_cache_size():
    cache = ModuleCache(max_size=10)
    cache.put(make_module("mod-a"))
    cache.put(make_module("mod-b"))
    assert cache.size() == 2
