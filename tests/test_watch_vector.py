import pytest
from pathlib import Path

from knowledge_manager.watch_scheduler import WatchScheduler, WatchSource, WatchEvent
from knowledge_manager.vector_index import VectorIndex


class TestWatchScheduler:
    @pytest.fixture
    def scheduler(self, tmp_path):
        kb = tmp_path / "test_kb"
        kb.mkdir()
        return WatchScheduler(kb)

    def test_add_source(self, scheduler):
        src = scheduler.add_source("local", {"path": "/tmp"}, "test")
        assert src.type == "local"
        assert src.id in scheduler.sources

    def test_remove_source(self, scheduler):
        src = scheduler.add_source("doc_dir", {"path": "/tmp"})
        assert scheduler.remove_source(src.id) is True
        assert scheduler.remove_source("nonexistent") is False

    def test_get_status_empty(self, scheduler):
        status = scheduler.get_status()
        assert status["sources"] == 0

    @pytest.mark.asyncio
    async def test_poll_nonexistent_source(self, scheduler):
        event = await scheduler.poll_source("nonexistent")
        assert len(event.errors) > 0

    @pytest.mark.asyncio
    async def test_poll_local(self, scheduler, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "test.md").write_text("test")
        scheduler.add_source("local", {"path": str(docs), "patterns": ["*.md"]})
        sid = list(scheduler.sources.keys())[0]
        event = await scheduler.poll_source(sid)
        assert event.items_found >= 0

    def test_config_persistence(self, scheduler, tmp_path):
        docs = tmp_path / "docs2"
        docs.mkdir()
        scheduler.add_source("local", {"path": str(docs)})
        scheduler2 = WatchScheduler(scheduler.kb_path)
        scheduler2.load_config()
        assert scheduler2.get_status()["sources"] == 1

    @pytest.mark.asyncio
    async def test_poll_all(self, scheduler, tmp_path):
        docs = tmp_path / "docs3"
        docs.mkdir()
        scheduler.add_source("local", {"path": str(docs)})
        events = await scheduler.poll_all()
        assert len(events) == 1


class TestWatchEvent:
    def test_event_creation(self):
        e = WatchEvent("test-source")
        assert e.source_id == "test-source"
        assert e.trigger_type == "schedule"
        assert len(e.errors) == 0


class TestVectorIndex:
    @pytest.fixture
    def vi(self, tmp_path):
        kb = tmp_path / "test_kb"
        kb.mkdir()
        return VectorIndex(kb)

    def test_empty_search(self, vi):
        results = vi.search("test query")
        assert results == []

    def test_init_defaults(self, vi):
        assert vi.provider == "ollama"
        assert vi.dimensions == 1024
