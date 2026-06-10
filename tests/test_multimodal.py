import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from knowledge_manager.extractor import (
    Extractor, IMAGE_PROMPT, REPO_PROMPT, MEETING_PROMPT,
)
from knowledge_manager.llm_clients import BaseLLMClient
from knowledge_manager.schemas import ExtractionConfig, Module


class MockLLMClient(BaseLLMClient):
    def __init__(self):
        pass

    async def complete(self, prompt: str) -> str:
        return (
            '[{"id": "test-module", "category": "test", "title": "Test Module", '
            '"summary": "This is a test module extracted from source.", '
            '"content": {"overview": "Our approach to testing is comprehensive.", '
            '"details": "We use pytest with fixtures and mocking.", '
            '"examples": "Example code here.", "references": "See also testing docs.", '
            '"caveats": "Mock carefully."}, '
            '"metadata": {"tags": ["test"], "confidence": "high"}}]'
        )

    async def complete_vision(self, prompt: str, image_path: str) -> str:
        return (
            '[{"id": "arch-diagram", "category": "architecture", "title": "System Architecture", '
            '"summary": "Microservice architecture with 5 services.", '
            '"content": {"overview": "Our system uses a microservice architecture.", '
            '"details": "Services communicate via gRPC and Kafka.", '
            '"examples": "Diagram shows service A calling B via gRPC.", '
            '"references": "See deployment docs.", "caveats": "Latency not shown in diagram."}, '
            '"metadata": {"tags": ["architecture", "diagram"], "confidence": "high"}}]'
        )


@pytest.fixture
def extractor():
    cfg = ExtractionConfig()
    return Extractor(MockLLMClient(), cfg)


class TestImageExtraction:
    def test_extract_from_image(self, extractor, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n\x00" + b"\x00" * 100)
        modules = asyncio.run(extractor.extract_from_image(str(img), "architecture"))
        assert len(modules) == 1
        assert modules[0].id == "arch-diagram"
        assert modules[0].category == "architecture"

    def test_image_vision_not_implemented(self, tmp_path):
        class NoVisionClient(BaseLLMClient):
            def __init__(self):
                pass

            async def complete(self, prompt: str) -> str:
                return (
                    '[{"id": "fallback", "category": "general", "title": "Fallback Module", '
                    '"summary": "This is a fallback test module for extraction.", '
                    '"content": {"overview": "Our fallback approach to testing.", '
                    '"details": "We use fallback when vision is unavailable.", '
                    '"examples": "", "references": "", "caveats": ""}, '
                    '"metadata": {"tags": ["fallback"], "confidence": "low"}}]'
                )

        cfg = ExtractionConfig()
        extractor = Extractor(NoVisionClient(), cfg)
        img = tmp_path / "test.png"
        img.write_bytes(b"fake")
        modules = asyncio.run(extractor.extract_from_image(str(img), "general"))
        assert len(modules) == 1
        assert modules[0].id == "fallback"


class TestRepoExtraction:
    def test_repo_dir_tree(self, tmp_path):
        repo = tmp_path / "test-repo"
        (repo / "src").mkdir(parents=True)
        (repo / "README.md").write_text("# Test Repo\nA test project.")
        (repo / "pyproject.toml").write_text("[project]\nname = 'test'")
        (repo / "src" / "main.py").write_text("def main(): pass")

        tree = Extractor._render_dir_tree(repo)
        assert "README.md" in tree
        assert "pyproject.toml" in tree
        assert "src/" in tree
        assert "main.py" in tree

    def test_read_key_files(self, tmp_path):
        repo = tmp_path / "test-repo2"
        repo.mkdir()
        (repo / "README.md").write_text("# Test\nSome content.\n" * 10)
        (repo / "pyproject.toml").write_text("[project]\nname = 'test2'")

        result = Extractor._read_key_files(repo)
        assert "README.md" in result
        assert "pyproject.toml" in result

    def test_extract_from_repo(self, extractor, tmp_path):
        repo = tmp_path / "test-repo3"
        repo.mkdir()
        (repo / "README.md").write_text("# Test Repo")
        (repo / "src").mkdir()
        (repo / "src" / "main.py").write_text("print('hello')")

        modules = extractor.extract_from_repo(str(repo), "backend")
        assert len(modules) == 1
        assert modules[0].category == "backend"

    def test_repo_missing(self, extractor):
        result = extractor.extract_from_repo("/nonexistent/path", "general")
        assert len(result) == 0


class TestMeetingExtraction:
    def test_extract_from_meeting(self, extractor):
        text = "## Architecture Decision\nWe decided to use PostgreSQL over MongoDB for the following reasons..."
        modules = extractor.extract_from_meeting(text, "decisions")
        assert len(modules) >= 1

    def test_meeting_decision_tags(self, extractor):
        text = "决定: 使用 Redis 作为缓存层。理由: 低延迟, 支持丰富数据结构。"
        modules = extractor.extract_from_meeting(text, "decisions")
        for m in modules:
            assert m.metadata.tags is not None

    def test_empty_meeting(self, extractor):
        modules = extractor.extract_from_meeting("", "general")
        assert isinstance(modules, list)


class TestRenderDirTree:
    def test_empty_dir(self, tmp_path):
        empty = tmp_path / "empty-repo"
        empty.mkdir()
        tree = Extractor._render_dir_tree(empty)
        assert tree == ""

    def test_max_files_truncation(self, tmp_path):
        big = tmp_path / "big-repo"
        big.mkdir()
        for i in range(100):
            (big / f"file_{i}.py").write_text(f"# file {i}")
        tree = Extractor._render_dir_tree(big, max_files=20)
        assert "truncated" in tree
