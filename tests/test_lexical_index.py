from knowledge_manager.schemas import Index, Module, ModuleContent
from knowledge_manager.storage import delete_module, save_index, save_module


def test_lexical_index_is_written_to_temporary_sibling(tmp_path, monkeypatch):
    from pathlib import Path
    from knowledge_manager.lexical_index import build_lexical_index

    kb = tmp_path / "kb"
    kb.mkdir()
    writes = []
    real_write_text = Path.write_text

    def record_write_text(path, data, *args, **kwargs):
        if path.name == "lexical_index.json" or "lexical_index.json." in path.name:
            writes.append(path)
        return real_write_text(path, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", record_write_text)
    build_lexical_index(kb)

    assert writes
    assert writes[-1].suffix == ".tmp"


def test_lexical_index_returns_candidate_keys_for_query(tmp_path):
    from knowledge_manager.lexical_index import build_lexical_index, query_lexical_index

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="lexical index"), kb)
    save_module(
        Module(
            id="rollback-guide",
            category="ops",
            title="Rollback Guide",
            summary="Rollback summary.",
            content=ModuleContent(
                overview="Rollback safely during incidents.",
                details="Detailed rollback workflow and incident handling.",
            ),
        ),
        kb,
    )

    build_lexical_index(kb)
    keys = query_lexical_index(kb, "rollback incidents")

    assert "ops/rollback-guide" in keys


def test_save_module_updates_lexical_index_without_full_rebuild(tmp_path, monkeypatch):
    from knowledge_manager.lexical_index import build_lexical_index, query_lexical_index

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="incremental lexical index"), kb)
    save_module(
        Module(
            id="rollback-guide",
            category="ops",
            title="Rollback Guide",
            summary="Rollback summary.",
            content=ModuleContent(
                overview="Rollback safely during incidents.",
                details="Detailed rollback workflow and incident handling.",
            ),
        ),
        kb,
    )
    build_lexical_index(kb)

    def explode(*_args, **_kwargs):
        raise AssertionError("full lexical rebuild should not be used on save_module")

    monkeypatch.setattr("knowledge_manager.lexical_index.build_lexical_index", explode)
    save_module(
        Module(
            id="tenant-policy",
            category="policy",
            title="Tenant Isolation Policy",
            summary="Tenant isolation summary.",
            content=ModuleContent(
                overview="Tenant isolation overview.",
                details="Detailed tenant policy for boundary enforcement.",
            ),
        ),
        kb,
    )

    keys = query_lexical_index(kb, "tenant isolation")
    assert "policy/tenant-policy" in keys


def test_delete_module_updates_lexical_index_without_full_rebuild(tmp_path, monkeypatch):
    from knowledge_manager.lexical_index import build_lexical_index, query_lexical_index

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="incremental lexical index delete"), kb)
    save_module(
        Module(
            id="rollback-guide",
            category="ops",
            title="Rollback Guide",
            summary="Rollback summary.",
            content=ModuleContent(
                overview="Rollback safely during incidents.",
                details="Detailed rollback workflow and incident handling.",
            ),
        ),
        kb,
    )
    build_lexical_index(kb)

    def explode(*_args, **_kwargs):
        raise AssertionError("full lexical rebuild should not be used on delete_module")

    monkeypatch.setattr("knowledge_manager.lexical_index.build_lexical_index", explode)
    assert delete_module("rollback-guide", "ops", kb) is True

    keys = query_lexical_index(kb, "rollback incidents")
    assert "ops/rollback-guide" not in keys
