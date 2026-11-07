import json

from click.testing import CliRunner

from knowledge_manager.cli import cli
from knowledge_manager.storage import list_modules, list_staging, load_index


def test_demo_creates_searchable_kb_without_api_key(tmp_path):
    runner = CliRunner()
    demo_path = tmp_path / "km-demo"

    result = runner.invoke(cli, ["demo", str(demo_path)])

    assert result.exit_code == 0, result.output
    assert "Created demo knowledge base" in result.output
    assert "approved modules" in result.output
    assert "staged for review" in result.output

    index = load_index(demo_path)
    assert index is not None
    assert index.stats.total_modules == 4
    assert index.stats.categories == 3
    assert len(list_modules(demo_path)) == 4
    assert [module.id for module in list_staging(demo_path / ".staging")] == [
        "staged-oncall-handoff"
    ]

    config = json.loads((demo_path / "config.json").read_text(encoding="utf-8"))
    assert config["llm_providers"]["deepseek"]["api_key"] == ""

    search_result = runner.invoke(
        cli,
        ["--kb-path", str(demo_path), "search", "rollback deployment"],
    )
    assert search_result.exit_code == 0, search_result.output
    assert "rollback-deployment" in search_result.output


def test_demo_refuses_non_empty_directory(tmp_path):
    runner = CliRunner()
    demo_path = tmp_path / "km-demo"
    demo_path.mkdir()
    (demo_path / "keep.txt").write_text("do not overwrite", encoding="utf-8")

    result = runner.invoke(cli, ["demo", str(demo_path)])

    assert result.exit_code != 0
    assert "not empty" in result.output.lower()
    assert (demo_path / "keep.txt").read_text(encoding="utf-8") == "do not overwrite"


def test_demo_defaults_to_km_demo_directory(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(cli, ["demo"])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "km-demo" / "index.json").is_file()
    assert load_index(tmp_path / "km-demo").stats.total_modules == 4
