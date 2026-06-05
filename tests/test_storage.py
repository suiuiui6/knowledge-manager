import json
import pytest
from pathlib import Path
from datetime import datetime
from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata, Index
from knowledge_manager.storage import (
    save_module, load_module, delete_module, list_modules,
    save_index, load_index, rebuild_index,
    save_to_staging, list_staging, load_from_staging, approve_from_staging,
    _stem, search_modules,
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


def _kb_with_signals(kb_path: Path) -> None:
    save_module(Module(
        id="jwt", category="auth",
        title="JWT signing and validation",
        summary="Issuing and validating JSON Web Tokens with RS256",
        content=ModuleContent(
            overview="A JWT is a compact token signed with RS256.",
            details="Signing uses an RSA private key; gateways validate via JWKS.",
        ),
        metadata=ModuleMetadata(tags=["jwt", "authentication", "rs256"]),
    ), kb_path)
    save_module(Module(
        id="conn-pool", category="database",
        title="Database connection pooling",
        summary="Sizing and lifecycle of database connection pools for Postgres",
        content=ModuleContent(
            overview="Pool keeps connections so requests skip the TCP+TLS+auth handshake.",
            details="Right-size the pool; Postgres prefers a small number of busy connections.",
        ),
        metadata=ModuleMetadata(tags=["database", "postgres", "performance"]),
    ), kb_path)


def test_search_modules_empty_query_returns_empty(kb_path):
    _kb_with_signals(kb_path)
    assert search_modules("", kb_path) == []
    assert search_modules("   ", kb_path) == []


def test_search_modules_no_match_returns_empty(kb_path):
    _kb_with_signals(kb_path)
    assert search_modules("kubernetes ingress", kb_path) == []


def test_search_modules_uses_word_boundaries(kb_path):
    # "auth" is a short term (<5 chars), so it uses both word-boundary and partial matching.
    # conn-pool has "auth" as standalone word in overview ("TCP+TLS+auth") → word boundary match
    # jwt has "authentication" tag → partial match (lower score)
    # Both should be found, but conn-pool should rank higher due to word boundary match
    _kb_with_signals(kb_path)
    results = search_modules("auth", kb_path)
    ids = [m.id for m in results]

    # Both modules should be found
    assert "conn-pool" in ids, "Should find conn-pool via word boundary match"
    assert "jwt" in ids, "Should find jwt via partial match on 'authentication' tag"

    # conn-pool should rank higher (word boundary match > partial match)
    assert ids.index("conn-pool") < ids.index("jwt"), "Word boundary match should rank higher than partial match"


def test_search_modules_ranks_title_above_overview(kb_path):
    # Query "signing auth" — jwt matches "signing" in title (weight 5);
    # conn-pool matches "auth" in overview (weight 1). jwt should rank first.
    _kb_with_signals(kb_path)
    results = search_modules("signing auth", kb_path)
    ids = [m.id for m in results]
    assert ids[0] == "jwt"
    assert ids == ["jwt", "conn-pool"]


def test_search_modules_filters_out_zero_score(kb_path):
    # Query that matches nothing should return empty even when modules exist
    _kb_with_signals(kb_path)
    assert search_modules("nonexistentterm", kb_path) == []


def test_search_modules_case_insensitive(kb_path):
    _kb_with_signals(kb_path)
    lower = search_modules("jwt", kb_path)
    upper = search_modules("JWT", kb_path)
    assert [m.id for m in lower] == [m.id for m in upper]


def test_search_modules_short_term_partial_match(kb_path):
    """Short terms (<5 chars) should use partial matching to find results."""
    _kb_with_signals(kb_path)

    # "auth" should match "authentication" in tags via partial match
    results = search_modules("auth", kb_path)
    assert len(results) > 0, "Short term 'auth' should return results via partial matching"

    # Should find the jwt module (has "authentication" tag)
    ids = [m.id for m in results]
    assert "jwt" in ids, "Should find jwt module with 'authentication' tag"


def test_search_modules_short_term_lower_score(kb_path):
    """Partial matches should score lower than word-boundary matches."""
    _kb_with_signals(kb_path)

    # Create a module with exact "auth" word boundary match
    exact_match = Module(
        id="auth-exact",
        category="auth",
        title="Auth System",
        summary="Authentication and authorization system",
        content=ModuleContent(
            overview="Auth system overview",
            details="Auth system handles authentication"
        ),
        metadata=ModuleMetadata(tags=["auth", "security"])
    )
    save_module(exact_match, kb_path)

    results = search_modules("auth", kb_path)

    # The exact match should rank higher than partial matches
    assert results[0].id == "auth-exact", "Exact word boundary match should rank first"



def test_stem_reduces_morphological_variants():
    assert _stem("validation") == "valid"
    assert _stem("validating") == "valid"
    assert _stem("validate") == "valid"
    assert _stem("running") == "run"
    assert _stem("connections") == "connect"
    assert _stem("SIGNING") == "sign"



def test_search_modules_with_category_filter(kb_path):
    _kb_with_signals(kb_path)
    results = search_modules("auth", kb_path, category="auth")
    ids = [m.id for m in results]
    assert "jwt" in ids
    assert "conn-pool" not in ids, "conn-pool is in database category, should be filtered out"


def test_search_modules_with_nonexistent_category(kb_path):
    _kb_with_signals(kb_path)
    results = search_modules("auth", kb_path, category="nonexistent")
    assert results == []


def test_search_modules_without_category_filter_returns_all(kb_path):
    _kb_with_signals(kb_path)
    results = search_modules("auth", kb_path)
    ids = [m.id for m in results]
    assert "jwt" in ids
    assert "conn-pool" in ids


def test_search_modules_stem_matches_long_term(kb_path):
    _kb_with_signals(kb_path)

    results = search_modules("validate", kb_path)
    ids = [m.id for m in results]

    assert "jwt" in ids



def test_search_modules_stem_matches_pooling_query(kb_path):
    _kb_with_signals(kb_path)

    results = search_modules("pooling", kb_path)
    ids = [m.id for m in results]

    assert "conn-pool" in ids



def test_search_modules_exact_ranks_above_stem(kb_path):
    _kb_with_signals(kb_path)
    save_module(Module(
        id="validate-guide", category="auth",
        title="Validate requests correctly",
        summary="Guidance for outbound request authentication",
        content=ModuleContent(
            overview="Clients must sign each gateway request.",
            details="Use the shared secret to sign each outbound request body.",
        ),
        metadata=ModuleMetadata(tags=["gateway"]),
    ), kb_path)

    results = search_modules("validate", kb_path)
    ids = [m.id for m in results]

    assert ids[0] == "validate-guide"
    assert "jwt" in ids
    assert ids.index("validate-guide") < ids.index("jwt")
