import json
import zipfile

import pytest


def test_benchmark_gate_rejects_fast_errors():
    from knowledge_manager.performance_benchmarks import _evaluate_gate_summary

    report = {"benchmarks": {"http": {"search_http": {"mean_ms": 1, "p95_ms": 1, "errors": ["RuntimeError"]}}}}
    assert _evaluate_gate_summary(report)["search_http"]["status"] == "fail"


def test_benchmark_seeds_without_per_module_index_rewrites(tmp_path, monkeypatch):
    from knowledge_manager import performance_benchmarks as perf

    calls = []
    monkeypatch.setattr(perf, "save_module", lambda *args, **kwargs: calls.append(kwargs))
    perf._seed_modules(perf.BenchmarkConfig(kb_path=tmp_path / "kb", output_dir=tmp_path / "out", module_count=4))
    assert not calls
    from knowledge_manager.storage import load_index
    assert sum(len(category.modules) for category in load_index(tmp_path / "kb").categories.values()) == 4


def test_backup_refuses_output_inside_source(tmp_path):
    from knowledge_manager.backup_restore import create_backup_bundle

    (tmp_path / "index.json").write_text("{}")
    with pytest.raises(ValueError, match="outside"):
        create_backup_bundle(tmp_path, tmp_path / "backups")


def test_restore_rejects_traversal_before_writing(tmp_path):
    from knowledge_manager.backup_restore import restore_backup_bundle

    bundle = tmp_path / "hostile.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"restore_policy": "empty-target-only"}))
        archive.writestr("kb/index.json", "{}")
        archive.writestr("kb/../escaped.txt", "escape")
    with pytest.raises(ValueError, match="Unsafe"):
        restore_backup_bundle(bundle, tmp_path / "restored")
    assert not (tmp_path / "escaped.txt").exists()
    assert not (tmp_path / "restored" / "index.json").exists()


def test_backup_validates_hashes_before_restore(tmp_path):
    from knowledge_manager.backup_restore import create_backup_bundle, restore_backup_bundle

    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "index.json").write_text("{}")
    original = create_backup_bundle(kb, tmp_path / "backups")
    corrupted = tmp_path / "corrupt.zip"
    with zipfile.ZipFile(original) as src, zipfile.ZipFile(corrupted, "w") as dst:
        for name in src.namelist():
            dst.writestr(name, b"corrupted" if name == "kb/index.json" else src.read(name))
    with pytest.raises(ValueError, match="checksum"):
        restore_backup_bundle(corrupted, tmp_path / "restored")
