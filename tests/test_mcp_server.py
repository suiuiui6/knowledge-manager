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
