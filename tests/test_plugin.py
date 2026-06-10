import json
import pytest
from pathlib import Path

from knowledge_manager.plugin import (
    PluginManifest, Plugin, PluginManager, search_registry,
)


class TestPluginManifest:
    def test_defaults(self):
        m = PluginManifest(name="test", version="0.1.0")
        assert m.name == "test"
        assert m.version == "0.1.0"
        assert m.min_km_version == "0.5.0"
        assert m.hooks == []

    def test_full(self):
        m = PluginManifest(
            name="slack", version="1.2.0",
            description="Slack integration",
            author="dev", hooks=["after_approve"],
        )
        assert m.hooks == ["after_approve"]


class TestPluginManager:
    @pytest.fixture
    def pm(self, tmp_path):
        kb = tmp_path / "test_kb"
        kb.mkdir()
        return PluginManager(kb)

    def test_init_creates_dir(self, pm):
        assert pm.plugins_dir.exists()

    def test_list_empty(self, pm):
        assert pm.list_plugins() == []

    def test_enable_disable_missing(self, pm):
        assert not pm.enable("nonexistent")
        assert not pm.disable("nonexistent")
        assert not pm.uninstall("nonexistent")

    def test_load_from_dir(self, pm):
        plugin_dir = pm.plugins_dir / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "test-plugin",
            "version": "0.1.0",
            "description": "A test plugin",
            "author": "tester",
        }))
        (plugin_dir / "__init__.py").write_text(
            "def after_approve(module, ctx):\n"
            "    return module\n"
        )

        p = pm._load_from_dir(plugin_dir)
        assert p is not None
        assert p.manifest.name == "test-plugin"
        assert p.enabled
        assert callable(p.hook("after_approve"))

    def test_load_all(self, pm):
        for name in ["a-plugin", "b-plugin"]:
            d = pm.plugins_dir / name
            d.mkdir()
            (d / "plugin.json").write_text(json.dumps({
                "name": name, "version": "0.1.0",
            }))
            (d / "__init__.py").write_text("")

        pm.load_all()
        assert len(pm.plugins) == 2
        assert "a-plugin" in pm.plugins

    def test_register_local(self, pm):
        src = pm.kb_path / "src-plugin"
        src.mkdir()
        (src / "plugin.json").write_text(json.dumps({
            "name": "src-plugin", "version": "1.0.0",
        }))
        (src / "__init__.py").write_text("")

        p = pm.register_local(src)
        assert p is not None
        assert p.manifest.name == "src-plugin"

    def test_register_duplicate(self, pm):
        src = pm.kb_path / "dup-plugin"
        src.mkdir()
        (src / "plugin.json").write_text(json.dumps({
            "name": "dup-plugin", "version": "1.0.0",
        }))
        (src / "__init__.py").write_text("")
        pm.register_local(src)
        result = pm.register_local(src)
        assert result is None

    def test_enable_disable(self, pm):
        plugin_dir = pm.plugins_dir / "toggle-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "toggle-plugin", "version": "0.1.0",
        }))
        (plugin_dir / "__init__.py").write_text("")
        pm._load_from_dir(plugin_dir)

        assert pm.disable("toggle-plugin")
        assert not pm.plugins["toggle-plugin"].enabled
        assert pm.enable("toggle-plugin")
        assert pm.plugins["toggle-plugin"].enabled

    def test_uninstall(self, pm):
        plugin_dir = pm.plugins_dir / "rm-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "rm-plugin", "version": "0.1.0",
        }))
        (plugin_dir / "__init__.py").write_text("")
        pm._load_from_dir(plugin_dir)

        assert pm.uninstall("rm-plugin")
        assert "rm-plugin" not in pm.plugins
        assert not plugin_dir.exists()

    def test_get_enabled(self, pm):
        plugin_dir = pm.plugins_dir / "hook-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "hook-plugin", "version": "0.1.0",
        }))
        (plugin_dir / "__init__.py").write_text(
            "def before_search(query, ctx):\n"
            "    return query + ' enhanced'\n"
        )
        pm._load_from_dir(plugin_dir)

        hooks = pm.get_enabled("before_search")
        assert len(hooks) == 1

    def test_get_enabled_skips_disabled(self, pm):
        plugin_dir = pm.plugins_dir / "off-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "off-plugin", "version": "0.1.0",
        }))
        (plugin_dir / "__init__.py").write_text(
            "def after_search(query, results, ctx):\n"
            "    return results\n"
        )
        pm._load_from_dir(plugin_dir)
        pm.disable("off-plugin")

        hooks = pm.get_enabled("after_search")
        assert len(hooks) == 0


class TestSearchRegistry:
    def test_returns_results(self):
        results = search_registry("slack")
        assert len(results) >= 1
        assert "name" in results[0]
