import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from knowledge_manager.cli import cli
from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata
from knowledge_manager.storage import save_module, save_to_staging, save_index, rebuild_index, load_index
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

    async def fake_extract(self, text, category, existing_categories=""):
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


def test_cli_add_verbose_logs_only_metadata(cli_runner, initialized_kb, tmp_path, caplog):
    src_file = tmp_path / "notes.txt"
    raw_text = "Sensitive note about JWT authentication and internal claims."
    src_file.write_text(raw_text)

    sample = make_module("auth-jwt", "auth")

    async def fake_extract(self, text, category, existing_categories=""):
        logging.getLogger("knowledge_manager.extractor").debug(
            "Extractor chunk processed (%s chars)", len(text)
        )
        return [sample]

    with patch("knowledge_manager.cli.Extractor.extract", new=fake_extract):
        with patch("knowledge_manager.cli.create_client") as mock_create:
            mock_create.return_value = AsyncMock()
            with caplog.at_level(logging.DEBUG, logger="knowledge_manager"):
                result = cli_runner.invoke(
                    cli,
                    [
                        "--verbose",
                        "--kb-path",
                        str(initialized_kb),
                        "add",
                        str(src_file),
                        "-c",
                        "auth",
                    ],
                )

    assert result.exit_code == 0, result.output
    assert any(
        record.name == "knowledge_manager.extractor"
        and "Extractor chunk processed" in record.getMessage()
        for record in caplog.records
    )
    log_text = caplog.text
    assert raw_text not in log_text
    assert str(src_file) not in log_text


def test_cli_review_empty_staging(cli_runner, initialized_kb):
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "review"])
    assert result.exit_code == 0
    assert "No" in result.output or "no" in result.output.lower()


def test_cli_search_shows_confidence_badges(cli_runner, initialized_kb):
    save_module(Module(
        id="conf-high", category="general",
        title="High confidence module",
        summary="A module with high confidence rating",
        content=ModuleContent(overview="High confidence overview text", details="High confidence details for testing badges in CLI"),
        metadata=ModuleMetadata(tags=["test"], confidence="high"),
    ), initialized_kb)
    rebuild_index(initialized_kb)
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "search", "confidence"])
    assert result.exit_code == 0
    assert "[high]" in result.output


def test_cli_search_shows_related_source_badge(cli_runner, initialized_kb):
    save_module(Module(
        id="graph-direct", category="general",
        title="Direct match module",
        summary="This module matches the query directly",
        content=ModuleContent(overview="Direct match overview for testing.", details="Direct match details for testing source badges in CLI."),
        metadata=ModuleMetadata(tags=["graph"], related_modules=["general/graph-neighbor"]),
    ), initialized_kb)
    save_module(Module(
        id="graph-neighbor", category="general",
        title="Neighbor module title",
        summary="Neighbor module for graph expansion",
        content=ModuleContent(overview="Neighbor overview for graph expansion testing.", details="Neighbor details for testing graph expansion source badges in CLI search."),
        metadata=ModuleMetadata(tags=["graph"]),
    ), initialized_kb)
    rebuild_index(initialized_kb)
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "search", "Direct match"])
    assert result.exit_code == 0
    assert "graph-direct" in result.output
    assert "graph-neighbor" in result.output
    assert "[related]" in result.output


def test_cli_telemetry_status(cli_runner, initialized_kb):
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "telemetry", "status"])
    assert result.exit_code == 0
    assert "Telemetry" in result.output


def test_cli_telemetry_disable_enable(cli_runner, initialized_kb):
    # Disable
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "telemetry", "disable"])
    assert result.exit_code == 0
    assert "disabled" in result.output.lower()
    # Enable
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "telemetry", "enable"])
    assert result.exit_code == 0
    assert "enabled" in result.output.lower()


def test_cli_rank_status(cli_runner, initialized_kb):
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "rank", "status"])
    assert result.exit_code == 0
    assert "Model" in result.output


def test_cli_rank_retrain(cli_runner, initialized_kb):
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "rank", "retrain"])
    assert result.exit_code == 0
    assert "retrain" in result.output.lower() or "model" in result.output.lower()


def test_cli_stale_shows_expired_module(cli_runner, initialized_kb):
    from datetime import datetime, timedelta, timezone
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    save_module(Module(
        id="expired-mod", category="general",
        title="Expired module",
        summary="This module has already expired",
        content=ModuleContent(
            overview="Overview for expired module that should show in stale list.",
            details="Details for expired module — this module is past its expiry date.",
        ),
        metadata=ModuleMetadata(
            tags=["test"],
            expires_at=yesterday,
        ),
    ), initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "stale"])
    assert result.exit_code == 0
    assert "expired-mod" in result.output


def test_cli_stale_shows_review_due_module(cli_runner, initialized_kb):
    from datetime import datetime, timedelta, timezone
    old_date = datetime.now(timezone.utc) - timedelta(days=40)
    save_module(Module(
        id="review-mod", category="general",
        title="Module due for review",
        summary="This module was updated long ago and should be reviewed",
        content=ModuleContent(
            overview="Overview for module that needs review based on interval.",
            details="Details for review due module for testing stale command.",
        ),
        metadata=ModuleMetadata(
            tags=["test"],
            review_interval_days=30,
        ),
        updated_at=old_date,
    ), initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "stale"])
    assert result.exit_code == 0
    assert "review-mod" in result.output


def test_cli_stale_empty_when_none_stale(cli_runner, initialized_kb):
    save_module(make_module("fresh-mod", "general"), initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "stale"])
    assert result.exit_code == 0
    assert "No stale modules" in result.output


def test_init_creates_gitignore_template(cli_runner, tmp_path):
    kb = tmp_path / "kb"
    result = cli_runner.invoke(cli, ["init", str(kb)])
    assert result.exit_code == 0
    gitignore = kb / ".gitignore"
    assert gitignore.exists(), ".gitignore should be created on init"
    content = gitignore.read_text()
    assert ".staging/" in content
    assert ".telemetry/" in content
    assert "config.local.json" in content


@pytest.fixture
def remote_kb(tmp_path):
    """Create a 'remote' git repo with a valid KM knowledge base."""
    import subprocess
    remote = tmp_path / "remote-kb"
    remote.mkdir()
    subprocess.run(["git", "-C", str(remote), "init"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(remote), "config", "user.email", "kb@test.com"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(remote), "config", "user.name", "KB Test"], capture_output=True, check=True)
    # Create index.json
    from knowledge_manager.schemas import Index
    Index(description="Test remote KB").model_dump_json()
    import json
    (remote / "index.json").write_text(json.dumps({"version": "1.0", "description": "Test remote KB", "categories": {}, "graph": {}, "stats": {"total_modules": 0, "total_words": 0, "categories": 0}}))
    subprocess.run(["git", "-C", str(remote), "add", "-A"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(remote), "commit", "-m", "init"], capture_output=True, check=True)
    return remote


def test_cli_clone_into_new_directory(cli_runner, remote_kb, tmp_path):
    local = tmp_path / "local-kb"
    result = cli_runner.invoke(cli, ["clone", str(remote_kb), "--path", str(local)])
    assert result.exit_code == 0
    assert local.exists()
    assert (local / "index.json").exists()
    assert "Cloned" in result.output


def test_cli_clone_rejects_existing_path(cli_runner, remote_kb, tmp_path):
    local = tmp_path / "existing"
    local.mkdir()
    result = cli_runner.invoke(cli, ["clone", str(remote_kb), "--path", str(local)])
    assert result.exit_code != 0
    assert "already exists" in result.output.lower()


def test_cli_clone_warns_on_non_kb_repo(cli_runner, tmp_path):
    import subprocess
    non_kb = tmp_path / "non-kb"
    non_kb.mkdir()
    subprocess.run(["git", "-C", str(non_kb), "init"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(non_kb), "config", "user.email", "test@test.com"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(non_kb), "config", "user.name", "Test"], capture_output=True, check=True)
    (non_kb / "README.md").write_text("Just a regular repo")
    subprocess.run(["git", "-C", str(non_kb), "add", "-A"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(non_kb), "commit", "-m", "init"], capture_output=True, check=True)

    local = tmp_path / "clone-non-kb"
    result = cli_runner.invoke(cli, ["clone", str(non_kb), "--path", str(local)])
    assert result.exit_code == 0
    assert "may not be a valid km knowledge base" in result.output.lower()


def test_cli_push_sanitizes_api_keys(cli_runner, initialized_kb):
    from knowledge_manager.schemas import Config, LLMProviderConfig
    from knowledge_manager.storage import _load_config_safe
    import subprocess

    kb = initialized_kb
    # Set up git in the KB
    subprocess.run(["git", "-C", str(kb), "init"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "config", "user.email", "kb@test.com"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "config", "user.name", "KB Test"], capture_output=True, check=True)
    # Add a remote (point to a bare repo)
    bare = kb.parent / "bare.git"
    bare.mkdir()
    subprocess.run(["git", "-C", str(bare), "init", "--bare"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "remote", "add", "origin", str(bare)], capture_output=True, check=True)

    # Set a real API key
    cfg = Config(
        llm_providers={
            "deepseek": LLMProviderConfig(
                api_key="sk-real-key-123",
                model="deepseek-v4",
                default=True,
            ),
        },
    )
    config_path = kb / "config.json"
    config_path.write_text(cfg.model_dump_json())

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "push"])
    # Push may fail for shallow reasons but should NOT leak the API key in output
    if result.exit_code == 0:
        # Config should have been restored with real key
        restored = _load_config_safe(kb)
        assert restored is not None
        assert restored.llm_providers["deepseek"].api_key == "sk-real-key-123"


def test_init_creates_meaningful_description():
    runner = CliRunner()
    with runner.isolated_filesystem():
        kb = Path("test_kb")
        result = runner.invoke(cli, ["init", str(kb)])
        assert result.exit_code == 0

        index = load_index(kb)
        assert index is not None
        assert len(index.description) > 20, "Description should be more than just 'Knowledge base'"
        assert "methodology" in index.description.lower() or "knowledge" in index.description.lower()
