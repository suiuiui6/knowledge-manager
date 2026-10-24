import json


def test_backup_restore_drill_rebuilds_and_searches_restored_kb(tmp_path):
    from knowledge_manager.schemas import Index, Module, ModuleContent
    from knowledge_manager.storage import save_index, save_module
    from scripts.run_backup_restore_drill import main

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="drill"), kb)
    (kb / "config.json").write_text(json.dumps({"llm_providers": {"local": {"api_key": "x", "model": "x", "default": True}}}), encoding="utf-8")
    save_module(Module(id="rollback", category="ops", title="Rollback runbook", summary="Rollback runbook summary text.", content=ModuleContent(overview="Rollback overview for recovery drill.", details="Rollback details long enough for the recovery drill.")), kb, defer_noncritical=False)
    output = tmp_path / "evidence"
    import sys

    original = sys.argv
    sys.argv = ["run_backup_restore_drill", "--kb-path", str(kb), "--output-dir", str(output)]
    try:
        assert main() == 0
    finally:
        sys.argv = original
    report = json.loads((output / "restore-verify-deployment.json").read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["search_overlap"]


def test_backup_restore_drill_uses_kb_content_instead_of_rollback_keyword(tmp_path, monkeypatch):
    from knowledge_manager.schemas import Index, Module, ModuleContent
    from knowledge_manager.storage import save_index, save_module
    from scripts.run_backup_restore_drill import main
    import sys

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="generic drill"), kb)
    (kb / "config.json").write_text(json.dumps({"llm_providers": {"local": {"api_key": "x", "model": "x", "default": True}}}), encoding="utf-8")
    save_module(Module(id="oauth", category="auth", title="OAuth authorization", summary="OAuth authorization summary.", content=ModuleContent(overview="OAuth authorization overview.", details="OAuth authorization details.")), kb, defer_noncritical=False)
    output = tmp_path / "evidence"
    monkeypatch.setattr(sys, "argv", ["drill", "--kb-path", str(kb), "--output-dir", str(output)])
    assert main() == 0
    report = json.loads((output / "restore-verify-deployment.json").read_text(encoding="utf-8"))
    assert report["source_module_count"] == 1
    assert report["restored_module_count"] == 1
    assert report["canonical_files_match"] is True
