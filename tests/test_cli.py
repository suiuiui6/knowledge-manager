import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from knowledge_manager.cli import cli
from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata
from knowledge_manager.storage import save_module, save_to_staging, save_index, rebuild_index
from knowledge_manager.schemas import Index


@pytest.fixture
def cli_runner():
    return CliRunner()


def make_module(id="test-mod", category="test") -> Module:
    return Module(
        id=id,
        category=category,
        title=f"Test Module {id}",
        summary="A summary describing the test module purpose",
        content=ModuleContent(
            overview="Overview that is long enough",
            details="Details that are definitely long enough to pass validation",
        ),
        metadata=ModuleMetadata(tags=["sample", "demo"]),
    )


@pytest.fixture
def kb_path(tmp_path):
    path = tmp_path / "kb"
    path.mkdir()
    return path


@pytest.fixture
def initialized_kb(cli_runner, tmp_path):
    path = tmp_path / "kb"
    cli_runner.invoke(cli, ["init", str(path)])
    return path


def test_cli_help(cli_runner):
    result = cli_runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Knowledge Manager" in result.output


def test_cli_version(cli_runner):
    result = cli_runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_cli_init_creates_knowledge_base(cli_runner, tmp_path):
    kb = tmp_path / "kb"
    result = cli_runner.invoke(cli, ["init", str(kb)])
    assert result.exit_code == 0
    assert "Initialized" in result.output
    assert kb.exists()
    assert (kb / "index.json").exists()
    assert (kb / "config.json").exists()
    assert (kb / ".staging").exists()


def test_cli_init_already_exists(cli_runner, tmp_path):
    kb = tmp_path / "kb"
    cli_runner.invoke(cli, ["init", str(kb)])
    result = cli_runner.invoke(cli, ["init", str(kb)])
    assert result.exit_code != 0
    assert "already" in result.output.lower()


def test_cli_list_empty(cli_runner, initialized_kb):
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "list"])
    assert result.exit_code == 0


def test_cli_list_modules(cli_runner, initialized_kb):
    save_module(make_module("auth-jwt", "auth"), initialized_kb)
    rebuild_index(initialized_kb)
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "list"])
    assert result.exit_code == 0
    assert "auth-jwt" in result.output


def test_cli_list_by_category(cli_runner, initialized_kb):
    save_module(make_module("auth-jwt", "auth"), initialized_kb)
    save_module(make_module("db-conn", "database"), initialized_kb)
    rebuild_index(initialized_kb)
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "list", "-c", "auth"])
    assert result.exit_code == 0
    assert "auth-jwt" in result.output
    assert "db-conn" not in result.output


def test_cli_stats(cli_runner, initialized_kb):
    save_module(make_module("auth-jwt", "auth"), initialized_kb)
    rebuild_index(initialized_kb)
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "stats"])
    assert result.exit_code == 0
    assert "Total modules" in result.output
    assert "1" in result.output


def test_cli_search(cli_runner, initialized_kb):
    save_module(make_module("auth-jwt", "auth"), initialized_kb)
    save_module(make_module("db-conn", "database"), initialized_kb)
    rebuild_index(initialized_kb)
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "search", "auth"])
    assert result.exit_code == 0
    assert "auth-jwt" in result.output


def test_cli_rebuild(cli_runner, initialized_kb):
    save_module(make_module("auth-jwt", "auth"), initialized_kb)
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "rebuild"])
    assert result.exit_code == 0
    assert "Rebuilt" in result.output or "rebuilt" in result.output.lower()


def test_cli_delete_with_confirm(cli_runner, initialized_kb):
    save_module(make_module("auth-jwt", "auth"), initialized_kb)
    rebuild_index(initialized_kb)
    result = cli_runner.invoke(
        cli,
        ["--kb-path", str(initialized_kb), "delete", "auth-jwt", "-c", "auth", "--yes"],
    )
    assert result.exit_code == 0
    assert not (initialized_kb / "auth" / "auth-jwt.json").exists()


def test_cli_delete_not_found(cli_runner, initialized_kb):
    result = cli_runner.invoke(
        cli,
        ["--kb-path", str(initialized_kb), "delete", "missing", "-c", "auth", "--yes"],
    )
    assert result.exit_code != 0


def test_cli_show_module(cli_runner, initialized_kb):
    save_module(make_module("auth-jwt", "auth"), initialized_kb)
    result = cli_runner.invoke(
        cli, ["--kb-path", str(initialized_kb), "show", "auth-jwt", "-c", "auth"]
    )
    assert result.exit_code == 0
    assert "auth-jwt" in result.output


def test_cli_config_list(cli_runner, initialized_kb):
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "config", "list"])
    assert result.exit_code == 0


def test_cli_config_set_get(cli_runner, initialized_kb):
    set_result = cli_runner.invoke(
        cli,
        [
            "--kb-path",
            str(initialized_kb),
            "config",
            "set",
            "extraction.provider",
            "claude",
        ],
    )
    assert set_result.exit_code == 0
    get_result = cli_runner.invoke(
        cli,
        ["--kb-path", str(initialized_kb), "config", "get", "extraction.provider"],
    )
    assert get_result.exit_code == 0
    assert "claude" in get_result.output


def test_cli_add_extracts_to_staging(cli_runner, initialized_kb, tmp_path):
    src_file = tmp_path / "notes.txt"
    src_file.write_text("Some notes about JWT authentication.")

    sample = make_module("auth-jwt", "auth")

    async def fake_extract(self, text, category):
        return [sample]

    with patch("knowledge_manager.cli.Extractor.extract", new=fake_extract):
        with patch("knowledge_manager.cli.create_client") as mock_create:
            mock_create.return_value = AsyncMock()
            result = cli_runner.invoke(
                cli,
                [
                    "--kb-path",
                    str(initialized_kb),
                    "add",
                    str(src_file),
                    "-c",
                    "auth",
                ],
            )

    assert result.exit_code == 0, result.output
    assert "Extracted" in result.output or "extracted" in result.output.lower()
    staging_files = list((initialized_kb / ".staging").glob("*.json"))
    assert len(staging_files) == 1


def test_cli_add_file_not_found(cli_runner, initialized_kb):
    result = cli_runner.invoke(
        cli,
        [
            "--kb-path",
            str(initialized_kb),
            "add",
            "no-such-file.txt",
            "-c",
            "general",
        ],
    )
    assert result.exit_code != 0


def test_cli_review_approve(cli_runner, initialized_kb):
    sample = make_module("auth-jwt", "auth")
    save_to_staging(sample, initialized_kb / ".staging")

    result = cli_runner.invoke(
        cli, ["--kb-path", str(initialized_kb), "review"], input="a\n"
    )
    assert result.exit_code == 0
    assert (initialized_kb / "auth" / "auth-jwt.json").exists()
    assert not (initialized_kb / ".staging" / "auth-jwt.json").exists()


def test_cli_review_reject(cli_runner, initialized_kb):
    sample = make_module("auth-jwt", "auth")
    save_to_staging(sample, initialized_kb / ".staging")

    result = cli_runner.invoke(
        cli, ["--kb-path", str(initialized_kb), "review"], input="r\n"
    )
    assert result.exit_code == 0
    assert not (initialized_kb / "auth" / "auth-jwt.json").exists()
    assert not (initialized_kb / ".staging" / "auth-jwt.json").exists()


def test_cli_review_skip(cli_runner, initialized_kb):
    sample = make_module("auth-jwt", "auth")
    save_to_staging(sample, initialized_kb / ".staging")

    result = cli_runner.invoke(
        cli, ["--kb-path", str(initialized_kb), "review"], input="s\n"
    )
    assert result.exit_code == 0
    # Skipped — should remain in staging
    assert (initialized_kb / ".staging" / "auth-jwt.json").exists()


def test_cli_review_empty_staging(cli_runner, initialized_kb):
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "review"])
    assert result.exit_code == 0
    assert "No" in result.output or "no" in result.output.lower()
