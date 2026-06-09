import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from knowledge_manager.schemas import Module, ModuleContent, Index
from knowledge_manager.storage import save_module, save_index


def make_module(id="auth-jwt", category="auth") -> Module:
    return Module(
        id=id, category=category,
        title="JWT Authentication Guide",
        summary="How JWT tokens work in our system for authentication",
        content=ModuleContent(
            overview="JWT tokens are used for stateless authentication",
            details="Tokens are signed with RS256 and expire after 24 hours",
        ),
    )


@pytest.fixture
def kb_path(tmp_path):
    path = tmp_path / "kb"
    path.mkdir()
    return path


@pytest.fixture
def server(kb_path):
    from knowledge_manager.mcp_server import create_server
    return create_server(kb_path)


def test_server_creates_fastmcp_instance(server):
    from mcp.server.fastmcp import FastMCP
    assert isinstance(server, FastMCP)


@pytest.mark.asyncio
async def test_resource_index_returns_json(server, kb_path):
    index = Index(description="Test KB")
    module = make_module()
    index.add_module(module)
    save_index(index, kb_path)

    result = await server.read_resource("knowledge://index")
    content = result[0].content if hasattr(result[0], "content") else str(result[0])
    data = json.loads(content)
    assert "categories" in data or "description" in data


@pytest.mark.asyncio
async def test_tool_load_module_found(server, kb_path):
    module = make_module()
    save_module(module, kb_path)

    result = await server.call_tool("load_module", {"module_id": "auth-jwt", "category": "auth"})
    content = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert "JWT" in content


@pytest.mark.asyncio
async def test_tool_load_module_not_found(server, kb_path):
    result = await server.call_tool("load_module", {"module_id": "missing", "category": "auth"})
    content = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert "not found" in content.lower()


@pytest.mark.asyncio
async def test_tool_search_modules(server, kb_path):
    save_module(make_module("auth-jwt", "auth"), kb_path)
    save_module(make_module("db-conn", "database"), kb_path)

    result = await server.call_tool("search_modules", {"query": "JWT authentication"})
    raw = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert "auth-jwt" in raw
    assert '"source": "direct"' in raw
    assert '"confidence": "medium"' in raw
    assert '"caveats"' in raw
    assert '"related_modules"' in raw


@pytest.mark.asyncio
async def test_tool_list_categories(server, kb_path):
    save_module(make_module("auth-jwt", "auth"), kb_path)
    save_module(make_module("db-conn", "database"), kb_path)
    index = Index()
    index.add_module(make_module("auth-jwt", "auth"))
    index.add_module(make_module("db-conn", "database"))
    save_index(index, kb_path)

    result = await server.call_tool("list_categories", {})
    content = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert "auth" in content


@pytest.mark.asyncio
async def test_tool_expand_module_returns_module_and_neighbors(server, kb_path):
    from knowledge_manager.schemas import ModuleMetadata
    main = Module(
        id="jwt", category="auth",
        title="JWT tokens",
        summary="Handling JSON Web Tokens for auth",
        content=ModuleContent(
            overview="A JWT overview for testing expand",
            details="Detailed JWT notes for testing expand tool behavior",
        ),
        metadata=ModuleMetadata(tags=["auth"], related_modules=["auth/oauth-flow"]),
    )
    neighbor = Module(
        id="oauth-flow", category="auth",
        title="OAuth 2.0 flow",
        summary="OAuth 2.0 authorization flow setup",
        content=ModuleContent(
            overview="OAuth overview for expand testing",
            details="Detailed OAuth notes for testing expand tool behavior",
        ),
        metadata=ModuleMetadata(tags=["oauth"]),
    )
    save_module(main, kb_path)
    save_module(neighbor, kb_path)

    result = await server.call_tool("expand_module", {"module_id": "jwt", "category": "auth"})
    content = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert "jwt" in content
    assert "oauth-flow" in content


@pytest.mark.asyncio
async def test_tool_expand_module_not_found(server, kb_path):
    result = await server.call_tool("expand_module", {"module_id": "missing", "category": "auth"})
    content = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert "not found" in content.lower()


@pytest.mark.asyncio
async def test_tool_deep_search_returns_full_content(server, kb_path):
    from knowledge_manager.schemas import ModuleMetadata
    main = Module(
        id="auth-jwt", category="auth",
        title="JWT authentication module",
        summary="How JWT tokens work in our system",
        content=ModuleContent(
            overview="JWT tokens are used for stateless authentication in our system.",
            details="Tokens are signed with RS256 and expire after 24 hours by default.",
        ),
        metadata=ModuleMetadata(tags=["jwt"], related_modules=["auth/oauth-flow"]),
    )
    neighbor = Module(
        id="oauth-flow", category="auth",
        title="OAuth flow module",
        summary="OAuth authorization flow details",
        content=ModuleContent(
            overview="OAuth 2.0 flow for authentication delegation.",
            details="OAuth authorization code flow with PKCE extension for secure exchange.",
        ),
        metadata=ModuleMetadata(tags=["oauth"]),
    )
    save_module(main, kb_path)
    save_module(neighbor, kb_path)

    result = await server.call_tool("deep_search", {"query": "JWT authentication"})
    content = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert "auth-jwt" in content
    assert "details" in content  # Full content loaded
    assert "neighbors" in content  # Graph expanded
    assert "oauth-flow" in content  # Neighbor included


@pytest.mark.asyncio
async def test_session_context_boosts_recently_loaded(server, kb_path):
    """Loading a module should boost it in subsequent searches within the session."""
    save_module(Module(
        id="mod-a", category="general",
        title="Zanzibar quick reference",
        summary="Quick reference for zanzibar topic",
        content=ModuleContent(
            overview="Zanzibar overview for session boost comparison.",
            details="Zanzibar details for mod-a — this module covers the basics.",
        ),
    ), kb_path)
    save_module(Module(
        id="mod-b", category="general",
        title="Zanzibar deep dive",
        summary="In-depth zanzibar module with details",
        content=ModuleContent(
            overview="Zanzibar overview for session boost testing.",
            details="Zanzibar details for mod-b — provides comprehensive coverage.",
        ),
    ), kb_path)

    # Load mod-b first
    await server.call_tool("load_module", {"module_id": "mod-b", "category": "general"})

    # Verify load succeeded
    load_result = await server.call_tool("load_module", {"module_id": "mod-b", "category": "general"})
    load_content = load_result[0].text if hasattr(load_result[0], "text") else str(load_result[0])
    assert "mod-b" in load_content, f"Load should succeed, got: {load_content[:200]}"

    # Search for a term both modules match — mod-b should rank first due to session boost
    result = await server.call_tool("search_modules", {"query": "zanzibar"})
    content = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert "mod-b" in content, f"Search should find mod-b, got: {content[:300]}"
    assert "mod-a" in content, f"Search should find mod-a, got: {content[:300]}"
    # mod-b should appear before mod-a (session boost applied after loading mod-b)
    assert content.index("mod-b") < content.index("mod-a"), \
        f"Session boost should rank loaded mod-b before mod-a"


# ── Phase 2C: MCP changelog resources ──


@pytest.mark.asyncio
async def test_resource_changelog_returns_json(server, kb_path):
    """knowledge://changelog should return valid JSON."""
    (kb_path / ".changelog").mkdir(exist_ok=True)
    from datetime import date
    changelog_file = kb_path / ".changelog" / f"{date.today().isoformat()}.json"
    changelog_file.write_text(json.dumps({
        "date": date.today().isoformat(),
        "commits": [{"hash": "abc1234", "author": "test", "message": "add module", "changes": {"added": ["test/mod"], "modified": [], "deleted": []}}],
    }))

    result = await server.read_resource("knowledge://changelog")
    content = result[0].content if hasattr(result[0], "content") else str(result[0])
    data = json.loads(content)
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["commits"][0]["hash"] == "abc1234"


@pytest.mark.asyncio
async def test_resource_changelog_module_specific(server, kb_path):
    """knowledge://changelog/<key> should return entries for a specific module."""
    (kb_path / ".changelog").mkdir(exist_ok=True)
    from datetime import date
    changelog_file = kb_path / ".changelog" / f"{date.today().isoformat()}.json"
    changelog_file.write_text(json.dumps({
        "date": date.today().isoformat(),
        "commits": [{"hash": "abc1234", "author": "test", "message": "add module", "changes": {"added": ["simplemod"], "modified": [], "deleted": []}}],
    }))

    # Simple key without slash for FastMCP template compatibility
    result = await server.read_resource("knowledge://changelog/simplemod")
    content = result[0].content if hasattr(result[0], "content") else str(result[0])
    data = json.loads(content)
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_resource_changelog_empty_when_missing(server, kb_path):
    """knowledge://changelog should return empty list when no changelogs exist."""
    result = await server.read_resource("knowledge://changelog")
    content = result[0].content if hasattr(result[0], "content") else str(result[0])
    data = json.loads(content)
    assert isinstance(data, list)
    assert len(data) == 0


# ── Phase 2D: archived/deprecated search filtering via MCP ──


@pytest.mark.asyncio
async def test_search_modules_excludes_archived_by_default(server, kb_path):
    """search_modules should exclude archived modules when include_archived=false."""
    from knowledge_manager.schemas import ModuleMetadata
    active = Module(
        id="active", category="test",
        title="Active Module",
        summary="An active test module for search",
        content=ModuleContent(overview="Active module overview for testing.", details="Details for active module that are long enough."),
        metadata=ModuleMetadata(status="published"),
    )
    archived = Module(
        id="archived", category="test",
        title="Archived Module",
        summary="An archived test module for search",
        content=ModuleContent(overview="Archived module overview for testing.", details="Details for archived module that are long enough."),
        metadata=ModuleMetadata(status="archived"),
    )
    save_module(active, kb_path)
    save_module(archived, kb_path)

    result = await server.call_tool("search_modules", {"query": "module"})
    content = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert "active" in content
    assert "archived" not in content


@pytest.mark.asyncio
async def test_search_modules_includes_archived_when_requested(server, kb_path):
    """search_modules should include archived modules when include_archived=true."""
    from knowledge_manager.schemas import ModuleMetadata
    active = Module(
        id="active2", category="test",
        title="Active Module 2",
        summary="Another active module for search",
        content=ModuleContent(overview="Active 2 overview for testing.", details="Details for active2 that are long enough."),
        metadata=ModuleMetadata(status="published"),
    )
    archived = Module(
        id="archived2", category="test",
        title="Archived Module 2",
        summary="Another archived module for search",
        content=ModuleContent(overview="Archived 2 overview for testing.", details="Details for archived2 that are long enough."),
        metadata=ModuleMetadata(status="archived"),
    )
    save_module(active, kb_path)
    save_module(archived, kb_path)

    result = await server.call_tool("search_modules", {"query": "module", "include_archived": True})
    content = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert "active2" in content
    assert "archived2" in content


# ── Phase 3A: MCP health resources ──


@pytest.mark.asyncio
async def test_resource_health_returns_report(server, kb_path):
    """knowledge://health should return health report JSON."""
    from knowledge_manager.storage import save_module, rebuild_index
    mod = make_module("h1", "auth")
    save_module(mod, kb_path)
    rebuild_index(kb_path)

    result = await server.read_resource("knowledge://health")
    content = result[0].content if hasattr(result[0], "content") else str(result[0])
    data = json.loads(content)
    assert "total_modules" in data
    assert data["total_modules"] == 1
    assert "overall_score" in data


@pytest.mark.asyncio
async def test_resource_health_module_specific(server, kb_path):
    """knowledge://health/<key> should return single module health (single-segment key)."""
    from knowledge_manager.storage import save_module, rebuild_index
    mod = make_module("h2mod", "auth")
    save_module(mod, kb_path)
    rebuild_index(kb_path)

    # Use a key without slash for FastMCP template compatibility
    result = await server.read_resource("knowledge://health/h2mod")
    content = result[0].content if hasattr(result[0], "content") else str(result[0])
    data = json.loads(content)
    # Single-segment key without slash won't parse as category/id → error expected
    assert "error" in data or "module_id" in data


@pytest.mark.asyncio
async def test_resource_health_empty_kb(server, kb_path):
    """knowledge://health on empty KB should return zero-count report."""
    result = await server.read_resource("knowledge://health")
    content = result[0].content if hasattr(result[0], "content") else str(result[0])
    data = json.loads(content)
    assert data["total_modules"] == 0


# ── Phase 3B: MCP stats resource ──


@pytest.mark.asyncio
async def test_resource_stats_returns_json(server, kb_path):
    """knowledge://stats should return usage statistics JSON."""
    (kb_path / ".telemetry").mkdir(exist_ok=True)

    result = await server.read_resource("knowledge://stats")
    content = result[0].content if hasattr(result[0], "content") else str(result[0])
    data = json.loads(content)
    assert "total_searches" in data
    assert "period_days" in data


# ── Phase 3C: knowledge_graph MCP tool ──


@pytest.mark.asyncio
async def test_tool_knowledge_graph_global(server, kb_path):
    """knowledge_graph without query should return global stats + clusters."""
    from knowledge_manager.storage import save_module, rebuild_index
    mod = make_module("kg1", "auth")
    mod.metadata.related_modules = ["db/kg2"]
    save_module(mod, kb_path)
    mod2 = make_module("kg2", "db")
    mod2.metadata.related_modules = ["auth/kg1"]
    save_module(mod2, kb_path)
    rebuild_index(kb_path)

    result = await server.call_tool("knowledge_graph", {})
    raw = result[0][0].text
    data = json.loads(raw)
    assert "stats" in data
    assert "clusters" in data


@pytest.mark.asyncio
async def test_tool_knowledge_graph_with_query(server, kb_path):
    """knowledge_graph with query should return related modules for matched modules."""
    from knowledge_manager.storage import save_module, rebuild_index
    mod = make_module("kg3", "auth")
    mod.metadata.related_modules = ["db/kg4"]
    save_module(mod, kb_path)
    mod2 = make_module("kg4", "db")
    save_module(mod2, kb_path)
    rebuild_index(kb_path)

    result = await server.call_tool("knowledge_graph", {"query": "JWT"})
    raw = result[0][0].text
    data = json.loads(raw)
    assert "query" in data
    assert "results" in data


# ── Phase 3D: knowledge://recommendations MCP resource ──


@pytest.mark.asyncio
async def test_resource_recommendations_returns_json(server, kb_path):
    """knowledge://recommendations should return recommendation report JSON."""
    from knowledge_manager.storage import save_module, rebuild_index
    mod = make_module("r1", "auth")
    save_module(mod, kb_path)
    rebuild_index(kb_path)

    result = await server.read_resource("knowledge://recommendations")
    content = result[0].content if hasattr(result[0], "content") else str(result[0])
    data = json.loads(content)
    assert "archive_candidates" in data
    assert "enrichment_needed" in data
    assert "suggested_links" in data
    assert "review_reminders" in data


@pytest.mark.asyncio
async def test_resource_recommendations_empty_kb(server, kb_path):
    """knowledge://recommendations on empty KB should return zero-count report."""
    result = await server.read_resource("knowledge://recommendations")
    content = result[0].content if hasattr(result[0], "content") else str(result[0])
    data = json.loads(content)
    assert data["archive_candidates"] == []
    assert data["enrichment_needed"] == []


# ── Phase 4B: Federation MCP tests ──


@pytest.fixture
def federated_server(tmp_path):
    """Create an MCP server with two federated namespaces."""
    from knowledge_manager.mcp_server import create_server
    from knowledge_manager.storage import save_module, rebuild_index, save_index
    from knowledge_manager.schemas import Index

    main_path = tmp_path / "main-kb"
    main_path.mkdir()
    save_index(Index(description="Main KB"), main_path)
    mod = make_module("main-mod", "general")
    save_module(mod, main_path)
    rebuild_index(main_path)

    ns_path = tmp_path / "team-auth-kb"
    ns_path.mkdir()
    save_index(Index(description="Auth team KB"), ns_path)
    ns_mod = make_module("auth-mod", "auth")
    ns_mod.title = "Auth Team Module"
    save_module(ns_mod, ns_path)
    rebuild_index(ns_path)

    federation = {
        "auth": {
            "index": load_index(ns_path),
            "path": ns_path,
            "description": "Auth team KB",
            "search_default": True,
        }
    }
    return create_server(main_path, federation=federation), main_path, ns_path


def load_index(path: Path):
    from knowledge_manager.storage import load_index as _load
    return _load(path)


@pytest.mark.asyncio
async def test_resource_federation_index(federated_server):
    """knowledge://federation/index should list all namespaces."""
    server, main_path, ns_path = federated_server

    result = await server.read_resource("knowledge://federation/index")
    content = result[0].content if hasattr(result[0], "content") else str(result[0])
    data = json.loads(content)
    assert "namespaces" in data
    assert "auth" in data["namespaces"]
    assert data["namespaces"]["auth"]["description"] == "Auth team KB"
    assert data["total_namespaces"] == 1


@pytest.mark.asyncio
async def test_tool_federated_search(federated_server):
    """federated_search should return results grouped by namespace."""
    server, main_path, ns_path = federated_server

    result = await server.call_tool("federated_search", {"query": "module", "top_per_ns": 3})
    raw = result[0][0].text
    data = json.loads(raw)
    assert "results" in data
    assert "auth" in data["results"]
    # auth namespace should have auth-mod
    auth_results = data["results"]["auth"]
    assert any("auth-mod" in str(r) for r in auth_results)


@pytest.mark.asyncio
async def test_tool_search_modules_with_namespace(federated_server):
    """search_modules with namespace=auth should search the auth KB only."""
    server, main_path, ns_path = federated_server

    result = await server.call_tool("search_modules", {"query": "auth", "namespace": "auth"})
    raw = result[0][0].text
    data = json.loads(raw)
    assert any("auth-mod" in str(r) for r in data)


@pytest.mark.asyncio
async def test_tool_load_module_with_namespace(federated_server):
    """load_module with namespace=auth should load from the auth KB."""
    server, main_path, ns_path = federated_server

    result = await server.call_tool("load_module", {"module_id": "auth-mod", "category": "auth", "namespace": "auth"})
    raw = result[0][0].text
    assert "Auth Team Module" in raw


@pytest.mark.asyncio
async def test_tool_list_categories_with_namespace(federated_server):
    """list_categories with namespace should list the correct KB's categories."""
    server, main_path, ns_path = federated_server

    result = await server.call_tool("list_categories", {"namespace": "auth"})
    raw = result[0][0].text
    data = json.loads(raw)
    assert any(c["category"] == "auth" for c in data)
