import pytest
from pathlib import Path

from knowledge_manager.chat import ChatEvent, ChatPipeline, REWRITE_PROMPT, SYSTEM_PROMPT


class FakeLLMClient:
    def __init__(self, responses=None):
        self.responses = responses or []
        self.call_count = 0
        self.config = type("Config", (), {
            "api_key": "test",
            "model": "test-model",
            "base_url": "",
            "temperature": 0.3,
            "max_tokens": 1024,
        })()

    async def complete(self, prompt: str) -> str:
        if self.call_count < len(self.responses):
            result = self.responses[self.call_count]
            self.call_count += 1
            return result
        self.call_count += 1
        return "Test response"


class TestChatEvent:
    def test_event_creation(self):
        e = ChatEvent("status", {"message": "test"})
        assert e.type == "status"
        assert e.data["message"] == "test"


class TestChatPipeline:
    @pytest.fixture
    def pipeline(self, tmp_path):
        kb = tmp_path / "test_kb"
        kb.mkdir()
        from knowledge_manager.schemas import Index
        from knowledge_manager.storage import save_index

        idx = Index(description="Test KB")
        save_index(idx, kb)

        llm = FakeLLMClient(responses=["rewritten query", '["q1", "q2", "q3"]'])
        return ChatPipeline(kb, llm)

    @pytest.mark.asyncio
    async def test_rewrite_query_no_history(self, pipeline):
        result = await pipeline._rewrite_query("test query", [])
        assert result == "test query"

    @pytest.mark.asyncio
    async def test_rewrite_query_with_history(self, pipeline):
        pipeline.llm.responses = ["JWT token expiration time"]
        pipeline.llm.call_count = 0
        history = [
            {"role": "user", "content": "How does JWT work?"},
            {"role": "assistant", "content": "JWT uses RS256..."},
        ]
        result = await pipeline._rewrite_query("its expiration time", history)
        assert len(result) > 0

    def test_rrf_fuse(self, pipeline):
        kw = [{"key": "a/1", "title": "A1", "summary": ""}]
        result = pipeline._rrf_fuse([], kw, [], {"keyword": 0.65, "tree": 0, "vector": 0})
        assert len(result) == 1
        assert result[0]["key"] == "a/1"

    def test_rrf_fuse_merges_sources(self, pipeline):
        tree = [{"key": "a/1", "title": "T1", "summary": ""}]
        kw = [{"key": "a/2", "title": "K2", "summary": ""}]
        result = pipeline._rrf_fuse(tree, kw, [], {"tree": 0.35, "keyword": 0.4, "vector": 0})
        assert len(result) == 2

    def test_build_system_prompt(self, pipeline):
        mods = [{"key": "a/1", "title": "Test Module", "summary": "A test summary"}]
        prompt = pipeline._build_system_prompt(mods, "reference")
        assert "a/1" in prompt
        assert "Test Module" in prompt

    def test_detect_citation(self, pipeline):
        mods = [{"key": "auth/jwt", "title": "JWT", "summary": ""}]
        assert pipeline._detect_citation("auth/jwt explains", mods) == "auth/jwt"
        assert pipeline._detect_citation("nothing here", mods) is None

    def test_collect_citations(self, pipeline):
        mods = [
            {"key": "auth/jwt", "title": "JWT", "summary": ""},
            {"key": "auth/oauth", "title": "OAuth", "summary": ""},
        ]
        cited = pipeline._collect_citations("auth/jwt is used here", mods)
        assert "auth/jwt" in cited
        assert "auth/oauth" not in cited

    @pytest.mark.asyncio
    async def test_chat_stream(self, pipeline):
        pipeline.llm.responses = ["rewritten query", '["q1", "q2", "q3"]']
        pipeline.llm.call_count = 0
        events = []
        async for event in pipeline.chat("test query", [], "precise"):
            events.append(event)
        types = [e.type for e in events]
        assert "status" in types
        assert "done" in types
        done = next(e for e in events if e.type == "done")
        assert "took_ms" in done.data

    @pytest.mark.asyncio
    async def test_chat_empty_history(self, pipeline):
        pipeline.llm.responses = ["original query", '["q1"]']
        pipeline.llm.call_count = 0
        events = []
        async for event in pipeline.chat("new topic", [], "precise"):
            events.append(event)
        assert len(events) > 0


class TestSSEEndpoint:
    @pytest.fixture
    def client(self, tmp_path):
        kb = tmp_path / "test_kb"
        kb.mkdir()
        from knowledge_manager.schemas import Index, Config, LLMProviderConfig
        from knowledge_manager.storage import save_index

        idx = Index(description="Test KB")
        save_index(idx, kb)

        cfg = Config(llm_providers={"test": LLMProviderConfig(
            api_key="test-key", model="test-model", base_url="https://test.example.com", default=True,
        )})
        (kb / "config.json").write_text(cfg.model_dump_json(), encoding="utf-8")

        from knowledge_manager.http_server import create_app
        from fastapi.testclient import TestClient

        app = create_app(kb)
        return TestClient(app)

    def test_chat_endpoint_accepts_request(self, client):
        r = client.post("/api/chat", json={"query": "test", "history": [], "mode": "precise"})
        assert r.status_code in (200, 503)
