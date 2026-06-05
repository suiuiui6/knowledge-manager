"""Integration tests covering full end-to-end workflows."""
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from knowledge_manager.cli import cli
from knowledge_manager.schemas import (
    Index,
    Module,
    ModuleContent,
    ModuleMetadata,
)
from knowledge_manager.storage import (
    list_modules,
    list_staging,
    load_index,
    load_module,
    rebuild_index,
    save_module,
    save_to_staging,
)


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def integration_kb(runner, tmp_path):
    kb = tmp_path / "kb"
    result = runner.invoke(cli, ["init", str(kb)])
    assert result.exit_code == 0
    return kb


def make_module(id: str, category: str = "test") -> Module:
    return Module(
        id=id,
        category=category,
        title=f"Module {id}",
        summary=f"Summary for module {id} that is long enough",
        content=ModuleContent(
            overview="Overview text long enough",
            details="Details text definitely long enough to pass validation",
        ),
        metadata=ModuleMetadata(tags=[category, "integration"]),
    )


def test_full_workflow_manual_module(runner, integration_kb):
    """init -> save -> rebuild -> list -> search -> stats -> show -> delete."""
    module = make_module("oauth-flow", "auth")
    save_module(module, integration_kb)
    rebuild_index(integration_kb)

    result = runner.invoke(cli, ["--kb-path", str(integration_kb), "list"])
    assert result.exit_code == 0
    assert "oauth-flow" in result.output

    result = runner.invoke(
        cli, ["--kb-path", str(integration_kb), "search", "oauth"]
    )
    assert result.exit_code == 0
    assert "oauth-flow" in result.output

    result = runner.invoke(cli, ["--kb-path", str(integration_kb), "stats"])
    assert result.exit_code == 0
    assert "Total modules: 1" in result.output

    result = runner.invoke(
        cli,
        ["--kb-path", str(integration_kb), "show", "oauth-flow", "-c", "auth"],
    )
    assert result.exit_code == 0
    assert "oauth-flow" in result.output

    result = runner.invoke(
        cli,
        [
            "--kb-path",
            str(integration_kb),
            "delete",
            "oauth-flow",
            "-c",
            "auth",
            "--yes",
        ],
    )
    assert result.exit_code == 0
    assert load_module("oauth-flow", "auth", integration_kb) is None

    index = load_index(integration_kb)
    assert index is not None
    assert index.stats.total_modules == 0


def test_config_workflow(runner, integration_kb):
    """config set -> get -> list."""
    result = runner.invoke(
        cli,
        [
            "--kb-path",
            str(integration_kb),
            "config",
            "set",
            "extraction.provider",
            "openai",
        ],
    )
    assert result.exit_code == 0

    result = runner.invoke(
        cli,
        [
            "--kb-path",
            str(integration_kb),
            "config",
            "get",
            "extraction.provider",
        ],
    )
    assert result.exit_code == 0
    assert "openai" in result.output

    result = runner.invoke(
        cli, ["--kb-path", str(integration_kb), "config", "list"]
    )
    assert result.exit_code == 0
    assert "llm_providers" in result.output


def test_rebuild_index_workflow(runner, integration_kb):
    """create modules on disk -> rebuild -> stats reflect them."""
    for i in range(3):
        save_module(make_module(f"mod-{i}", "test"), integration_kb)

    result = runner.invoke(cli, ["--kb-path", str(integration_kb), "rebuild"])
    assert result.exit_code == 0
    assert "3 modules" in result.output

    result = runner.invoke(cli, ["--kb-path", str(integration_kb), "stats"])
    assert result.exit_code == 0
    assert "Total modules: 3" in result.output


def test_extract_review_approve_workflow(runner, integration_kb):
    """add (mocked LLM) -> staged -> review approve -> module persisted."""
    src_file = integration_kb.parent / "notes.txt"
    src_file.write_text("Notes about JWT and OAuth flows.")

    extracted = [make_module("auth-jwt", "auth"), make_module("auth-oauth", "auth")]

    async def fake_extract(self, text, category, existing_categories=""):
        return extracted

    with patch("knowledge_manager.cli.Extractor.extract", new=fake_extract), patch(
        "knowledge_manager.cli.create_client"
    ) as mock_create:
        mock_create.return_value = AsyncMock()
        result = runner.invoke(
            cli,
            [
                "--kb-path",
                str(integration_kb),
                "add",
                str(src_file),
                "-c",
                "auth",
            ],
        )
    assert result.exit_code == 0
    assert "Extracted 2" in result.output

    staged = list_staging(integration_kb / ".staging")
    assert len(staged) == 2

    result = runner.invoke(
        cli, ["--kb-path", str(integration_kb), "review"], input="a\na\n"
    )
    assert result.exit_code == 0

    assert load_module("auth-jwt", "auth", integration_kb) is not None
    assert load_module("auth-oauth", "auth", integration_kb) is not None
    assert list_staging(integration_kb / ".staging") == []

    result = runner.invoke(cli, ["--kb-path", str(integration_kb), "stats"])
    assert "Total modules: 2" in result.output


def test_extract_review_reject_workflow(runner, integration_kb):
    """staged -> review reject -> nothing persisted, staging cleared."""
    save_to_staging(make_module("rejected", "draft"), integration_kb / ".staging")

    result = runner.invoke(
        cli, ["--kb-path", str(integration_kb), "review"], input="r\n"
    )
    assert result.exit_code == 0

    assert load_module("rejected", "draft", integration_kb) is None
    assert list_staging(integration_kb / ".staging") == []


def test_serve_command_wires_up(runner, integration_kb):
    """serve command should construct the MCP server without crashing."""
    save_module(make_module("hello", "general"), integration_kb)
    rebuild_index(integration_kb)

    with patch("knowledge_manager.mcp_server.create_server") as mock_create_server, patch(
        "knowledge_manager.cli.asyncio.run"
    ) as mock_run:
        mock_server = mock_create_server.return_value
        mock_server.run_stdio_async = AsyncMock()

        result = runner.invoke(cli, ["--kb-path", str(integration_kb), "serve"])

    assert result.exit_code == 0
    mock_create_server.assert_called_once()
    mock_run.assert_called_once()


def test_index_format_matches_schema(runner, integration_kb):
    """The on-disk index.json round-trips through the Index schema."""
    save_module(make_module("alpha", "core"), integration_kb)
    save_module(make_module("beta", "core"), integration_kb)
    save_module(make_module("gamma", "advanced"), integration_kb)
    rebuild_index(integration_kb)

    raw = (integration_kb / "index.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    assert "categories" in data
    assert "stats" in data
    assert data["stats"]["total_modules"] == 3
    assert data["stats"]["categories"] == 2

    index = Index.model_validate_json(raw)
    assert sorted(index.categories.keys()) == ["advanced", "core"]
