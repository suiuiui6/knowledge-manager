import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from knowledge_manager.http_server import create_app


@pytest.fixture
def client(tmp_path):
    kb = tmp_path / "test_kb"
    kb.mkdir()
    from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata
    from knowledge_manager.storage import save_index, save_module

    idx = Index(description="Test KB")
    save_index(idx, kb)

    mod = Module(
        id="test-mod", category="general", title="Test Module Title",
        summary="A test module for HTTP tests.",
        content=ModuleContent(overview="test overview content", details="test details content here"),
        metadata=ModuleMetadata(tags=["test", "api"], confidence="high", status="published"),
    )
    save_module(mod, kb)

    app = create_app(kb)
    return TestClient(app)


class TestHealth:
    def test_health_ok(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert "overall_score" in data
        assert "total_modules" in data


class TestTree:
    def test_tree_ok(self, client):
        r = client.get("/api/tree")
        assert r.status_code == 200
        data = r.json()
        assert data["type"] == "root"
        assert len(data["children"]) >= 0

    def test_tree_subtree(self, client):
        r = client.get("/api/tree/general/test-mod")
        assert r.status_code == 200
        data = r.json()
        assert data["type"] == "module"
        assert data["id"] == "general/test-mod"

    def test_tree_subtree_404(self, client):
        r = client.get("/api/tree/general/nonexistent")
        assert r.status_code == 404


class TestModules:
    def test_list_modules(self, client):
        r = client.get("/api/modules")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        assert "items" in data
        assert data["page"] == 1

    def test_list_modules_filter_category(self, client):
        r = client.get("/api/modules?category=general")
        assert r.status_code == 200
        data = r.json()
        assert all(m["category"] == "general" for m in data["items"])

    def test_list_modules_pagination(self, client):
        r = client.get("/api/modules?page=1&limit=1")
        assert r.status_code == 200
        data = r.json()
        assert data["limit"] == 1
        assert data["pages"] >= 1

    def test_list_modules_limit_validation(self, client):
        r = client.get("/api/modules?limit=999")
        assert r.status_code == 422

    def test_module_detail(self, client):
        r = client.get("/api/modules/general/test-mod")
        assert r.status_code == 200
        data = r.json()
        assert data["title"] == "Test Module Title"
        assert data["category"] == "general"

    def test_module_detail_404(self, client):
        r = client.get("/api/modules/general/nonexistent")
        assert r.status_code == 404

    def test_module_md_available(self, client):
        r = client.get("/api/modules/general/test-mod.md")
        assert r.status_code == 200
        assert "text/markdown" in r.headers["content-type"]


class TestSearch:
    def test_search_ok(self, client):
        r = client.post("/api/search", json={"query": "test module", "top_k": 5})
        assert r.status_code == 200
        data = r.json()
        assert data["intent"] in ("how-to", "reference", "decision-record", "general")
        assert "results" in data

    def test_search_empty_query(self, client):
        r = client.post("/api/search", json={"query": ""})
        assert r.status_code == 422

    def test_search_category_filter(self, client):
        r = client.post("/api/search", json={"query": "test", "category": "general"})
        assert r.status_code == 200


class TestGraph:
    def test_graph_ok(self, client):
        r = client.get("/api/graph")
        assert r.status_code == 200
        data = r.json()
        assert "nodes" in data
        assert "edges" in data

    def test_graph_subgraph(self, client):
        r = client.get("/api/graph/general/test-mod")
        assert r.status_code == 200
        data = r.json()
        assert len(data["nodes"]) >= 1

    def test_graph_subgraph_404(self, client):
        r = client.get("/api/graph/general/nonexistent")
        assert r.status_code == 404


class TestFallback:
    def test_fallback_ui(self, client):
        r = client.get("/ui/fallback")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "Knowledge Manager" in r.text
        assert "htmx" in r.text.lower()

    def test_ui_redirects_to_fallback(self, client):
        r = client.get("/ui", follow_redirects=False)
        assert r.status_code in (200, 302, 307)


class TestRecommendations:
    def test_recommendations_ok(self, client):
        r = client.get("/api/recommendations")
        assert r.status_code == 200
        data = r.json()
        assert "archive_candidates" in data


class TestStats:
    def test_stats_ok(self, client):
        r = client.get("/api/stats")
        assert r.status_code == 200
        data = r.json()
        assert "total_searches" in data
