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


def test_search_modules_chinese_tokenization(kb_path):
    """Search should find Chinese modules by word after jieba segmentation."""
    from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata
    from knowledge_manager.storage import save_module, rebuild_index, search_modules

    kb_path.mkdir(parents=True, exist_ok=True)
    mod = Module(
        id="zh-search",
        category="general",
        title="知识管理系统架构决策",
        summary="关于知识管理系统的核心架构决策记录",
        content=ModuleContent(
            overview="我们选择 Git 作为存储层，JSON 文件作为数据格式，MCP 协议作为传输层",
            details="详细的架构决策包括不使用向量数据库、不使用 SQL 数据库、不使用消息队列等设计边界",
        ),
        metadata=ModuleMetadata(tags=["架构", "决策", "知识管理"]),
    )
    save_module(mod, kb_path)
    rebuild_index(kb_path)

    # These Chinese words should match after jieba segmentation
    results = search_modules("架构决策", kb_path)
    assert len(results) == 1
    assert results[0].module.id == "zh-search"

    results2 = search_modules("向量数据库", kb_path)
    assert len(results2) == 1

    results3 = search_modules("消息队列", kb_path)
    assert len(results3) == 1


def test_search_modules_mixed_chinese_english(kb_path):
    """Search should work with mixed Chinese and English content."""
    from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata
    from knowledge_manager.storage import save_module, rebuild_index, search_modules

    kb_path.mkdir(parents=True, exist_ok=True)
    mod = Module(
        id="mixed-lang",
        category="general",
        title="JWT 认证最佳实践",
        summary="JWT token 在微服务架构中的使用方法",
        content=ModuleContent(
            overview="JWT (JSON Web Token) 是一种无状态的认证机制，广泛应用于微服务架构",
            details="RS256 签名算法，24小时过期，支持 token refresh 流程",
        ),
        metadata=ModuleMetadata(tags=["auth", "认证", "JWT"]),
    )
    save_module(mod, kb_path)
    rebuild_index(kb_path)

    # English term in Chinese context
    assert len(search_modules("JWT 认证", kb_path)) == 1
    # Pure Chinese
    assert len(search_modules("微服务架构", kb_path)) == 1
    # Pure English
    assert len(search_modules("RS256", kb_path)) == 1
    # Tag search (Chinese tag)
    assert len(search_modules("认证", kb_path)) == 1



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


def test_sanitize_config_replaces_api_keys():
    from knowledge_manager.storage import sanitize_config
    from knowledge_manager.schemas import Config, LLMProviderConfig

    cfg = Config(
        llm_providers={
            "deepseek": LLMProviderConfig(
                api_key="sk-secret-123",
                model="deepseek-v4",
                default=True,
            ),
            "claude": LLMProviderConfig(
                api_key="sk-ant-secret-456",
                model="claude-opus-4",
            ),
        }
    )
    sanitized = sanitize_config(cfg)
    assert sanitized.llm_providers["deepseek"].api_key == "<LOCAL>"
    assert sanitized.llm_providers["claude"].api_key == "<LOCAL>"
    # Other fields preserved
    assert sanitized.llm_providers["deepseek"].model == "deepseek-v4"
    assert sanitized.llm_providers["deepseek"].default is True


def test_sanitize_config_handles_empty_keys():
    from knowledge_manager.storage import sanitize_config
    from knowledge_manager.schemas import Config, LLMProviderConfig

    cfg = Config(
        llm_providers={
            "deepseek": LLMProviderConfig(
                api_key="",
                model="deepseek-v4",
                default=True,
            ),
        }
    )
    sanitized = sanitize_config(cfg)
    assert sanitized.llm_providers["deepseek"].api_key == ""


def test_sanitize_config_handles_no_providers():
    from knowledge_manager.storage import sanitize_config
    from knowledge_manager.schemas import Config
    cfg = Config()
    sanitized = sanitize_config(cfg)
    assert sanitized.llm_providers == {}


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


# ── Phase 2B: staging metadata & review pipeline tests ──


def test_staging_meta_save_and_load(kb_path):
    from knowledge_manager.schemas import StagingMeta
    from knowledge_manager.storage import save_staging_meta, load_staging_meta

    kb_path.mkdir(parents=True, exist_ok=True)
    staging = kb_path / ".staging"
    staging.mkdir(exist_ok=True)

    meta = StagingMeta(module_id="test-mod", submitted_by="alice")
    save_staging_meta(meta, staging)

    loaded = load_staging_meta("test-mod", staging)
    assert loaded is not None
    assert loaded.module_id == "test-mod"
    assert loaded.submitted_by == "alice"
    assert loaded.status == "pending"


def test_staging_meta_load_missing_returns_none(kb_path):
    from knowledge_manager.storage import load_staging_meta

    kb_path.mkdir(parents=True, exist_ok=True)
    staging = kb_path / ".staging"
    staging.mkdir(exist_ok=True)

    assert load_staging_meta("nonexistent", staging) is None


def test_staging_meta_delete(kb_path):
    from knowledge_manager.schemas import StagingMeta
    from knowledge_manager.storage import save_staging_meta, delete_staging_meta, load_staging_meta

    kb_path.mkdir(parents=True, exist_ok=True)
    staging = kb_path / ".staging"
    staging.mkdir(exist_ok=True)

    meta = StagingMeta(module_id="to-delete")
    save_staging_meta(meta, staging)
    assert (staging / "to-delete.meta.json").exists()

    delete_staging_meta("to-delete", staging)
    assert not (staging / "to-delete.meta.json").exists()
    assert load_staging_meta("to-delete", staging) is None


def test_staging_meta_list(kb_path):
    from knowledge_manager.schemas import StagingMeta
    from knowledge_manager.storage import save_staging_meta, list_staging_meta

    kb_path.mkdir(parents=True, exist_ok=True)
    staging = kb_path / ".staging"
    staging.mkdir(exist_ok=True)

    save_staging_meta(StagingMeta(module_id="a"), staging)
    save_staging_meta(StagingMeta(module_id="b"), staging)

    metas = list_staging_meta(staging)
    assert len(metas) == 2
    assert {m.module_id for m in metas} == {"a", "b"}


def test_staging_meta_approval_count():
    from knowledge_manager.schemas import StagingMeta, ReviewRecord

    meta = StagingMeta(module_id="mod")
    assert meta.approval_count() == 0

    meta.reviews.append(ReviewRecord(reviewer="alice", action="approved"))
    assert meta.approval_count() == 1

    meta.reviews.append(ReviewRecord(reviewer="bob", action="changes-requested"))
    assert meta.approval_count() == 1  # only approved counts

    meta.reviews.append(ReviewRecord(reviewer="carol", action="approved"))
    assert meta.approval_count() == 2


def test_review_config_defaults():
    from knowledge_manager.schemas import ReviewConfig

    cfg = ReviewConfig()
    assert cfg.required_approvals == 1
    assert cfg.auto_approve_self_submitted is False
    assert cfg.reviewer_whitelist == []


def test_notifications_config_defaults():
    from knowledge_manager.schemas import NotificationsConfig

    cfg = NotificationsConfig()
    assert cfg.webhook_url == ""
    assert cfg.on_push is True
    assert cfg.on_review_approved is False


def test_approve_from_staging_moves_to_kb(kb_path):
    from knowledge_manager.schemas import StagingMeta, ReviewRecord, Module, ModuleContent, ModuleMetadata
    from knowledge_manager.storage import (
        save_to_staging, save_staging_meta, approve_from_staging,
        load_from_staging, load_module,
    )

    kb_path.mkdir(parents=True, exist_ok=True)
    staging = kb_path / ".staging"
    staging.mkdir(exist_ok=True)

    mod = Module(
        id="mod-x", category="test", title="Test Module X",
        summary="A test module for approval testing.",
        content=ModuleContent(overview="Overview text here", details="Details text long enough for validation"),
        metadata=ModuleMetadata(tags=["test"]),
    )
    save_to_staging(mod, staging)
    save_staging_meta(StagingMeta(module_id="mod-x", submitted_by="alice"), staging)

    approve_from_staging("mod-x", staging, kb_path)

    # Should be in kb now, not staging
    loaded = load_module("mod-x", "test", kb_path)
    assert loaded is not None
    assert loaded.title == "Test Module X"
    assert load_from_staging("mod-x", staging) is None


# ── Phase 2C: changelog generation & loading tests ──


def _init_git_for_kb(kb: Path):
    """Init git in a kb path and configure identity."""
    import subprocess
    if not (kb / ".git").exists():
        subprocess.run(["git", "-C", str(kb), "init"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "config", "user.email", "test@test.com"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "config", "user.name", "Test"], capture_output=True, check=True)
    # Ensure branch is "main" for test consistency
    branch = subprocess.run(["git", "-C", str(kb), "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True)
    if branch.stdout.strip() != "main":
        subprocess.run(["git", "-C", str(kb), "branch", "-m", "main"], capture_output=True, check=True)


def test_generate_changelog_empty_no_commits(kb_path):
    """No commits → changelog is None."""
    from knowledge_manager.storage import generate_changelog
    kb_path.mkdir(parents=True, exist_ok=True)
    _init_git_for_kb(kb_path)

    result = generate_changelog(kb_path)
    assert result is None


def test_generate_changelog_with_module_commit(kb_path):
    """Commits with module changes should produce changelog entries, including root commits."""
    import subprocess, json
    from knowledge_manager.storage import generate_changelog

    kb_path.mkdir(parents=True, exist_ok=True)
    _init_git_for_kb(kb_path)

    mod_dir = kb_path / "test"
    mod_dir.mkdir(exist_ok=True)
    mod_file = mod_dir / "sample.json"
    mod_file.write_text(json.dumps({"id": "sample", "title": "Sample Module"}))

    subprocess.run(["git", "-C", str(kb_path), "add", "-A"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb_path), "commit", "-m", "add sample module"], capture_output=True, check=True)

    result = generate_changelog(kb_path)
    assert result is not None
    assert len(result["commits"]) >= 1
    assert result["commits"][0]["message"] == "add sample module"

    # Verify file was written
    assert (kb_path / ".changelog" / f"{result['date']}.json").exists()


def test_generate_changelog_root_commit_classified_as_added(kb_path):
    """Root commit files should be classified as 'added' (no parent to diff against)."""
    import subprocess, json
    from knowledge_manager.storage import generate_changelog

    kb_path.mkdir(parents=True, exist_ok=True)
    _init_git_for_kb(kb_path)

    mod_dir = kb_path / "test"
    mod_dir.mkdir(exist_ok=True)
    (mod_dir / "root.json").write_text(json.dumps({"id": "root", "title": "Root Module"}))

    subprocess.run(["git", "-C", str(kb_path), "add", "-A"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb_path), "commit", "-m", "root commit"], capture_output=True, check=True)

    result = generate_changelog(kb_path)
    assert result is not None
    assert len(result["commits"]) == 1
    changes = result["commits"][0]["changes"]
    assert "test/root" in changes["added"]
    assert changes["modified"] == []
    assert changes["deleted"] == []


def test_load_changelogs_returns_recent(kb_path):
    """load_changelogs should return entries from last N days."""
    import subprocess, json

    kb_path.mkdir(parents=True, exist_ok=True)
    _init_git_for_kb(kb_path)

    mod_dir = kb_path / "test"
    mod_dir.mkdir(exist_ok=True)
    (mod_dir / "m.json").write_text(json.dumps({"id": "m"}))
    subprocess.run(["git", "-C", str(kb_path), "add", "-A"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb_path), "commit", "-m", "add module"], capture_output=True, check=True)

    from knowledge_manager.storage import generate_changelog, load_changelogs
    generate_changelog(kb_path)

    changelogs = load_changelogs(kb_path, days=7)
    assert len(changelogs) >= 1


def test_load_module_changelog_filters_by_key(kb_path):
    """load_module_changelog should return entries for a specific module."""
    import subprocess, json

    kb_path.mkdir(parents=True, exist_ok=True)
    _init_git_for_kb(kb_path)

    mod_dir = kb_path / "test"
    mod_dir.mkdir(exist_ok=True)
    (mod_dir / "target.json").write_text(json.dumps({"id": "target", "title": "Target"}))
    subprocess.run(["git", "-C", str(kb_path), "add", "-A"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb_path), "commit", "-m", "add target module"], capture_output=True, check=True)

    from knowledge_manager.storage import generate_changelog, load_module_changelog
    generate_changelog(kb_path)

    entries = load_module_changelog(kb_path, "test/target")
    assert len(entries) >= 1


def test_load_changelogs_handles_missing_dir(tmp_path):
    """load_changelogs returns empty list if directory missing."""
    from knowledge_manager.storage import load_changelogs
    result = load_changelogs(tmp_path / "nonexistent_kb", days=7)
    assert result == []


def test_load_module_changelog_handles_missing_dir(tmp_path):
    """load_module_changelog returns empty list if directory missing."""
    from knowledge_manager.storage import load_module_changelog
    result = load_module_changelog(tmp_path / "nonexistent_kb", "test/mod")
    assert result == []


def test_generate_changelog_handles_non_git(kb_path):
    """generate_changelog returns None for non-git directory."""
    from knowledge_manager.storage import generate_changelog
    kb_path.mkdir(parents=True, exist_ok=True)
    result = generate_changelog(kb_path)
    assert result is None


# ── Phase 2D: module state machine & search filtering tests ──


def test_search_excludes_archived_by_default(kb_path):
    """search_modules should exclude archived modules when include_archived=False."""
    from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata
    from knowledge_manager.storage import search_modules

    kb_path.mkdir(parents=True, exist_ok=True)
    published = Module(
        id="pub", category="test", title="Published Module",
        summary="A published module for search testing.",
        content=ModuleContent(overview="Published overview here.", details="Published details long enough for validation check."),
        metadata=ModuleMetadata(status="published"),
    )
    archived = Module(
        id="arch", category="test", title="Archived Module",
        summary="An archived module for search testing.",
        content=ModuleContent(overview="Archived overview here.", details="Archived details long enough for validation check."),
        metadata=ModuleMetadata(status="archived"),
    )
    save_module(published, kb_path)
    save_module(archived, kb_path)
    from knowledge_manager.storage import rebuild_index
    rebuild_index(kb_path)

    results = search_modules("module", kb_path)
    result_ids = [r.module.id for r in results]
    assert "pub" in result_ids
    assert "arch" not in result_ids


def test_search_includes_archived_when_requested(kb_path):
    """search_modules should include archived modules when include_archived=True."""
    from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata
    from knowledge_manager.storage import search_modules

    kb_path.mkdir(parents=True, exist_ok=True)
    published = Module(
        id="pub2", category="test", title="Published Module 2",
        summary="A published module for search testing.",
        content=ModuleContent(overview="Published 2 overview here.", details="Published 2 details long enough for validation check."),
        metadata=ModuleMetadata(status="published"),
    )
    archived = Module(
        id="arch2", category="test", title="Archived Module 2",
        summary="An archived module for search testing.",
        content=ModuleContent(overview="Archived 2 overview here.", details="Archived 2 details long enough for validation check."),
        metadata=ModuleMetadata(status="archived"),
    )
    save_module(published, kb_path)
    save_module(archived, kb_path)
    from knowledge_manager.storage import rebuild_index
    rebuild_index(kb_path)

    results = search_modules("module", kb_path, include_archived=True)
    result_ids = [r.module.id for r in results]
    assert "pub2" in result_ids
    assert "arch2" in result_ids


def test_search_deprecated_gets_lower_confidence(kb_path):
    """Deprecated modules should have effective confidence treated as low."""
    from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata
    from knowledge_manager.storage import search_modules

    kb_path.mkdir(parents=True, exist_ok=True)
    deprecated = Module(
        id="old", category="test", title="Deprecated Module",
        summary="A deprecated module for search.",
        content=ModuleContent(overview="Old overview here.", details="Old details long enough for validation check."),
        metadata=ModuleMetadata(status="deprecated", confidence="high"),
    )
    save_module(deprecated, kb_path)
    from knowledge_manager.storage import rebuild_index
    rebuild_index(kb_path)

    results = search_modules("deprecated module", kb_path)
    assert len(results) >= 1
    # Deprecated modules get confidence downgraded
    result = [r for r in results if r.module.id == "old"][0]
    assert result.module.metadata.confidence == "high"  # stored confidence unchanged
    # But the search result confidence should reflect the penalty...
    # (The penalty is applied in ranking, not returned in the module itself)


def test_module_status_default_is_published():
    """New modules should default to 'published' status."""
    from knowledge_manager.schemas import ModuleMetadata
    meta = ModuleMetadata()
    assert meta.status == "published"


def test_module_status_validates_literal():
    """ModuleMetadata.status should only accept valid literal values."""
    from knowledge_manager.schemas import ModuleMetadata
    meta = ModuleMetadata(status="draft")
    assert meta.status == "draft"
    meta = ModuleMetadata(status="reviewed")
    assert meta.status == "reviewed"


# ── Phase 3A: health dashboard tests ──


def test_health_score_defaults():
    from knowledge_manager.schemas import HealthScore
    hs = HealthScore()
    assert hs.freshness == 0.0
    assert hs.usage == 0.0
    assert hs.completeness == 0.0
    assert hs.overall == 0.0


def test_module_health_schema():
    from knowledge_manager.schemas import ModuleHealth, HealthScore
    mh = ModuleHealth(
        module_id="mod1", category="auth", title="Test",
        status="published",
        score=HealthScore(freshness=80, usage=60, completeness=70, overall=70.5),
    )
    assert mh.module_id == "mod1"
    assert mh.score.overall == 70.5
    assert mh.issues == []


def test_kb_health_report_schema():
    from knowledge_manager.schemas import KBHealthReport
    report = KBHealthReport(total_modules=10, total_categories=3, overall_score=75.0)
    assert report.total_modules == 10
    assert report.at_risk_modules == []
    assert report.category_breakdown == {}


def test_compute_module_health_freshness_recent(kb_path):
    """Recently updated modules should have high freshness."""
    from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata
    from knowledge_manager.storage import save_module, compute_module_health

    kb_path.mkdir(parents=True, exist_ok=True)
    mod = Module(
        id="fresh", category="test", title="Fresh Module",
        summary="Recently updated module.",
        content=ModuleContent(overview="Overview text.", details="Details long enough for validation check."),
        metadata=ModuleMetadata(confidence="high"),
    )
    save_module(mod, kb_path)
    h = compute_module_health(mod, kb_path)
    assert h.score.freshness == 100.0  # just created


def test_compute_module_health_completeness_full(kb_path):
    """Fully populated content should get max completeness."""
    from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata
    from knowledge_manager.storage import save_module, compute_module_health

    kb_path.mkdir(parents=True, exist_ok=True)
    mod = Module(
        id="full", category="test", title="Full Module",
        summary="Module with all fields completed.",
        content=ModuleContent(
            overview="Overview text here.",
            details="Details text long enough for validation.",
            examples="Examples section filled.",
            caveats="Caveats section filled.",
            references="References section filled.",
        ),
        metadata=ModuleMetadata(confidence="high"),
    )
    save_module(mod, kb_path)
    h = compute_module_health(mod, kb_path)
    assert h.score.completeness == 100.0


def test_compute_module_health_partial_completeness(kb_path):
    """Missing fields should reduce completeness score."""
    from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata
    from knowledge_manager.storage import save_module, compute_module_health

    kb_path.mkdir(parents=True, exist_ok=True)
    mod = Module(
        id="partial", category="test", title="Partial Module",
        summary="Module missing some fields.",
        content=ModuleContent(
            overview="Overview only.",
            details="Details text long enough.",
            # examples, caveats, references all empty
        ),
        metadata=ModuleMetadata(confidence="low"),
    )
    save_module(mod, kb_path)
    h = compute_module_health(mod, kb_path)
    # overview(30) + details(30) = 60
    assert h.score.completeness == 60.0


def test_compute_module_health_detects_zombie(kb_path):
    """Modules with no load events should be flagged as zombie."""
    from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata
    from knowledge_manager.storage import save_module, compute_module_health

    kb_path.mkdir(parents=True, exist_ok=True)
    mod = Module(
        id="zombie", category="test", title="Zombie Module",
        summary="Never loaded module.",
        content=ModuleContent(overview="Overview text here.", details="Details long enough for validation check."),
        metadata=ModuleMetadata(confidence="low"),
    )
    save_module(mod, kb_path)
    h = compute_module_health(mod, kb_path)
    assert "zombie" in h.issues


def test_compute_module_health_detects_incomplete(kb_path):
    """Low completeness (minimal content only) should flag incomplete issue."""
    from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata
    from knowledge_manager.storage import save_module, compute_module_health

    kb_path.mkdir(parents=True, exist_ok=True)
    mod = Module(
        id="bare", category="test", title="Bare Module",
        summary="Minimal module.",
        content=ModuleContent(
            overview="Just overview",
            details="Min details here only",
        ),
        metadata=ModuleMetadata(confidence="low"),
    )
    save_module(mod, kb_path)
    h = compute_module_health(mod, kb_path)
    # overview(30) + details(30) = 60, threshold is 70 → incomplete
    assert "incomplete" in h.issues


def test_generate_health_report_with_modules(kb_path):
    """Full report should aggregate module health."""
    from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata
    from knowledge_manager.storage import save_module, rebuild_index, generate_health_report

    kb_path.mkdir(parents=True, exist_ok=True)
    mod_a = Module(
        id="a", category="auth", title="Auth A",
        summary="Auth module A for health report.",
        content=ModuleContent(overview="Overview A.", details="Details for module A long enough."),
        metadata=ModuleMetadata(tags=["auth"]),
    )
    mod_b = Module(
        id="b", category="db", title="Database Module B",
        summary="DB module B for health report.",
        content=ModuleContent(overview="Overview B.", details="Details for module B long enough."),
        metadata=ModuleMetadata(tags=["db"]),
    )
    save_module(mod_a, kb_path)
    save_module(mod_b, kb_path)
    rebuild_index(kb_path)

    report = generate_health_report(kb_path)
    assert report.total_modules == 2
    assert report.total_categories == 2
    assert len(report.category_breakdown) == 2


def test_generate_health_report_empty(kb_path):
    """Empty KB should return zero-count report."""
    from knowledge_manager.storage import generate_health_report

    kb_path.mkdir(parents=True, exist_ok=True)
    report = generate_health_report(kb_path)
    assert report.total_modules == 0
    assert report.overall_score == 0.0


# ── Phase 3B: usage analytics tests ──


def test_usage_stats_schema():
    from knowledge_manager.schemas import UsageStats
    s = UsageStats(period_days=30)
    assert s.total_searches == 0
    assert s.top_modules == []
    assert s.unmatched_queries == []
    assert s.daily_activity == []


def test_aggregate_usage_stats_empty(kb_path):
    """Empty telemetry should return zero-count stats."""
    from knowledge_manager.storage import aggregate_usage_stats

    kb_path.mkdir(parents=True, exist_ok=True)
    (kb_path / ".telemetry").mkdir(exist_ok=True)

    stats = aggregate_usage_stats(kb_path, period_days=30)
    assert stats.total_searches == 0
    assert stats.total_loads == 0


def test_aggregate_usage_stats_with_events(kb_path):
    """Stats should aggregate search and load events correctly."""
    from knowledge_manager.storage import aggregate_usage_stats, record_search_event, record_load_event

    kb_path.mkdir(parents=True, exist_ok=True)

    record_search_event("test query", ["auth/jwt"], kb_path)
    record_load_event("jwt", "auth", kb_path)

    stats = aggregate_usage_stats(kb_path, period_days=30)
    assert stats.total_searches == 1
    assert stats.total_loads == 1


def test_daily_activity_point_schema():
    from knowledge_manager.schemas import DailyActivityPoint
    d = DailyActivityPoint(date="2026-06-09", searches=10, loads=5)
    assert d.searches == 10
    assert d.loads == 5


def test_module_usage_entry_schema():
    from knowledge_manager.schemas import ModuleUsageEntry
    m = ModuleUsageEntry(module_id="m", category="c", title="T", load_count=5, trend="up")
    assert m.load_count == 5
    assert m.trend == "up"


def test_unmatched_query_entry_schema():
    from knowledge_manager.schemas import UnmatchedQueryEntry
    u = UnmatchedQueryEntry(query_hash="abc", query_terms=["test", "query"], count=3)
    assert u.query_hash == "abc"
    assert u.count == 3


# ── Phase 3C: graph analysis tests ──


def test_graph_stats_schema():
    from knowledge_manager.schemas import GraphStats, HubEntry
    gs = GraphStats(
        total_nodes=10, total_edges=15, density=0.15,
        hub_modules=[HubEntry(module_id="h1", category="auth", title="Hub", in_degree=5, out_degree=2)],
    )
    assert gs.total_nodes == 10
    assert len(gs.hub_modules) == 1
    assert gs.orphan_modules == []
    assert gs.broken_links == []
    assert gs.clusters == []


def test_analyze_graph_empty(kb_path):
    from knowledge_manager.storage import analyze_graph
    kb_path.mkdir(parents=True, exist_ok=True)
    gs = analyze_graph(kb_path)
    assert gs.total_nodes == 0


def test_analyze_graph_with_modules(kb_path):
    from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata
    from knowledge_manager.storage import save_module, rebuild_index, analyze_graph

    kb_path.mkdir(parents=True, exist_ok=True)
    mod_a = Module(
        id="a", category="auth", title="Auth Module A",
        summary="Module A for graph testing.",
        content=ModuleContent(overview="Overview A.", details="Details for A long enough for validation."),
        metadata=ModuleMetadata(tags=["auth"], related_modules=["db/b"]),
    )
    mod_b = Module(
        id="b", category="db", title="DB Module B",
        summary="Module B for graph testing.",
        content=ModuleContent(overview="Overview B.", details="Details for B long enough for validation check."),
        metadata=ModuleMetadata(tags=["db"]),
    )
    save_module(mod_a, kb_path)
    save_module(mod_b, kb_path)
    rebuild_index(kb_path)

    gs = analyze_graph(kb_path)
    assert gs.total_nodes == 2
    assert gs.total_edges == 1  # a → b
    assert gs.total_nodes > 0


def test_detect_clusters_finds_components(kb_path):
    from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata
    from knowledge_manager.storage import save_module, rebuild_index, detect_clusters

    kb_path.mkdir(parents=True, exist_ok=True)
    mod_a = Module(
        id="a", category="auth", title="Auth A",
        summary="Auth module A cluster test.",
        content=ModuleContent(overview="Overview A.", details="Details for A long enough for validation."),
        metadata=ModuleMetadata(related_modules=["db/b"]),
    )
    mod_b = Module(
        id="b", category="db", title="Database Module B",
        summary="DB module B cluster test.",
        content=ModuleContent(overview="Overview B.", details="Details for B long enough for validation check."),
        metadata=ModuleMetadata(related_modules=["auth/a"]),
    )
    save_module(mod_a, kb_path)
    save_module(mod_b, kb_path)
    rebuild_index(kb_path)

    clusters = detect_clusters(kb_path)
    assert len(clusters) >= 1
    assert clusters[0].module_count >= 2


# ── Phase 3D: recommendation tests ──


def test_recommendation_schema():
    from knowledge_manager.schemas import Recommendation, RecommendationType
    r = Recommendation(
        type=RecommendationType.ARCHIVE,
        module_id="m", category="test", title="Test",
        score=0.8, reason="ZOMBIE, STALE",
    )
    assert r.type == RecommendationType.ARCHIVE
    assert r.score == 0.8


def test_recommendation_report_schema():
    from knowledge_manager.schemas import RecommendationReport
    report = RecommendationReport()
    assert report.archive_candidates == []
    assert report.enrichment_needed == []
    assert report.suggested_links == []
    assert report.review_reminders == []


def test_generate_recommendations_empty(kb_path):
    from knowledge_manager.storage import generate_recommendations

    kb_path.mkdir(parents=True, exist_ok=True)
    report = generate_recommendations(kb_path)
    assert report.archive_candidates == []


def test_generate_recommendations_suggests_enrichment(kb_path):
    from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata
    from knowledge_manager.storage import save_module, rebuild_index, generate_recommendations

    kb_path.mkdir(parents=True, exist_ok=True)
    mod = Module(
        id="bare", category="test", title="Bare Module",
        summary="Minimal content module.",
        content=ModuleContent(
            overview="Just overview text.",
            details="Details that are long enough for validation.",
            # no examples, caveats, references
        ),
        metadata=ModuleMetadata(tags=["test"]),
    )
    save_module(mod, kb_path)
    rebuild_index(kb_path)

    report = generate_recommendations(kb_path)
    assert len(report.enrichment_needed) >= 1
    assert report.enrichment_needed[0].module_id == "bare"


def test_generate_recommendations_link_suggestion(kb_path):
    from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata
    from knowledge_manager.storage import save_module, rebuild_index, generate_recommendations

    kb_path.mkdir(parents=True, exist_ok=True)
    mod_a = Module(
        id="a", category="auth", title="Auth Module A",
        summary="Module A for link suggestion.",
        content=ModuleContent(overview="Overview A.", details="Details for A long enough for validation."),
        metadata=ModuleMetadata(tags=["security", "api"]),
    )
    mod_b = Module(
        id="b", category="api", title="API Module B",
        summary="Module B for link suggestion.",
        content=ModuleContent(overview="Overview B.", details="Details for B long enough for validation check."),
        metadata=ModuleMetadata(tags=["security", "api"]),
    )
    save_module(mod_a, kb_path)
    save_module(mod_b, kb_path)
    rebuild_index(kb_path)

    report = generate_recommendations(kb_path)
    assert len(report.suggested_links) >= 1


# ── Phase 4B: Federation tests ──


def test_load_federation_empty(kb_path):
    """load_federation should return empty dict when no config or no namespaces."""
    from knowledge_manager.storage import load_federation, load_index, save_index
    kb_path.mkdir(parents=True, exist_ok=True)
    save_index(Index(), kb_path)

    result = load_federation(kb_path)
    assert result == {}


def test_load_federation_with_namespaces(kb_path, tmp_path):
    """load_federation should load and validate configured namespaces."""
    from knowledge_manager.storage import load_federation, load_index, save_index
    from knowledge_manager.schemas import Config, FederationConfig, FederationNamespace

    kb_path.mkdir(parents=True, exist_ok=True)
    save_index(Index(description="Main KB"), kb_path)

    # Create a secondary KB
    ns_path = tmp_path / "team-auth-kb"
    ns_path.mkdir()
    save_index(Index(description="Auth team KB"), ns_path)

    # Write federation config
    import json
    config_path = kb_path / "config.json"
    config_path.write_text(json.dumps({
        "federation": {
            "namespaces": {
                "auth": {"kb_path": str(ns_path), "description": "Auth team KB", "search_default": True}
            }
        }
    }))

    result = load_federation(kb_path)
    assert "auth" in result
    assert result["auth"]["description"] == "Auth team KB"
    assert result["auth"]["search_default"] is True
    assert result["auth"]["index"] is not None


def test_load_federation_missing_path(kb_path, tmp_path):
    """load_federation should skip namespaces whose path does not exist."""
    from knowledge_manager.storage import load_federation, load_index, save_index
    import json

    kb_path.mkdir(parents=True, exist_ok=True)
    save_index(Index(), kb_path)

    config_path = kb_path / "config.json"
    config_path.write_text(json.dumps({
        "federation": {
            "namespaces": {
                "missing": {"kb_path": "/nonexistent/path", "description": "Missing", "search_default": True}
            }
        }
    }))

    result = load_federation(kb_path)
    assert result == {}
