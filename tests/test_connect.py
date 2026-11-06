"""Tests for Phase 4A: Platform connector module."""

import json
import pytest
from pathlib import Path

from knowledge_manager.connect import (
    PLATFORMS,
    build_mcp_entry,
    has_entry,
    read_mcp_config,
    remove_mcp_entry,
    resolve_config_path,
    write_mcp_config,
)
from knowledge_manager.schemas import PlatformConfig


def test_platform_config_schema():
    """PlatformConfig should validate name, config_path, description."""
    cfg = PlatformConfig(name="test-platform", config_path="~/.test/mcp.json", description="Test platform")
    assert cfg.name == "test-platform"
    assert cfg.config_path == "~/.test/mcp.json"
    assert cfg.description == "Test platform"

    # Defaults
    cfg2 = PlatformConfig(name="minimal", config_path="some/path.json")
    assert cfg2.description == ""


def test_platforms_dict_has_required_entries():
    """PLATFORMS should contain claude-code and copilot at minimum."""
    assert "claude-code" in PLATFORMS
    assert "copilot" in PLATFORMS
    for name, cfg in PLATFORMS.items():
        assert isinstance(cfg, PlatformConfig)
        assert cfg.name == name
        assert cfg.config_path


def test_build_mcp_entry_format():
    """build_mcp_entry should produce the correct MCP server entry structure."""
    entry = build_mcp_entry(Path("/tmp/kb"))
    assert entry["command"] == "km"
    assert "--kb-path" in entry["args"]
    assert "serve" in entry["args"]
    assert entry["env"] == {}


def test_resolve_config_path_home_expansion():
    """resolve_config_path should expand ~ to the user's home directory."""
    path = resolve_config_path("claude-code", Path("/tmp/kb"))
    assert ".claude" in str(path)
    assert str(path).endswith("mcp.json")
    assert not str(path).startswith("~")  # Should be expanded


def test_resolve_config_path_relative():
    """resolve_config_path for copilot should resolve relative to kb_path."""
    path = resolve_config_path("copilot", Path("/tmp/kb"))
    assert str(path) == str(Path("/tmp/kb/.vscode/mcp.json").resolve())


def test_resolve_config_path_unknown_platform():
    """resolve_config_path should raise ValueError for unknown platforms."""
    with pytest.raises(ValueError, match="Unknown platform"):
        resolve_config_path("nonexistent", Path.cwd())


def test_read_mcp_config_empty(tmp_path):
    """read_mcp_config should return empty dict for missing file."""
    result = read_mcp_config(tmp_path / "nonexistent.json")
    assert result == {}


def test_read_mcp_config_valid(tmp_path):
    """read_mcp_config should parse existing JSON."""
    path = tmp_path / "mcp.json"
    path.write_text('{"mcpServers": {"other": {"command": "echo"}}}')
    result = read_mcp_config(path)
    assert result["mcpServers"]["other"]["command"] == "echo"


def test_read_mcp_config_invalid_json(tmp_path):
    """read_mcp_config should return empty dict for corrupt JSON."""
    path = tmp_path / "bad.json"
    path.write_text("{not valid json")
    result = read_mcp_config(path)
    assert result == {}


def test_write_mcp_config_new_file(tmp_path):
    """write_mcp_config should create config file with entry."""
    path = tmp_path / "mcp.json"
    entry = {"command": "km", "args": ["--kb-path", "/tmp/kb", "serve"]}
    write_mcp_config(path, entry)

    data = json.loads(path.read_text())
    assert "knowledge-manager" in data["mcpServers"]
    assert data["mcpServers"]["knowledge-manager"] == entry


def test_write_mcp_config_preserves_existing(tmp_path):
    """write_mcp_config should merge with existing mcpServers entries."""
    path = tmp_path / "mcp.json"
    path.write_text('{"mcpServers": {"existing-server": {"command": "node"}}}')

    entry = {"command": "km", "args": ["--kb-path", "/tmp/kb", "serve"]}
    write_mcp_config(path, entry)

    data = json.loads(path.read_text())
    assert "existing-server" in data["mcpServers"]
    assert "knowledge-manager" in data["mcpServers"]


def test_has_entry_true(tmp_path):
    """has_entry should return True when knowledge-manager is configured."""
    path = tmp_path / "mcp.json"
    write_mcp_config(path, {"command": "km"})
    assert has_entry(path)


def test_has_entry_false(tmp_path):
    """has_entry should return False for empty or missing config."""
    path = tmp_path / "mcp.json"
    assert not has_entry(path)

    path.write_text('{"mcpServers": {"other": {}}}')
    assert not has_entry(path)


def test_remove_mcp_entry_removes_and_updates_file(tmp_path):
    """remove_mcp_entry should remove the entry and write back."""
    path = tmp_path / "mcp.json"
    write_mcp_config(path, {"command": "km"})
    assert has_entry(path)

    assert remove_mcp_entry(path)
    assert not has_entry(path)

    data = json.loads(path.read_text())
    assert data["mcpServers"] == {}


def test_remove_mcp_entry_not_present(tmp_path):
    """remove_mcp_entry should return False if entry not found."""
    path = tmp_path / "mcp.json"
    assert not remove_mcp_entry(path)

    path.write_text('{"mcpServers": {"other": {}}}')
    assert not remove_mcp_entry(path)


def test_remove_mcp_entry_preserves_other_keys(tmp_path):
    """remove_mcp_entry should not remove other top-level keys."""
    path = tmp_path / "mcp.json"
    path.write_text('{"version": 2, "mcpServers": {"knowledge-manager": {"command": "km"}, "other": {}}}')
    assert remove_mcp_entry(path)

    data = json.loads(path.read_text())
    assert data["version"] == 2
    assert "knowledge-manager" not in data["mcpServers"]
    assert "other" in data["mcpServers"]
