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


# ── Phase 4B: namespace isolation ──


def test_cache_namespace_isolation():
    """Modules with same ID in different namespaces should not collide."""
    cache = ModuleCache(max_size=10)
    mod_a = make_module("same-id")
    mod_b = make_module("same-id")
    mod_b.title = "Different Title for NS2"

    cache.put(mod_a, namespace="ns1")
    cache.put(mod_b, namespace="ns2")

    # Same ID, different namespace → both stored
    result1 = cache.get("same-id", namespace="ns1")
    result2 = cache.get("same-id", namespace="ns2")
    assert result1 is not None
    assert result2 is not None
    assert result1.title == "Test Module Title"
    assert result2.title == "Different Title for NS2"


def test_cache_namespace_miss():
    """get with wrong namespace should return None."""
    cache = ModuleCache(max_size=10)
    cache.put(make_module("mod-a"), namespace="ns1")
    assert cache.get("mod-a", namespace="ns2") is None


def test_cache_namespace_invalidate():
    """invalidate should only remove from the specified namespace."""
    cache = ModuleCache(max_size=10)
    cache.put(make_module("mod-a"), namespace="ns1")
    cache.put(make_module("mod-a"), namespace="ns2")

    cache.invalidate("mod-a", namespace="ns1")
    assert cache.get("mod-a", namespace="ns1") is None
    assert cache.get("mod-a", namespace="ns2") is not None
