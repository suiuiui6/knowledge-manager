"""Integration tests covering full end-to-end workflows."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

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
        mock_create.return_value = MagicMock()
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
        mock_server.run_stdio_async = MagicMock()

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


def test_enterprise_ingest_eval_ops_flow(runner, integration_kb, monkeypatch, tmp_path):
    from knowledge_manager.confluence import ConfluencePage

    runner.invoke(
        cli,
        [
            "--kb-path",
            str(integration_kb),
            "source",
            "add-confluence",
            "team-docs",
            "--base-url",
            "https://example.atlassian.net/wiki",
            "--space-key",
            "ENG",
            "--email",
            "docs@example.com",
            "--token-env",
            "CONFLUENCE_API_TOKEN",
            "--category",
            "ops",
        ],
    )
    monkeypatch.setenv("CONFLUENCE_API_TOKEN", "token")

    async def fake_list_pages(self, space_key, root_page_id="", limit=25, cursor=""):
        return (
            [
                ConfluencePage(
                    page_id="12345",
                    title="JWT Runbook",
                    url="https://example.atlassian.net/wiki/spaces/ENG/pages/12345",
                    version="7",
                    body_text="Refresh tokens rotate on every successful refresh.",
                    heading_path=["ENG", "JWT Runbook"],
                    checksum="abc123",
                )
            ],
            "cursor-2",
        )

    async def fake_extract(self, text, category, existing_categories=""):
        return [make_module("jwt-playbook", category)]

    monkeypatch.setattr("knowledge_manager.confluence.ConfluenceClient.list_pages", fake_list_pages)
    monkeypatch.setattr("knowledge_manager.cli.Extractor.extract", fake_extract)
    monkeypatch.setattr("knowledge_manager.cli.create_client", lambda provider_name, provider_cfg: MagicMock())

    pull = runner.invoke(cli, ["--kb-path", str(integration_kb), "source", "pull", "team-docs"])
    assert pull.exit_code == 0
    assert "staged 1 modules" in pull.output

    review = runner.invoke(cli, ["--kb-path", str(integration_kb), "review"], input="a\n")
    assert review.exit_code == 0

    suite_path = tmp_path / "eval-suite.json"
    suite_path.write_text(
        json.dumps(
            {
                "name": "enterprise-flow",
                "cases": [
                    {
                        "id": "jwt-hit",
                        "query": "refresh tokens rotate",
                        "required_modules": ["ops/jwt-playbook"],
                        "top_k": 3,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    eval_run = runner.invoke(
        cli,
        ["--kb-path", str(integration_kb), "eval", "run", str(suite_path), "--top-k", "3"],
    )
    assert eval_run.exit_code == 0
    assert "Baseline win rate" in eval_run.output

    ops = runner.invoke(cli, ["--kb-path", str(integration_kb), "ops"])
    assert ops.exit_code == 0
    assert "Operations Report" in ops.output


def test_replacement_flow_import_ingest_eval_and_ops(runner, integration_kb, monkeypatch, tmp_path):
    from knowledge_manager.confluence import ConfluencePage

    export_path = tmp_path / "legacy-export.json"
    export_path.write_text(
        json.dumps([{"id": "page-1", "title": "Runbook", "body": "rollback safely"}]),
        encoding="utf-8",
    )

    dry_run = runner.invoke(
        cli,
        [
            "--kb-path",
            str(integration_kb),
            "migrate",
            "dry-run",
            str(export_path),
            "--source-kind",
            "llm_wiki",
        ],
    )
    assert dry_run.exit_code == 0
    assert '"total_documents": 1' in dry_run.output

    runner.invoke(
        cli,
        [
            "--kb-path",
            str(integration_kb),
            "source",
            "add-confluence",
            "team-docs",
            "--base-url",
            "https://example.atlassian.net/wiki",
            "--space-key",
            "ENG",
            "--email",
            "docs@example.com",
            "--token-env",
            "CONFLUENCE_API_TOKEN",
            "--category",
            "ops",
        ],
    )
    monkeypatch.setenv("CONFLUENCE_API_TOKEN", "token")

    async def fake_list_pages(self, space_key, root_page_id="", limit=25, cursor=""):
        return (
            [
                ConfluencePage(
                    page_id="12345",
                    title="JWT Runbook",
                    url="https://example.atlassian.net/wiki/spaces/ENG/pages/12345",
                    version="7",
                    body_text="Refresh tokens rotate on every successful refresh.",
                    heading_path=["ENG", "JWT Runbook"],
                    checksum="abc123",
                )
            ],
            "cursor-2",
        )

    async def fake_extract(self, text, category, existing_categories=""):
        return [make_module("jwt-playbook", category)]

    monkeypatch.setattr("knowledge_manager.confluence.ConfluenceClient.list_pages", fake_list_pages)
    monkeypatch.setattr("knowledge_manager.cli.Extractor.extract", fake_extract)
    monkeypatch.setattr("knowledge_manager.cli.create_client", lambda provider_name, provider_cfg: MagicMock())

    pull = runner.invoke(cli, ["--kb-path", str(integration_kb), "source", "pull", "team-docs"])
    assert pull.exit_code == 0
    assert "staged 1 modules" in pull.output

    review = runner.invoke(cli, ["--kb-path", str(integration_kb), "review"], input="a\n")
    assert review.exit_code == 0

    suite_path = tmp_path / "eval-suite.json"
    suite_path.write_text(
        json.dumps(
            {
                "name": "replacement-flow",
                "cases": [
                    {
                        "id": "jwt-hit",
                        "query": "refresh tokens rotate",
                        "required_modules": ["ops/jwt-playbook"],
                        "top_k": 3,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    eval_run = runner.invoke(
        cli,
        ["--kb-path", str(integration_kb), "eval", "run", str(suite_path), "--top-k", "3"],
    )
    assert eval_run.exit_code == 0
    assert "Baseline win rate" in eval_run.output

    ops = runner.invoke(cli, ["--kb-path", str(integration_kb), "ops", "--format", "json"])
    assert ops.exit_code == 0
    assert '"source_backlog"' in ops.output
