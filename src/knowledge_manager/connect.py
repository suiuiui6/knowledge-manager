"""Platform connector for one-click MCP configuration generation."""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from knowledge_manager.schemas import PlatformConfig

PLATFORMS: Dict[str, PlatformConfig] = {
    "claude-code": PlatformConfig(
        name="claude-code",
        config_path="~/.claude/mcp.json",
        description="Claude Code (via .claude/mcp.json)",
    ),
    "copilot": PlatformConfig(
        name="copilot",
        config_path=".vscode/mcp.json",
        description="VS Code GitHub Copilot (via .vscode/mcp.json)",
    ),
    "cursor": PlatformConfig(
        name="cursor",
        config_path=".cursor/mcp.json",
        description="Cursor IDE (via .cursor/mcp.json)",
    ),
    "windsurf": PlatformConfig(
        name="windsurf",
        config_path=".windsurf/mcp.json",
        description="Windsurf IDE (via .windsurf/mcp.json)",
    ),
}

ENTRY_KEY = "knowledge-manager"


def resolve_config_path(platform: str, kb_path: Path) -> Path:
    """Resolve a platform's MCP config path to an absolute path.

    Args:
        platform: Platform name (e.g. "claude-code", "copilot").
        kb_path: Path to the knowledge base (used as fallback cwd for relative paths).

    Returns:
        Absolute path to the platform's MCP config file.
    """
    cfg = PLATFORMS.get(platform)
    if cfg is None:
        raise ValueError(f"Unknown platform: {platform}. Use --list to see available platforms.")

    raw = cfg.config_path
    if raw.startswith("~"):
        return Path(os.path.expanduser(raw))
    return (kb_path / raw).resolve()


def read_mcp_config(config_path: Path) -> Dict[str, Any]:
    """Read an existing MCP config file, returning empty dict if absent."""
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def write_mcp_config(config_path: Path, entry: Dict[str, Any]) -> None:
    """Merge an MCP server entry into the config file.

    Preserves existing mcpServers entries, only updates the knowledge-manager key.
    Creates parent directories if needed.
    """
    existing = read_mcp_config(config_path)
    if "mcpServers" not in existing:
        existing["mcpServers"] = {}
    existing["mcpServers"][ENTRY_KEY] = entry

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")


def remove_mcp_entry(config_path: Path) -> bool:
    """Remove the knowledge-manager entry from an MCP config file.

    Returns True if the entry was found and removed, False if it wasn't there.
    Does NOT delete the file if mcpServers becomes empty.
    """
    existing = read_mcp_config(config_path)
    if not existing:
        return False

    servers = existing.get("mcpServers", {})
    if ENTRY_KEY not in servers:
        return False

    del servers[ENTRY_KEY]
    # Always write back: preserve mcpServers even when empty (user may add more later)
    config_path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    return True


def has_entry(config_path: Path) -> bool:
    """Check if knowledge-manager is already configured in the MCP config."""
    existing = read_mcp_config(config_path)
    return ENTRY_KEY in existing.get("mcpServers", {})


def build_mcp_entry(kb_path: Path) -> Dict[str, Any]:
    """Build the MCP server entry dict for knowledge-manager."""
    return {
        "command": "km",
        "args": ["--kb-path", str(kb_path.absolute()), "serve"],
        "env": {},
    }
