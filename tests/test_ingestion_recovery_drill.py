import json
import sys

import pytest


def test_ingestion_drill_verifies_staging_and_input_recovery(tmp_path, monkeypatch):
    from scripts.run_ingestion_recovery_drill import main

    output = tmp_path / "report.json"
    monkeypatch.setattr(sys, "argv", ["drill", "--output", str(output)])
    assert main() == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["failed_status"] == "failed"
    assert report["failure_preserved_input"]
    assert report["attempt_count"] == 2
    assert report["staged_module_valid"]
    assert report["staging_metadata_present"]
    assert report["published_module_count"] == 0
    assert report["provider_mode"] == "deterministic fault injection"


def test_ingestion_drill_refuses_existing_knowledge_base(tmp_path, monkeypatch):
    from scripts.run_ingestion_recovery_drill import main

    kb = tmp_path / "existing"
    kb.mkdir()
    marker = kb / "index.json"
    marker.write_text("existing KB", encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv", ["drill", "--kb-path", str(kb), "--output", str(tmp_path / "report.json")]
    )
    with pytest.raises(ValueError, match="empty"):
        main()
    assert marker.read_text(encoding="utf-8") == "existing KB"
