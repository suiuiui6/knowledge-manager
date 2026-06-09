import pytest
from pathlib import Path

from knowledge_manager.sync import MarkdownSync
from knowledge_manager.markdown import parse_markdown_module


class TestMarkdownSync:
    @pytest.fixture
    def kb(self, tmp_path):
        kb = tmp_path / "test_kb"
        kb.mkdir()
        from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata
        from knowledge_manager.storage import save_index, save_module

        save_index(Index(description="Test KB"), kb)

        mod = Module(
            id="test-mod", category="general",
            title="Test Module Title",
            summary="A test module for sync testing purposes.",
            content=ModuleContent(
                overview="This is the overview text for testing.",
                details="These are the details text with enough characters for validation to pass correctly.",
                examples="Example code goes here",
                caveats="Watch out for edge cases",
            ),
            metadata=ModuleMetadata(tags=["test", "sync"], confidence="high"),
        )
        save_module(mod, kb)
        return kb

    def test_sync_on_save_creates_md(self, kb):
        md_path = kb / "general" / "test-mod.md"
        assert md_path.exists()
        content = md_path.read_text(encoding="utf-8")
        assert "---" in content
        assert "test-mod" in content
        assert "# 概述" in content

    def test_sync_on_rebuild_no_conflicts(self, kb):
        conflicts = MarkdownSync.sync_on_rebuild(kb)
        assert len(conflicts) == 0

    def test_sync_md_to_json(self, kb):
        md_path = kb / "general" / "test-mod.md"
        md_path.write_text(md_path.read_text().replace("Test Module Title", "Updated Title"), encoding="utf-8")
        conflicts = MarkdownSync.sync_on_rebuild(kb)
        remaining = [c for c in conflicts if "Manually fix" in c.action_required]
        assert len(remaining) == 0

    def test_export_obsidian(self, kb, tmp_path):
        vault = tmp_path / "obsidian_vault"
        count = MarkdownSync.export_obsidian(kb, vault)
        assert count >= 1
        assert (vault / "general" / "test-mod.md").exists()
        assert (vault / ".obsidian" / "graph.json").exists()
        assert (vault / "_index.md").exists()

    def test_roundtrip_parse_render(self, kb):
        from knowledge_manager.storage import load_module
        from knowledge_manager.markdown import render_markdown_module

        module = load_module("test-mod", "general", kb)
        md = render_markdown_module(module)
        reparsed = parse_markdown_module(md)
        assert reparsed.id == module.id
        assert reparsed.title == module.title
