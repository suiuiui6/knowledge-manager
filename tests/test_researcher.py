import pytest
from pathlib import Path

from knowledge_manager.researcher import (
    Researcher,
    ResearchResult,
    SourceResult,
    SourceChunk,
    _quick_relevance,
    _chunked,
)
from knowledge_manager.schemas import ResearchConfig, ResearchSource


class FakeLLM:
    def __init__(self, responses=None):
        self.responses = responses or []
        self.idx = 0
        self.config = type("C", (), {
            "api_key": "", "model": "", "base_url": "", "temperature": 0.3, "max_tokens": 1024,
        })()

    async def complete(self, prompt):
        if self.idx < len(self.responses):
            r = self.responses[self.idx]
            self.idx += 1
            return r
        return '["simple query"]'


class TestQuickRelevance:
    def test_exact_match(self):
        assert _quick_relevance("JWT token configuration", "jwt") == 1.0

    def test_no_match(self):
        assert _quick_relevance("nothing here", "jwt") == 0.0

    def test_partial_match(self):
        score = _quick_relevance("JWT configuration for auth", "jwt token")
        assert 0 < score < 1.0


class TestChunked:
    def test_chunked(self):
        result = list(_chunked([1, 2, 3, 4, 5], 2))
        assert len(result) == 3
        assert result[0] == [1, 2]


class TestResearcher:
    @pytest.fixture
    def researcher(self, tmp_path):
        kb = tmp_path / "test_kb"
        kb.mkdir()
        from knowledge_manager.schemas import Index
        from knowledge_manager.storage import save_index
        save_index(Index(description="Test KB"), kb)

        cfg = ResearchConfig(enabled=True, default_depth="shallow")
        llm = FakeLLM([
            '["gRPC service communication", "message queue selection"]',  # decompose
            '["grpc", "protobuf", "stub", "channel"]',                     # code keywords
            "Synthesis: gRPC is recommended for service communication.",    # synthesize
        ])
        return Researcher(kb, cfg, llm)

    @pytest.mark.asyncio
    async def test_decompose_query(self, researcher):
        researcher.llm.idx = 0
        sub = await researcher._decompose_query("What protocol for microservices?")
        assert len(sub) >= 1

    @pytest.mark.asyncio
    async def test_decompose_fallback(self, researcher):
        researcher.llm.responses = ["not json"]
        researcher.llm.idx = 0
        sub = await researcher._decompose_query("test")
        assert sub == ["test"]

    def test_assign_sources(self, researcher):
        researcher.config.sources = [
            ResearchSource(type="doc_dir", path="/tmp/docs"),
        ]
        result = researcher._assign_sources(["q1", "q2"])
        assert len(result) == 2

    def test_validate_source_allows_safe_paths(self, researcher):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            src = ResearchSource(type="doc_dir", path=td)
            researcher._validate_source(src)

    def test_validate_source_rejects_forbidden(self, researcher, tmp_path):
        secret_dir = tmp_path / ".ssh"
        secret_dir.mkdir()
        src = ResearchSource(type="doc_dir", path=str(secret_dir))
        with pytest.raises(ValueError):
            researcher._validate_source(src)

    @pytest.mark.asyncio
    async def test_search_doc_dir(self, researcher, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "test.md").write_text("gRPC is used for inter-service communication with protobuf")
        src = ResearchSource(type="doc_dir", path=str(docs), include_patterns=["*.md"])
        result = await researcher._search_doc_dir("gRPC protobuf", src)
        assert result.total_found >= 1

    @pytest.mark.asyncio
    async def test_search_doc_dir_nonexistent(self, researcher):
        src = ResearchSource(type="doc_dir", path="/nonexistent/path")
        result = await researcher._search_doc_dir("test", src)
        assert result.total_found == 0

    @pytest.mark.asyncio
    async def test_research_pipeline(self, researcher):
        result = await researcher.research("What is gRPC?", "shallow")
        assert isinstance(result, ResearchResult)
        assert result.query == "What is gRPC?"
        assert result.took_ms >= 0

    @pytest.mark.asyncio
    async def test_research_empty_sources(self, researcher):
        researcher.llm.responses = ['["test query"]', "empty synthesis"]
        researcher.llm.idx = 0
        result = await researcher.research("test", "shallow")
        assert result.query == "test"

    @pytest.mark.asyncio
    async def test_extract_code_keywords(self, researcher):
        researcher.llm.idx = 1
        keywords = await researcher._extract_code_keywords("gRPC communication")
        assert len(keywords) >= 1
        assert all(isinstance(k, str) for k in keywords)

    @pytest.mark.asyncio
    async def test_synthesize_empty(self, researcher):
        result = await researcher._synthesize("test", [], "shallow")
        assert result == ""


class TestResearchConfig:
    def test_defaults(self):
        cfg = ResearchConfig()
        assert cfg.enabled is False
        assert cfg.default_depth == "shallow"
        assert cfg.auto_trigger is False

    def test_config_in_config(self):
        from knowledge_manager.schemas import Config
        cfg = Config()
        assert cfg.research.enabled is False
        assert cfg.research.sources == []
