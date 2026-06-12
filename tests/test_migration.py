import json

from knowledge_manager.migration import dry_run_import


def test_dry_run_import_reports_creates_updates_and_skips(tmp_path):
    source_dump = tmp_path / "export.json"
    source_dump.write_text(
        json.dumps([{"id": "page-1", "title": "Runbook", "body": "text"}]),
        encoding="utf-8",
    )

    summary = dry_run_import(source_dump, source_kind="llm_wiki")

    assert summary.total_documents == 1
    assert summary.creates == 1
    assert summary.updates == 0
    assert summary.skips == 0
    assert summary.errors == []


def test_dry_run_import_reports_invalid_payload_shape(tmp_path):
    source_dump = tmp_path / "export.json"
    source_dump.write_text(json.dumps({"id": "page-1"}), encoding="utf-8")

    summary = dry_run_import(source_dump, source_kind="llm_wiki")

    assert summary.total_documents == 0
    assert summary.creates == 0
    assert "source payload must be a JSON array" in summary.errors
