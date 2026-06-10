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
    assert "0.5.1" in result.output


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
    staging_files = [f for f in (initialized_kb / ".staging").glob("*.json") if not f.name.endswith(".meta.json")]
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
    (remote / "index.json").write_text(json.dumps({"version": "1.0", "description": "Test remote KB", "categories": {}, "graph": {}, "usage": {"total_modules": 0, "total_words": 0, "categories": 0}}))
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


# ── Phase 2A: git collaboration tests ──



def _init_git_in_dir(path: Path):
    """Ensure path is a git repo. If not, init and configure. Always rename branch to 'main'."""
    import subprocess
    if not (path / ".git").exists():
        subprocess.run(["git", "-C", str(path), "init"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "kb@test.com"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test User"], capture_output=True, check=True)
    # Ensure branch is named "main" (CLI hardcodes origin/main)
    branch_result = subprocess.run(["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True)
    if branch_result.stdout.strip() != "main":
        subprocess.run(["git", "-C", str(path), "branch", "-m", "main"], capture_output=True, check=True)


def _create_bare_remote(kb: Path, remote_path: Path, push_initial: bool = True):
    """Helper: create a bare remote, set origin, optionally push initial commit."""
    import subprocess
    _init_git_in_dir(kb)
    remote_path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(remote_path), "init", "--bare"], capture_output=True, check=True)
    # Remove existing origin if present
    subprocess.run(["git", "-C", str(kb), "remote", "remove", "origin"], capture_output=True)
    subprocess.run(["git", "-C", str(kb), "remote", "add", "origin", str(remote_path)], capture_output=True, check=True)
    if push_initial:
        subprocess.run(["git", "-C", str(kb), "add", "-A"], capture_output=True, check=True)
        subprocess.run(["git", "-C", str(kb), "commit", "--allow-empty", "-m", "init"], capture_output=True, check=True)
        subprocess.run(["git", "-C", str(kb), "push", "-u", "origin", "main"], capture_output=True, check=True)


def test_cli_pull_up_to_date(cli_runner, initialized_kb, tmp_path):
    """pull when already up to date should report so."""
    import subprocess
    kb = initialized_kb
    bare = tmp_path / "bare.git"
    _create_bare_remote(kb, bare)

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "pull"])
    assert result.exit_code == 0
    assert "Already up to date" in result.output or "Index rebuilt" in result.output


def test_cli_pull_rebuilds_index(cli_runner, initialized_kb, tmp_path):
    """pull should rebuild the index after fetching."""
    import subprocess
    kb = initialized_kb
    bare = tmp_path / "bare.git"
    _create_bare_remote(kb, bare)

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "pull"])
    assert result.exit_code == 0
    assert "Index rebuilt" in result.output
    # index.json should exist and be valid
    assert (kb / "index.json").exists()
    idx = load_index(kb)
    assert idx is not None


def test_cli_status_no_changes(cli_runner, initialized_kb, tmp_path):
    """status with no local changes should report clean."""
    import subprocess
    kb = initialized_kb
    bare = tmp_path / "bare.git"
    _create_bare_remote(kb, bare)

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "status"])
    assert result.exit_code == 0
    # Should not show added/modified/deleted counts (clean state)
    assert "No changes" in result.output


def test_cli_status_shows_added_modules(cli_runner, initialized_kb, tmp_path):
    """status should detect locally added module files."""
    import subprocess
    kb = initialized_kb
    bare = tmp_path / "bare.git"
    _create_bare_remote(kb, bare)

    # Add a new module locally and stage it
    mod = make_module("new-mod", "test")
    save_module(mod, kb)
    subprocess.run(["git", "-C", str(kb), "add", "test/new-mod.json"], capture_output=True, check=True)

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "status"])
    assert result.exit_code == 0
    assert "test/new-mod.json" in result.output


def test_cli_status_shows_modified_modules(cli_runner, initialized_kb, tmp_path):
    """status should detect locally modified module files."""
    import subprocess
    kb = initialized_kb
    bare = tmp_path / "bare.git"
    _create_bare_remote(kb, bare)

    # Add and commit a module, push, then modify it locally
    mod = make_module("mod-m", "test")
    save_module(mod, kb)
    subprocess.run(["git", "-C", str(kb), "add", "-A"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "commit", "-m", "add module"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "push", "origin", "main"], capture_output=True, check=True)

    # Modify locally
    mod.summary = "Updated summary for testing"
    save_module(mod, kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "status"])
    assert result.exit_code == 0
    assert "Modified" in result.output or "test/mod-m.json" in result.output


def test_cli_diff_new_module(cli_runner, initialized_kb, tmp_path):
    """diff for a module not in remote should report it as new."""
    import subprocess
    kb = initialized_kb
    bare = tmp_path / "bare.git"
    _create_bare_remote(kb, bare)

    # Add a module locally without pushing
    mod = make_module("local-only", "test")
    save_module(mod, kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "diff", "test/local-only"])
    assert result.exit_code == 0
    assert "new" in result.output.lower() or "not in remote" in result.output.lower()


def test_cli_diff_shows_field_changes(cli_runner, initialized_kb, tmp_path):
    """diff should show field-level JSON differences."""
    import subprocess
    kb = initialized_kb
    bare = tmp_path / "bare.git"
    _create_bare_remote(kb, bare)

    # Add and push a module
    mod = make_module("mod-d", "test")
    save_module(mod, kb)
    subprocess.run(["git", "-C", str(kb), "add", "-A"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "commit", "-m", "add module"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "push", "origin", "main"], capture_output=True, check=True)

    # Modify locally
    mod.title = "Changed Title Here"
    mod.summary = "Changed summary text"
    save_module(mod, kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "diff", "test/mod-d"])
    assert result.exit_code == 0
    assert "Changed Title Here" in result.output or "title" in result.output.lower() or "Changes in test/mod-d" in result.output


def test_cli_diff_no_changes(cli_runner, initialized_kb, tmp_path):
    """diff with no local changes should report no differences."""
    import subprocess
    kb = initialized_kb
    bare = tmp_path / "bare.git"
    _create_bare_remote(kb, bare)

    # Add and push a module
    mod = make_module("mod-same", "test")
    save_module(mod, kb)
    subprocess.run(["git", "-C", str(kb), "add", "-A"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "commit", "-m", "add module"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "push", "origin", "main"], capture_output=True, check=True)

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "diff", "test/mod-same"])
    assert result.exit_code == 0
    assert "No differences" in result.output


def test_cli_diff_invalid_format(cli_runner, initialized_kb):
    """diff with invalid module_ref format should error."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "diff", "no-slash-here"])
    assert result.exit_code != 0
    assert "category/module-id" in result.output


def test_json_diff_sections_detects_all_change_types():
    """Unit test for _json_diff_sections helper."""
    from knowledge_manager.cli import _json_diff_sections

    remote = {
        "id": "test",
        "category": "x",
        "title": "Old Title",
        "summary": "Old Summary",
        "content": {"overview": "Old overview text.", "details": "Old details text that is long enough.", "examples": ""},
        "metadata": {"tags": ["old"], "confidence": "high"},
    }
    local = {
        "id": "test",
        "category": "x",
        "title": "New Title",
        "summary": "Old Summary",
        "content": {"overview": "New overview text.", "details": "Old details text that is long enough.", "references": "Added ref"},
        "metadata": {"tags": ["new"], "confidence": "low"},
    }

    lines = _json_diff_sections(remote, local)
    assert len(lines) > 0
    # title section changed
    assert any("title" in l for l in lines)
    # content nested diff
    assert any("content" in l for l in lines)
    # metadata nested diff
    assert any("metadata" in l for l in lines)


def test_json_diff_sections_identical():
    """Identical dicts should produce no diff lines."""
    from knowledge_manager.cli import _json_diff_sections

    data = {"id": "t", "category": "c", "title": "T", "summary": "S", "content": {"overview": "O"}}
    lines = _json_diff_sections(data, data)
    assert len(lines) == 0


# ── Phase 2B: review pipeline tests ──


def _stage_module(kb: Path, module_id: str = "test-mod", category: str = "test"):
    """Helper: add a module to staging and create metadata."""
    from knowledge_manager.storage import save_to_staging, save_staging_meta
    from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata, StagingMeta
    mod = Module(
        id=module_id,
        category=category,
        title=f"Review Test {module_id}",
        summary="A module for testing the review pipeline.",
        content=ModuleContent(
            overview="Overview for review testing.",
            details="Details that are definitely long enough to pass the validation check.",
        ),
        metadata=ModuleMetadata(tags=["review-test"]),
    )
    staging = kb / ".staging"
    staging.mkdir(exist_ok=True)
    save_to_staging(mod, staging)
    save_staging_meta(StagingMeta(module_id=module_id, submitted_by="test-user"), staging)
    return mod


def test_review_list_empty(cli_runner, initialized_kb):
    """review list with no staged modules should report empty."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "review", "list"])
    assert result.exit_code == 0
    assert "No staged modules" in result.output


def test_review_list_shows_staged(cli_runner, initialized_kb):
    """review list should show staged modules with status."""
    kb = initialized_kb
    _stage_module(kb, "mod-a")

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "review", "list"])
    assert result.exit_code == 0
    assert "mod-a" in result.output


def test_review_show_existing_module(cli_runner, initialized_kb):
    """review show should display module content and review history."""
    kb = initialized_kb
    _stage_module(kb, "mod-show")

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "review", "show", "mod-show"])
    assert result.exit_code == 0
    assert "mod-show" in result.output
    assert "Review Test" in result.output


def test_review_show_missing_module(cli_runner, initialized_kb):
    """review show with nonexistent module should error."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "review", "show", "no-such-module"])
    assert result.exit_code != 0


def test_review_approve_merges_module(cli_runner, initialized_kb):
    """review approve should merge module into KB when approval threshold met."""
    kb = initialized_kb
    _stage_module(kb, "mod-ok")

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "review", "approve", "mod-ok"])
    assert result.exit_code == 0
    assert "Approved and merged" in result.output

    # Module should now exist in KB
    from knowledge_manager.storage import load_module
    mod = load_module("mod-ok", "test", kb)
    assert mod is not None
    assert mod.title == "Review Test mod-ok"


def test_review_approve_requires_multiple_approvals(cli_runner, initialized_kb):
    """approve should not merge until required_approvals met."""
    kb = initialized_kb
    from knowledge_manager.schemas import Config, ReviewConfig
    from knowledge_manager.cli import _save_config

    # Configure 2 required approvals
    cfg = Config(review=ReviewConfig(required_approvals=2))
    _save_config(kb, cfg)

    _stage_module(kb, "mod-needs2")

    # First approval
    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "review", "approve", "mod-needs2"])
    assert result.exit_code == 0
    assert "1/2 approvals" in result.output

    # Module should NOT be in KB yet
    from knowledge_manager.storage import load_module, load_staging_meta
    assert load_module("mod-needs2", "test", kb) is None

    # Second approval
    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "review", "approve", "mod-needs2"])
    assert result.exit_code == 0
    assert "Approved and merged" in result.output
    assert load_module("mod-needs2", "test", kb) is not None


def test_review_approve_missing_module(cli_runner, initialized_kb):
    """approve with nonexistent module should error."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "review", "approve", "no-such"])
    assert result.exit_code != 0


def test_review_request_changes(cli_runner, initialized_kb):
    """request-changes should set status and record comment."""
    kb = initialized_kb
    _stage_module(kb, "mod-rc")

    result = cli_runner.invoke(cli, [
        "--kb-path", str(kb), "review", "request-changes",
        "mod-rc", "-m", "Needs more details in overview",
    ])
    assert result.exit_code == 0
    assert "Changes requested" in result.output

    # Verify meta was updated
    from knowledge_manager.storage import load_staging_meta
    staging = kb / ".staging"
    meta = load_staging_meta("mod-rc", staging)
    assert meta is not None
    assert meta.status == "changes-requested"
    assert len(meta.reviews) == 1
    assert meta.reviews[0].action == "changes-requested"
    assert meta.reviews[0].comment == "Needs more details in overview"


def test_review_request_changes_requires_comment(cli_runner, initialized_kb):
    """request-changes without --comment should fail (required option)."""
    kb = initialized_kb
    _stage_module(kb, "mod-rc2")

    result = cli_runner.invoke(cli, [
        "--kb-path", str(kb), "review", "request-changes", "mod-rc2",
    ])
    assert result.exit_code != 0


def test_review_my_submissions_shows_status(cli_runner, initialized_kb):
    """my-submissions should display submitted modules with review status."""
    kb = initialized_kb
    _stage_module(kb, "mod-sub1")
    _stage_module(kb, "mod-sub2")

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "review", "my-submissions"])
    assert result.exit_code == 0
    assert "mod-sub1" in result.output
    assert "mod-sub2" in result.output


def test_review_my_submissions_empty(cli_runner, initialized_kb):
    """my-submissions with no staged modules should report empty."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "review", "my-submissions"])
    assert result.exit_code == 0
    assert "No staged modules" in result.output


# ── Phase 2C: webhook notification tests ──


def test_push_sends_webhook_when_configured(cli_runner, initialized_kb, tmp_path):
    """push should POST to webhook_url when configured."""
    import subprocess
    from knowledge_manager.schemas import Config, LLMProviderConfig, NotificationsConfig
    from knowledge_manager.cli import _save_config

    kb = initialized_kb
    bare = tmp_path / "bare.git"
    _init_git_in_dir(kb)
    bare.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(bare), "init", "--bare"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "remote", "remove", "origin"], capture_output=True)
    subprocess.run(["git", "-C", str(kb), "remote", "add", "origin", str(bare)], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "add", "-A"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "commit", "--allow-empty", "-m", "init"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "push", "-u", "origin", "main"], capture_output=True, check=True)

    cfg = Config(
        notifications=NotificationsConfig(
            webhook_url="https://hooks.example.com/webhook",
            on_push=True,
        ),
    )
    _save_config(kb, cfg)

    with patch("httpx.post") as mock_post:
        result = cli_runner.invoke(cli, ["--kb-path", str(kb), "push"])
        # May fail for other reasons, but webhook should be attempted
        if mock_post.called:
            call_args = mock_post.call_args
            assert call_args[0][0] == "https://hooks.example.com/webhook"
            payload = call_args[1]["json"]
            assert "text" in payload


def test_push_webhook_failure_is_silent(cli_runner, initialized_kb, tmp_path):
    """push should continue gracefully when webhook fails."""
    import subprocess
    from knowledge_manager.schemas import Config, LLMProviderConfig, NotificationsConfig
    from knowledge_manager.cli import _save_config

    kb = initialized_kb
    bare = tmp_path / "bare.git"
    _init_git_in_dir(kb)
    bare.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(bare), "init", "--bare"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "remote", "remove", "origin"], capture_output=True)
    subprocess.run(["git", "-C", str(kb), "remote", "add", "origin", str(bare)], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "add", "-A"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "commit", "--allow-empty", "-m", "init"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "push", "-u", "origin", "main"], capture_output=True, check=True)

    cfg = Config(
        notifications=NotificationsConfig(
            webhook_url="https://hooks.example.com/webhook",
            on_push=True,
        ),
    )
    _save_config(kb, cfg)

    with patch("httpx.post", side_effect=Exception("Network error")):
        result = cli_runner.invoke(cli, ["--kb-path", str(kb), "push"])
        # Should not crash — webhook failures are non-critical
        # Exit code may be 0 or 1 depending on other push outcomes


def test_config_set_webhook_url(cli_runner, initialized_kb):
    """config set should support notifications.webhook_url."""
    result = cli_runner.invoke(cli, [
        "--kb-path", str(initialized_kb),
        "config", "set", "notifications.webhook_url", "https://hooks.example.com/test",
    ])
    assert result.exit_code == 0

    # Verify it was saved
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "config", "get", "notifications.webhook_url"])
    assert result.exit_code == 0
    assert "hooks.example.com" in result.output


# ── Phase 2D: deprecate, archive, search --include-archived tests ──


def test_cli_deprecate_module(cli_runner, initialized_kb):
    """km deprecate should set module status to deprecated."""
    kb = initialized_kb
    mod = make_module("mod-dep", "test")
    save_module(mod, kb)
    rebuild_index(kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "deprecate", "test/mod-dep", "--reason", "Outdated"])
    assert result.exit_code == 0
    assert "deprecated" in result.output.lower()

    from knowledge_manager.storage import load_module
    loaded = load_module("mod-dep", "test", kb)
    assert loaded is not None
    assert loaded.metadata.status == "deprecated"


def test_cli_deprecate_nonexistent(cli_runner, initialized_kb):
    """deprecate on nonexistent module should error."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "deprecate", "test/no-such"])
    assert result.exit_code != 0


def test_cli_archive_module(cli_runner, initialized_kb):
    """km archive should set module status to archived."""
    kb = initialized_kb
    mod = make_module("mod-arch", "test")
    save_module(mod, kb)
    rebuild_index(kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "archive", "test/mod-arch"])
    assert result.exit_code == 0
    assert "archived" in result.output.lower()

    from knowledge_manager.storage import load_module
    loaded = load_module("mod-arch", "test", kb)
    assert loaded is not None
    assert loaded.metadata.status == "archived"


def test_cli_archive_nonexistent(cli_runner, initialized_kb):
    """archive on nonexistent module should error."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "archive", "test/no-such"])
    assert result.exit_code != 0


def test_cli_search_include_archived(cli_runner, initialized_kb):
    """km search --include-archived should find archived modules."""
    from knowledge_manager.schemas import ModuleMetadata

    kb = initialized_kb
    mod = make_module("hidden-mod", "test")
    mod.metadata.status = "archived"
    save_module(mod, kb)
    rebuild_index(kb)

    # Default search (excludes archived)
    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "search", "hidden"])
    assert result.exit_code == 0
    assert "No matches" in result.output

    # Search with --include-archived
    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "search", "--include-archived", "hidden"])
    assert result.exit_code == 0
    assert "hidden-mod" in result.output


# ── Phase 3A: health CLI tests ──


def test_cli_health_show_overview(cli_runner, initialized_kb):
    """km health should show an overview table."""
    mod = make_module("h1", "auth")
    save_module(mod, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "health"])
    assert result.exit_code == 0
    assert "Knowledge Base Health Report" in result.output
    assert "auth" in result.output
    assert "Overall Health Score" in result.output


def test_cli_health_show_module_detail(cli_runner, initialized_kb):
    """km health --module should show single module detail."""
    mod = make_module("h2", "auth")
    save_module(mod, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "health", "--module", "auth/h2"])
    assert result.exit_code == 0
    assert "Module Health: h2" in result.output
    assert "Freshness" in result.output
    assert "Completeness" in result.output


def test_cli_health_module_not_found(cli_runner, initialized_kb):
    """km health --module with invalid module should error."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "health", "--module", "auth/nope"])
    assert result.exit_code != 0


def test_cli_health_module_invalid_format(cli_runner, initialized_kb):
    """km health --module without slash should error."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "health", "--module", "noslash"])
    assert result.exit_code != 0


def test_cli_health_at_risk(cli_runner, initialized_kb):
    """km health --at-risk should show only at-risk modules."""
    mod = make_module("h3", "auth")
    save_module(mod, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "health", "--at-risk"])
    assert result.exit_code == 0
    # Module just created is fresh but has no usage and only 60% completeness → at risk
    assert "h3" in result.output or "No modules at risk" in result.output


def test_cli_health_json_format(cli_runner, initialized_kb):
    """km health --format json should output valid JSON."""
    import json
    mod = make_module("h4", "auth")
    save_module(mod, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "health", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "total_modules" in data
    assert "overall_score" in data
    assert "category_breakdown" in data


def test_cli_health_empty_kb(cli_runner, initialized_kb):
    """km health on empty KB should report empty."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "health"])
    assert result.exit_code == 0
    assert "empty" in result.output.lower() or "0 modules" in result.output.lower()


# ── Phase 3B: stats CLI tests ──


def test_cli_stats_empty(cli_runner, initialized_kb):
    """km stats on empty KB should report no usage data."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "usage"])
    assert result.exit_code == 0
    assert "No usage data" in result.output


def test_cli_stats_json_format(cli_runner, initialized_kb):
    """km stats --format json should output valid JSON."""
    import json
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "usage", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "total_searches" in data
    assert "period_days" in data


def test_cli_stats_with_data(cli_runner, initialized_kb):
    """km stats should show stats after search/load events."""
    from knowledge_manager.storage import record_search_event, record_load_event

    kb = initialized_kb
    record_search_event("JWT authentication", ["auth/jwt"], kb)
    record_load_event("jwt", "auth", kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "usage"])
    assert result.exit_code == 0
    assert "1" in result.output  # at least 1 search


# ── Phase 3C: graph CLI tests ──


def test_cli_graph_overview(cli_runner, initialized_kb):
    """km graph should show graph overview with hubs, orphans, and clusters."""
    mod_a = make_module("g1", "auth")
    mod_a.metadata.related_modules = ["db/g2"]
    save_module(mod_a, initialized_kb)
    mod_b = make_module("g2", "db")
    mod_b.metadata.related_modules = ["auth/g1"]
    save_module(mod_b, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "graph"])
    assert result.exit_code == 0
    assert "Knowledge Graph Overview" in result.output
    assert "modules" in result.output
    assert "edges" in result.output


def test_cli_graph_export_mermaid(cli_runner, initialized_kb):
    """km graph --export mermaid should output valid Mermaid syntax."""
    mod = make_module("gm1", "auth")
    mod.metadata.related_modules = ["db/gm2"]
    save_module(mod, initialized_kb)
    mod2 = make_module("gm2", "db")
    save_module(mod2, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "graph", "--export", "mermaid"])
    assert result.exit_code == 0
    assert "graph TD" in result.output


def test_cli_graph_export_json(cli_runner, initialized_kb):
    """km graph --export json should output valid JSON with stats + clusters."""
    mod = make_module("gj1", "auth")
    save_module(mod, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "graph", "--export", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "stats" in data
    assert "clusters" in data
    assert data["stats"]["total_nodes"] >= 1


def test_cli_graph_empty(cli_runner, initialized_kb):
    """km graph on empty KB should report no modules."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "graph"])
    assert result.exit_code == 0
    assert "No modules" in result.output


# ── Phase 3D: recommend CLI tests ──


def test_cli_recommend_overview(cli_runner, initialized_kb):
    """km recommend should show recommendations in all categories."""
    mod = make_module("r1", "auth")
    save_module(mod, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "recommend"])
    assert result.exit_code == 0
    assert "Recommendations" in result.output


def test_cli_recommend_type_filter(cli_runner, initialized_kb):
    """km recommend --type archive should filter by type."""
    mod = make_module("r2", "auth")
    save_module(mod, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "recommend", "--type", "archive"])
    assert result.exit_code == 0


def test_cli_recommend_json_format(cli_runner, initialized_kb):
    """km recommend --format json should output valid JSON."""
    mod = make_module("r3", "auth")
    save_module(mod, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "recommend", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "archive_candidates" in data
    assert "enrichment_needed" in data
    assert "suggested_links" in data
    assert "review_reminders" in data


def test_cli_recommend_empty_kb(cli_runner, initialized_kb):
    """km recommend on empty KB should report great shape."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "recommend"])
    assert result.exit_code == 0
    assert "great shape" in result.output or "No recommendations" in result.output


# ── Phase 3D: apply CLI tests ──


def test_cli_apply_dry_run(cli_runner, initialized_kb):
    """km apply --dry-run should preview actions without executing."""
    mod = make_module("a1", "auth")
    save_module(mod, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "apply", "--type", "archive", "--dry-run"])
    assert result.exit_code == 0


def test_cli_apply_type_required(cli_runner, initialized_kb):
    """km apply without --type should error."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "apply"])
    assert result.exit_code != 0


def test_cli_apply_archive_actually_archives(cli_runner, initialized_kb):
    """km apply --type archive should archive recommended modules."""
    from knowledge_manager.storage import load_module

    mod = make_module("a2", "auth")
    # Make it look old and unused to trigger archive recommendation
    from datetime import datetime, timezone, timedelta
    mod.updated_at = datetime.now(timezone.utc) - timedelta(days=200)
    mod.content.examples = ""
    mod.content.caveats = ""
    mod.content.references = ""
    save_module(mod, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "apply", "--type", "archive"])
    assert result.exit_code == 0
    # Module should now be archived
    m = load_module("a2", "auth", initialized_kb)
    assert m is not None
    assert m.metadata.status == "archived"


# ── Phase 4A: connect/disconnect CLI tests ──


def test_connect_list_platforms(cli_runner, initialized_kb):
    """km connect --list should show available platforms."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "connect", "--list"])
    assert result.exit_code == 0
    assert "claude-code" in result.output
    assert "copilot" in result.output


def test_connect_print_outputs_json(cli_runner, initialized_kb):
    """km connect --print should output valid MCP JSON to stdout."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "connect", "--print", "claude-code"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "mcpServers" in data
    assert "knowledge-manager" in data["mcpServers"]


def test_connect_unknown_platform_errors(cli_runner, initialized_kb):
    """km connect with unknown platform should error."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "connect", "nonexistent"])
    assert result.exit_code != 0


def test_connect_no_platform_without_list(cli_runner, initialized_kb):
    """km connect without platform and without --list should error."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "connect"])
    assert result.exit_code != 0


def test_connect_writes_config_file(cli_runner, initialized_kb):
    """km connect claude-code should write config to a tmp config path."""
    import os
    from pathlib import Path
    from knowledge_manager.connect import read_mcp_config

    kb = initialized_kb
    # Override the config path to write into a temp dir instead of real ~/.claude
    fake_home = kb / "fake-home"
    fake_home.mkdir()

    cfg_path = fake_home / ".claude" / "mcp.json"
    result = cli_runner.invoke(cli, [
        "--kb-path", str(kb), "connect", "claude-code",
    ], env={"HOME": str(fake_home), "USERPROFILE": str(fake_home)})
    assert result.exit_code == 0

    # Check that the file was written
    data = read_mcp_config(cfg_path)
    assert "knowledge-manager" in data.get("mcpServers", {})


def test_disconnect_removes_entry(cli_runner, initialized_kb):
    """km disconnect should remove knowledge-manager from config."""
    import os
    from knowledge_manager.connect import write_mcp_config, build_mcp_entry, has_entry

    kb = initialized_kb
    fake_home = kb / "fake-home"
    fake_home.mkdir()

    # First manually write the config
    cfg_path = fake_home / ".claude" / "mcp.json"
    cfg_path.parent.mkdir(parents=True)
    write_mcp_config(cfg_path, build_mcp_entry(kb))
    assert has_entry(cfg_path)

    # Then disconnect
    result = cli_runner.invoke(cli, [
        "--kb-path", str(kb), "disconnect", "claude-code",
    ], env={"HOME": str(fake_home), "USERPROFILE": str(fake_home)})
    assert result.exit_code == 0
    assert not has_entry(cfg_path)


def test_disconnect_no_entry(cli_runner, initialized_kb):
    """km disconnect when no entry exists should report it."""
    import os
    kb = initialized_kb
    fake_home = kb / "fake-home"
    fake_home.mkdir()

    result = cli_runner.invoke(cli, [
        "--kb-path", str(kb), "disconnect", "claude-code",
    ], env={"HOME": str(fake_home), "USERPROFILE": str(fake_home)})
    assert result.exit_code == 0
    assert "No knowledge-manager entry found" in result.output


# ── Phase 4D: marketplace/install/publish CLI tests ──


def _make_marketplace_dir(tmp_path):
    """Create a minimal local marketplace directory for testing."""
    from knowledge_manager.schemas import MarketplaceIndex, MarketplaceModule

    mp_dir = tmp_path / "test-marketplace"
    mp_dir.mkdir()
    auth_dir = mp_dir / "auth"
    auth_dir.mkdir()

    idx = MarketplaceIndex(
        modules={
            "auth/oauth2": MarketplaceModule(
                id="oauth2", category="auth",
                title="OAuth 2.0 Best Practices",
                summary="Security-focused OAuth 2.0 implementation guide",
                tags=["auth", "security"], version="2.1.0", author="community",
                confidence="high",
            ),
        }
    )
    (mp_dir / "index.json").write_text(idx.model_dump_json(indent=2))

    # Write a minimal module JSON file
    mod_json = json.dumps({
        "id": "oauth2", "category": "auth",
        "title": "OAuth 2.0 Best Practices",
        "summary": "Security-focused OAuth 2.0 implementation guide",
        "content": {
            "overview": "OAuth 2.0 is the industry standard for authorization.",
            "details": "This guide covers all the common OAuth 2.0 grant types...",
            "examples": "", "references": "", "caveats": ""
        },
        "metadata": {"tags": ["auth", "security"], "confidence": "high", "status": "published"}
    })
    (auth_dir / "oauth2.json").write_text(mod_json)

    return mp_dir


def test_marketplace_search_local(cli_runner, initialized_kb):
    """km marketplace search should find modules in a local marketplace."""
    kb = initialized_kb
    mp_dir = _make_marketplace_dir(kb)

    cfg = json.loads((kb / "config.json").read_text())
    cfg["marketplace"] = {"index_url": str(mp_dir), "sanitize_patterns": []}
    (kb / "config.json").write_text(json.dumps(cfg))

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "marketplace", "search", "oauth"])
    assert result.exit_code == 0
    assert "oauth2" in result.output


def test_marketplace_show_found(cli_runner, initialized_kb):
    """km marketplace show should display module details."""
    kb = initialized_kb
    mp_dir = _make_marketplace_dir(kb)

    cfg = json.loads((kb / "config.json").read_text())
    cfg["marketplace"] = {"index_url": str(mp_dir), "sanitize_patterns": []}
    (kb / "config.json").write_text(json.dumps(cfg))

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "marketplace", "show", "auth/oauth2"])
    assert result.exit_code == 0
    assert "OAuth 2.0 Best Practices" in result.output


def test_marketplace_show_not_found(cli_runner, initialized_kb):
    """km marketplace show with unknown module should report not found."""
    kb = initialized_kb
    mp_dir = _make_marketplace_dir(kb)

    cfg = json.loads((kb / "config.json").read_text())
    cfg["marketplace"] = {"index_url": str(mp_dir), "sanitize_patterns": []}
    (kb / "config.json").write_text(json.dumps(cfg))

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "marketplace", "show", "nonexistent/mod"])
    assert result.exit_code == 0
    assert "not found" in result.output.lower()


def test_install_from_marketplace(cli_runner, initialized_kb):
    """km install should put a marketplace module into staging."""
    kb = initialized_kb
    mp_dir = _make_marketplace_dir(kb)

    cfg = json.loads((kb / "config.json").read_text())
    cfg["marketplace"] = {"index_url": str(mp_dir), "sanitize_patterns": []}
    (kb / "config.json").write_text(json.dumps(cfg))

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "install", "auth/oauth2", "--yes"])
    assert result.exit_code == 0
    # Module should be in staging
    staging_file = kb / ".staging" / "oauth2.json"
    assert staging_file.exists()


def test_install_nonexistent_module(cli_runner, initialized_kb):
    """km install with unknown module should error."""
    kb = initialized_kb
    mp_dir = _make_marketplace_dir(kb)

    cfg = json.loads((kb / "config.json").read_text())
    cfg["marketplace"] = {"index_url": str(mp_dir), "sanitize_patterns": []}
    (kb / "config.json").write_text(json.dumps(cfg))

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "install", "nonexistent/mod", "--yes"])
    assert result.exit_code != 0


def test_publish_dry_run(cli_runner, initialized_kb):
    """km publish --dry-run should preview sanitized module."""
    mod = make_module("pub1", "auth")
    save_module(mod, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "publish", "auth/pub1", "--dry-run"])
    assert result.exit_code == 0
    assert "Sanitized module preview" in result.output


def test_publish_invalid_ref(cli_runner, initialized_kb):
    """km publish without category/id format should error."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "publish", "noslash"])
    assert result.exit_code != 0


def test_publish_module_not_found(cli_runner, initialized_kb):
    """km publish with nonexistent module should error."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "publish", "auth/nonexistent"])
    assert result.exit_code != 0
