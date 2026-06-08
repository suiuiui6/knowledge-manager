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
    record_search_event, record_load_event, load_search_events,
    compute_bayesian_priors, save_rank_model, load_rank_model,
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


def test_rebuild_index_auto_generates_category_descriptions(kb_path):
    save_module(Module(
        id="jwt", category="auth",
        title="JWT signing and validation",
        summary="Issuing and validating JSON Web Tokens with RS256",
        content=ModuleContent(overview="JWT auth overview text", details="JWT auth details for testing auto descriptions"),
        metadata=ModuleMetadata(tags=["jwt", "authentication", "rs256"]),
    ), kb_path)
    save_module(Module(
        id="oauth", category="auth",
        title="OAuth 2.0 flow",
        summary="OAuth 2.0 authorization flow setup",
        content=ModuleContent(overview="OAuth overview for desc testing", details="OAuth details for testing auto description generation in rebuild."),
        metadata=ModuleMetadata(tags=["oauth", "authentication"]),
    ), kb_path)
    save_module(Module(
        id="conn-pool", category="database",
        title="Database connection pooling",
        summary="Sizing and lifecycle of database connection pools",
        content=ModuleContent(overview="Pool overview for desc test", details="Pool details for testing auto category descriptions on rebuild index."),
        metadata=ModuleMetadata(tags=["postgres", "performance"]),
    ), kb_path)

    index = rebuild_index(kb_path)
    assert index.categories["auth"].description != ""
    assert "authentication" in index.categories["auth"].description.lower()
    assert index.categories["database"].description != ""
    assert "postgres" in index.categories["database"].description.lower()


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
    ids = [r.module.id for r in results]

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
    ids = [r.module.id for r in results]
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
    assert [r.module.id for r in lower] == [r.module.id for r in upper]


def test_search_modules_short_term_partial_match(kb_path):
    """Short terms (<5 chars) should use partial matching to find results."""
    _kb_with_signals(kb_path)

    # "auth" should match "authentication" in tags via partial match
    results = search_modules("auth", kb_path)
    assert len(results) > 0, "Short term 'auth' should return results via partial matching"

    # Should find the jwt module (has "authentication" tag)
    ids = [r.module.id for r in results]
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
    assert results[0].module.id == "auth-exact", "Exact word boundary match should rank first"



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
    ids = [r.module.id for r in results]
    assert "jwt" in ids
    assert "conn-pool" not in ids, "conn-pool is in database category, should be filtered out"


def test_search_modules_with_nonexistent_category(kb_path):
    _kb_with_signals(kb_path)
    results = search_modules("auth", kb_path, category="nonexistent")
    assert results == []


def test_search_modules_without_category_filter_returns_all(kb_path):
    _kb_with_signals(kb_path)
    results = search_modules("auth", kb_path)
    ids = [r.module.id for r in results]
    assert "jwt" in ids
    assert "conn-pool" in ids


def test_search_modules_stem_matches_long_term(kb_path):
    _kb_with_signals(kb_path)

    results = search_modules("validate", kb_path)
    ids = [r.module.id for r in results]

    assert "jwt" in ids



def test_search_modules_stem_matches_pooling_query(kb_path):
    _kb_with_signals(kb_path)

    results = search_modules("pooling", kb_path)
    ids = [r.module.id for r in results]

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
    ids = [r.module.id for r in results]

    assert ids[0] == "validate-guide"
    assert "jwt" in ids
    assert ids.index("validate-guide") < ids.index("jwt")


def test_search_modules_bm25_breaks_heuristic_ties(kb_path):
    """When two modules have same heuristic score and quality, BM25 differentiates."""
    # Two modules that both match "cache" exactly in title — same heuristic, same quality
    save_module(Module(
        id="cache-basic", category="performance",
        title="Cache strategies",
        summary="Basic caching patterns",
        content=ModuleContent(
            overview="Cache is a simple key-value store.",
            details="Cache frequently accessed data. Cache invalidation is hard. Cache everything you can. Cache makes things fast.",
        ),
        metadata=ModuleMetadata(tags=["cache", "performance"]),
    ), kb_path)
    save_module(Module(
        id="cache-advanced", category="performance",
        title="Cache strategies advanced",
        summary="Advanced caching patterns",
        content=ModuleContent(
            overview="A brief overview of cache strategies.",
            details="Short description of the module content for testing.",
        ),
        metadata=ModuleMetadata(tags=["cache"]),
    ), kb_path)

    results = search_modules("cache", kb_path)
    ids = [r.module.id for r in results]

    assert "cache-basic" in ids
    assert "cache-advanced" in ids
    # cache-basic has "cache" many times → higher BM25, should rank first
    assert ids[0] == "cache-basic", f"BM25 should favor higher term frequency, got {ids}"


def test_search_modules_graph_expansion_returns_neighbors(kb_path):
    """Graph expansion: modules referenced via related_modules appear in results."""
    save_module(Module(
        id="jwt", category="auth",
        title="JWT signing and validation",
        summary="Issuing and validating JSON Web Tokens with RS256",
        content=ModuleContent(
            overview="A JWT is a compact token signed with RS256.",
            details="Signing uses an RSA private key; gateways validate via JWKS.",
        ),
        metadata=ModuleMetadata(tags=["jwt"], related_modules=["auth/oauth-flow"]),
    ), kb_path)
    save_module(Module(
        id="oauth-flow", category="auth",
        title="OAuth 2.0 authorization code flow",
        summary="OAuth 2.0 authorization flow setup and configuration",
        content=ModuleContent(
            overview="OAuth 2.0 is an authorization framework that enables apps to obtain limited access.",
            details="The authorization code flow involves exchanging an authorization code for an access token.",
        ),
        metadata=ModuleMetadata(tags=["oauth"]),
    ), kb_path)

    results = search_modules("JWT", kb_path)
    ids = [r.module.id for r in results]

    # jwt matches directly; oauth-flow should appear via graph expansion
    assert "jwt" in ids
    assert "oauth-flow" in ids


def test_search_modules_graph_expansion_scores_lower_than_direct(kb_path):
    """Direct matches should always rank above graph-expanded neighbors."""
    save_module(Module(
        id="jwt", category="auth",
        title="JWT signing and validation",
        summary="Issuing and validating JSON Web Tokens with RS256",
        content=ModuleContent(
            overview="A JWT is a compact token signed with RS256.",
            details="Signing uses an RSA private key; gateways validate via JWKS.",
        ),
        metadata=ModuleMetadata(tags=["jwt"], related_modules=["auth/oauth-flow"]),
    ), kb_path)
    save_module(Module(
        id="oauth-flow", category="auth",
        title="OAuth 2.0 authorization code flow",
        summary="JWT is used in OAuth for access tokens",
        content=ModuleContent(
            overview="OAuth uses JWT tokens for access and refresh token exchange.",
            details="This module covers implementation patterns for JWT-based access tokens in OAuth flows.",
        ),
        metadata=ModuleMetadata(tags=["oauth", "jwt"]),
    ), kb_path)

    # Both modules match "JWT" — oauth-flow has JWT in summary (stem match)
    # jwt has "JWT" in title (exact match). jwt should also have oauth-flow as neighbor.
    results = search_modules("JWT", kb_path)
    ids = [r.module.id for r in results]

    assert ids[0] == "jwt", "Direct title match should rank above stem match + graph expansion"


def test_search_modules_graph_expansion_is_one_hop_only(kb_path):
    """Graph expansion should only be 1-hop — 2-hop neighbors should not appear."""
    # A → B → C chain; query matches only A; B should appear (1-hop), C should not (2-hop)
    save_module(Module(
        id="mod-a", category="general",
        title="Xylophone framework architecture",
        summary="The xylophone framework is for testing hop limits",
        content=ModuleContent(
            overview="Xylophone is the only entry point for this test.",
            details="Xylophone provides unique capabilities for testing graph expansion limits.",
        ),
        metadata=ModuleMetadata(tags=["xylophone", "hop-source"], related_modules=["general/mod-b"]),
    ), kb_path)
    save_module(Module(
        id="mod-b", category="general",
        title="Bridge module between layers",
        summary="Intermediate linking module for hop testing",
        content=ModuleContent(
            overview="This bridge module connects different parts of the system.",
            details="The bridge module should only appear through graph expansion, not direct matching.",
        ),
        metadata=ModuleMetadata(tags=["hop-mid"], related_modules=["general/mod-c"]),
    ), kb_path)
    save_module(Module(
        id="mod-c", category="general",
        title="Terminal module at end of path",
        summary="Final destination that should be unreachable",
        content=ModuleContent(
            overview="This terminal module should never appear in search results.",
            details="Two hops away from the entry point, this module must be excluded.",
        ),
        metadata=ModuleMetadata(tags=["hop-end"]),
    ), kb_path)

    results = search_modules("xylophone", kb_path)
    ids = [r.module.id for r in results]

    assert "mod-a" in ids, "Direct match should appear"
    assert "mod-b" in ids, "1-hop neighbor should appear via graph expansion"
    assert "mod-c" not in ids, "2-hop neighbor should NOT appear"


def test_search_modules_confidence_weights_high_above_low(kb_path):
    """High confidence modules should rank above low confidence when heuristic equal."""
    save_module(Module(
        id="conf-high", category="general",
        title="Confidence testing module",
        summary="Testing confidence weighting",
        content=ModuleContent(
            overview="This module tests high confidence ranking.",
            details="High confidence modules should appear before low confidence ones with the same score.",
        ),
        metadata=ModuleMetadata(tags=["test"], confidence="high"),
    ), kb_path)
    save_module(Module(
        id="conf-medium", category="general",
        title="Confidence testing module medium",
        summary="Testing confidence weighting",
        content=ModuleContent(
            overview="This module tests medium confidence ranking.",
            details="Medium confidence module for testing confidence weighting in search results.",
        ),
        metadata=ModuleMetadata(tags=["test"], confidence="medium"),
    ), kb_path)
    save_module(Module(
        id="conf-low", category="general",
        title="Confidence testing module low",
        summary="Testing confidence weighting",
        content=ModuleContent(
            overview="This module tests low confidence ranking.",
            details="Low confidence module for testing confidence weighting in search results.",
        ),
        metadata=ModuleMetadata(tags=["test"], confidence="low"),
    ), kb_path)

    results = search_modules("confidence", kb_path)
    ids = [r.module.id for r in results]

    assert len(ids) == 3
    assert ids[0] == "conf-high"
    assert ids[1] == "conf-medium"
    assert ids[2] == "conf-low"


def test_search_modules_matches_in_details_field(kb_path):
    """Query terms in details (but not title/tags/summary/overview) should still match."""
    save_module(Module(
        id="surface-mod", category="general",
        title="Generic module title",
        summary="A very generic summary with nothing specific",
        content=ModuleContent(
            overview="This overview is also extremely generic and says nothing interesting.",
            details="The real content is here. We use xylophone-pattern for all distributed coordination tasks.",
        ),
    ), kb_path)

    results = search_modules("xylophone", kb_path)
    assert len(results) == 1, "Should find module via details field match"
    assert results[0].module.id == "surface-mod"


# --- Telemetry & Bayesian ranking tests ---


def test_search_modules_user_synonym_expansion(kb_path):
    """User-configured synonyms should expand query terms for matching."""
    from knowledge_manager.schemas import Config

    save_module(Module(
        id="jwt", category="auth",
        title="JWT signing and validation",
        summary="Issuing and validating JSON Web Tokens with RS256",
        content=ModuleContent(
            overview="JWT is used for stateless authentication in our system.",
            details="Tokens are signed with RS256 and expire after 24 hours.",
        ),
    ), kb_path)

    # Query "bearer" — module has no "bearer" in any field, so no match without synonym
    results_no_syn = search_modules("bearer", kb_path)
    assert len(results_no_syn) == 0, "Without synonym, 'bearer' should not match JWT module"

    cfg = Config(synonyms={"bearer": ["jwt"]})
    cfg_path = kb_path / "config.json"
    cfg_path.write_text(cfg.model_dump_json())

    results = search_modules("bearer", kb_path)
    assert len(results) > 0, "With user synonym bearer→jwt, should find JWT module"
    assert results[0].module.id == "jwt"


def test_search_modules_weighted_graph_edges(kb_path):
    """Graph edges with weight annotations should rank higher-weight neighbors first."""
    # Module A matches the query; B and C are neighbors with different weights
    save_module(Module(
        id="mod-a", category="general",
        title="Xylophone query module",
        summary="This is the entry module for weighted graph edge testing",
        content=ModuleContent(
            overview="Xylophone is the primary entry point for this weighted edge test.",
            details="Xylophone testing details for weighted graph expansion edge testing.",
        ),
        metadata=ModuleMetadata(tags=["xylophone"], related_modules=["general/mod-b:0.9", "general/mod-c:0.1"]),
    ), kb_path)
    save_module(Module(
        id="mod-b", category="general",
        title="High weight neighbor module",
        summary="This module has a high edge weight from mod-a",
        content=ModuleContent(
            overview="High weight module should rank above low weight module.",
            details="Testing weighted graph edges — this module should appear before mod-c.",
        ),
    ), kb_path)
    save_module(Module(
        id="mod-c", category="general",
        title="Low weight neighbor module",
        summary="This module has a low edge weight from mod-a",
        content=ModuleContent(
            overview="Low weight module should rank below high weight module.",
            details="Testing weighted graph edges — this module should appear after mod-b.",
        ),
    ), kb_path)

    results = search_modules("xylophone", kb_path)
    ids = [r.module.id for r in results]

    assert "mod-a" in ids, "Direct match should appear"
    assert "mod-b" in ids, "High-weight neighbor should appear"
    assert "mod-c" in ids, "Low-weight neighbor should appear"
    # High-weight neighbor should rank before low-weight neighbor
    assert ids.index("mod-b") < ids.index("mod-c"), \
        f"High-weight neighbor mod-b should rank before low-weight mod-c, got {ids}"


# --- Intent classification tests ---


def test_classify_intent_detects_how_to():
    from knowledge_manager.storage import _classify_intent
    assert _classify_intent("how to configure JWT signing") == "how-to"
    assert _classify_intent("how do I set up OAuth flow") == "how-to"
    assert _classify_intent("guide for database migration") == "how-to"
    assert _classify_intent("implement caching pattern") == "how-to"


def test_classify_intent_detects_decision_record():
    from knowledge_manager.storage import _classify_intent
    assert _classify_intent("why did we choose RS256") == "decision-record"
    assert _classify_intent("tradeoff between Postgres and MySQL") == "decision-record"
    assert _classify_intent("architecture decision for microservices") == "decision-record"
    assert _classify_intent("ADR for authentication protocol") == "decision-record"


def test_classify_intent_detects_reference():
    from knowledge_manager.storage import _classify_intent
    assert _classify_intent("what is the JWT signing algorithm") == "reference"
    assert _classify_intent("API endpoint configuration") == "reference"
    assert _classify_intent("database schema definition") == "reference"


def test_classify_intent_defaults_to_general():
    from knowledge_manager.storage import _classify_intent
    assert _classify_intent("JWT authentication") == "general"
    assert _classify_intent("Postgres connection pool") == "general"
    assert _classify_intent("rate limiting") == "general"


def test_search_modules_how_to_intent_boosts_examples(kb_path):
    """How-to intent should boost modules with rich examples content."""
    save_module(Module(
        id="with-examples", category="general",
        title="Xylophone configuration",
        summary="Configuring the xylophone module",
        content=ModuleContent(
            overview="Configuration overview for the xylophone module.",
            details="Step-by-step xylophone configuration details for testing.",
            examples="Real xylophone configuration examples. Here is configure xylophone in practice.",
        ),
    ), kb_path)
    save_module(Module(
        id="no-examples", category="general",
        title="Xylophone configuration reference",
        summary="Reference for xylophone configuration",
        content=ModuleContent(
            overview="Xylophone is configured via environment variables.",
            details="This module describes xylophone configuration at a high reference level.",
            examples="",
        ),
    ), kb_path)

    results = search_modules("how to configure xylophone", kb_path)
    ids = [r.module.id for r in results]
    assert ids[0] == "with-examples", f"How-to intent should boost examples, got {ids}"


def test_search_modules_decision_intent_boosts_details(kb_path):
    """Decision-record intent should boost modules with rich details and caveats."""
    save_module(Module(
        id="deep-details", category="general",
        title="Xylophone architecture decision",
        summary="Why we chose xylophone for our architecture",
        content=ModuleContent(
            overview="Architecture decision overview for xylophone.",
            details="Comprehensive analysis of xylophone architecture. We evaluated three options. The tradeoff between latency and throughput was key. PostgreSQL was chosen because it offers the best balance.",
            caveats="This xylophone decision assumes single-region deployment. Multi-region adds significant complexity.",
        ),
    ), kb_path)
    save_module(Module(
        id="shallow-details", category="general",
        title="Xylophone architecture reference",
        summary="Architecture reference overview for xylophone",
        content=ModuleContent(
            overview="Reference material for xylophone architecture details.",
            details="Xylophone is a reference architecture pattern for distributed systems.",
            caveats="",
        ),
    ), kb_path)

    results = search_modules("why xylophone architecture decision tradeoff", kb_path)
    ids = [r.module.id for r in results]
    assert ids[0] == "deep-details", f"Decision intent should boost details+caveats, got {ids}"


def test_search_modules_boost_ids_promotes_recently_loaded(kb_path):
    """Modules in boost_ids should rank higher than similarly-scored modules."""
    save_module(Module(
        id="mod-a", category="general",
        title="Database connection troubleshooting",
        summary="How to troubleshoot database connections",
        content=ModuleContent(
            overview="Troubleshooting database connections is important.",
            details="Database connection troubleshooting details for testing boost parameter.",
        ),
    ), kb_path)
    save_module(Module(
        id="mod-b", category="general",
        title="Database connection pooling",
        summary="Database connection pool configuration",
        content=ModuleContent(
            overview="Connection pooling for databases is essential.",
            details="Database connection pooling configuration for testing boost parameter.",
        ),
    ), kb_path)

    # Without boost, both match "database connection" equally in title
    results = search_modules("database connection", kb_path)
    ids = [r.module.id for r in results]

    # With boost on mod-b, it should rank first
    results_boosted = search_modules("database connection", kb_path, boost_ids=["mod-b"])
    boosted_ids = [r.module.id for r in results_boosted]
    assert boosted_ids[0] == "mod-b", f"Boost should promote mod-b, got {boosted_ids}"


def test_record_search_event_writes_jsonl(kb_path):
    record_search_event("JWT authentication", ["auth/jwt", "auth/oauth-flow"], kb_path)
    events_file = kb_path / ".telemetry" / "search_events.jsonl"
    assert events_file.exists()
    lines = events_file.read_text().strip().split("\n")
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["type"] == "search"
    assert event["query_hash"] is not None
    assert len(event["query_hash"]) == 64  # SHA256 hex
    assert event["query_hash"] != "JWT authentication"  # hashed, not raw
    assert "query_terms" in event
    assert len(event["query_terms"]) > 0  # stemmed terms stored for Bayesian
    assert event["results_shown"] == ["auth/jwt", "auth/oauth-flow"]


def test_record_load_event_writes_jsonl(kb_path):
    record_load_event("jwt", "auth", kb_path)
    events_file = kb_path / ".telemetry" / "search_events.jsonl"
    assert events_file.exists()
    lines = events_file.read_text().strip().split("\n")
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["type"] == "load"
    assert event["module_id"] == "jwt"
    assert event["category"] == "auth"


def test_load_search_events_returns_all_events(kb_path):
    record_search_event("query one", ["mod-a"], kb_path)
    record_load_event("mod-a", "cat", kb_path)
    record_search_event("query two", ["mod-b"], kb_path)
    events = load_search_events(kb_path)
    assert len(events) == 3


def test_load_search_events_empty_dir_returns_empty(kb_path):
    events = load_search_events(kb_path)
    assert events == []


def test_record_search_event_skips_when_disabled(kb_path):
    from knowledge_manager.schemas import Config
    kb_path.mkdir(parents=True, exist_ok=True)
    cfg = Config(telemetry={"enabled": False})
    cfg_path = kb_path / "config.json"
    cfg_path.write_text(cfg.model_dump_json())
    record_search_event("test", ["mod"], kb_path, cfg)
    assert not (kb_path / ".telemetry" / "search_events.jsonl").exists()


def test_compute_bayesian_priors_basic(kb_path):
    # Simulate: "jwt auth" search → jwt loaded; "oauth flow" search → oauth loaded
    record_search_event("jwt auth", ["auth/jwt", "auth/oauth"], kb_path)
    record_load_event("jwt", "auth", kb_path)
    record_search_event("oauth flow", ["auth/oauth"], kb_path)
    record_load_event("oauth", "auth", kb_path)

    priors = compute_bayesian_priors(kb_path)

    # P(jwt | "jwt") should be > 0
    assert "jwt" in priors, "Should have prior for query term 'jwt'"
    assert "auth/jwt" in priors["jwt"], "Module jwt should appear in term 'jwt' prior"
    assert priors["jwt"]["auth/jwt"] > 0


def test_compute_bayesian_priors_empty_returns_empty(kb_path):
    priors = compute_bayesian_priors(kb_path)
    assert priors == {}


def test_compute_bayesian_priors_smoothing(kb_path):
    # One search that showed 2 modules, only 1 of which was loaded
    record_search_event("smoothing test query", ["auth/jwt", "auth/other"], kb_path)
    record_load_event("jwt", "auth", kb_path)

    priors = compute_bayesian_priors(kb_path)

    # The stemmed query terms should have priors
    assert "smooth" in priors  # stem of "smoothing"
    assert "test" in priors
    assert "queri" in priors  # stem of "query"
    # jwt was loaded → higher probability
    assert priors["smooth"]["auth/jwt"] > 0
    # Smoothing ensures probability is < 1.0 (other module gets some mass too)
    assert priors["smooth"]["auth/jwt"] < 1.0
    assert priors["smooth"]["auth/other"] > 0  # gets smoothing mass


def test_save_and_load_rank_model(kb_path):
    priors = {"test": {"auth/jwt": 0.75, "auth/other": 0.25}}
    save_rank_model(priors, event_count=10, kb_path=kb_path)
    loaded = load_rank_model(kb_path, expected_event_count=10)
    assert loaded is not None
    assert "test" in loaded
    assert loaded["test"]["auth/jwt"] == 0.75


def test_load_rank_model_stale_when_events_changed(kb_path):
    priors = {"test": {"auth/jwt": 0.5}}
    save_rank_model(priors, event_count=5, kb_path=kb_path)
    loaded = load_rank_model(kb_path, expected_event_count=10)
    assert loaded is None  # events changed, cache is stale


def test_load_rank_model_missing_file_returns_none(kb_path):
    assert load_rank_model(kb_path, expected_event_count=0) is None


def test_compute_bayesian_priors_caches_to_disk(kb_path):
    record_search_event("test query", ["auth/jwt"], kb_path)
    record_load_event("jwt", "auth", kb_path)

    # First call computes and saves
    priors1 = compute_bayesian_priors(kb_path)
    # Second call should load from cache (same event count)
    priors2 = compute_bayesian_priors(kb_path)

    assert priors1 == priors2
    # Verify cache file was written
    assert (kb_path / ".telemetry" / "rank_model.json").exists()
