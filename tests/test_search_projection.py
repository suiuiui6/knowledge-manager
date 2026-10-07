from __future__ import annotations

from pathlib import Path

from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata
from knowledge_manager.storage import save_index, save_module, search_modules


def test_search_projection_updates_on_save_without_full_scan(tmp_path, monkeypatch):
    from knowledge_manager.search_projection import build_search_projection, load_search_projection

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="projection test"), kb)
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
    build_search_projection(kb)

    def explode(*_args, **_kwargs):
        raise AssertionError("full projection rebuild should not run on save")

    monkeypatch.setattr("knowledge_manager.search_projection.build_search_projection", explode)
    save_module(
        Module(
            id="tenant-runbook",
            category="ops",
            title="Tenant Isolation Runbook",
            summary="Tenant isolation summary.",
            content=ModuleContent(
                overview="Contain tenant blast radius quickly.",
                details="Detailed isolation steps for multi-tenant incidents.",
            ),
        ),
        kb,
    )

    projection = load_search_projection(kb)
    assert "ops/tenant-runbook" in projection["documents"]


def test_search_modules_uses_projection_candidates_before_scoring(tmp_path, monkeypatch):
    from knowledge_manager.search_projection import build_search_projection

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="projection candidates"), kb)
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
    build_search_projection(kb)

    calls = {"count": 0}

    def tracked_list_modules(*_args, **_kwargs):
        calls["count"] += 1
        return []

    monkeypatch.setattr("knowledge_manager.storage.list_modules", tracked_list_modules)
    results = search_modules("rollback incidents", kb)

    assert results[0].module.id == "rollback-guide"
    assert calls["count"] == 0


def test_query_and_projection_document_load_reuse_single_disk_read(tmp_path, monkeypatch):
    import knowledge_manager.search_projection as search_projection
    from knowledge_manager.search_projection import build_search_projection, query_search_projection

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="projection cache"), kb)
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
    build_search_projection(kb)
    search_projection._PROJECTION_CACHE.clear()

    read_calls = {"count": 0}
    real_read_text = Path.read_text

    def counted_read_text(path_obj, *args, **kwargs):
        if path_obj == kb / ".cache" / "search_projection.json":
            read_calls["count"] += 1
        return real_read_text(path_obj, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counted_read_text)

    keys = query_search_projection(kb, "rollback incidents")
    documents = search_projection.load_search_projection_readonly(kb)["documents"]

    assert keys == ["ops/rollback-guide"]
    assert "ops/rollback-guide" in documents
    assert read_calls["count"] == 1


def test_build_search_projection_includes_rendering_and_graph_fields(tmp_path):
    from knowledge_manager.search_projection import build_search_projection

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="projection payload"), kb)
    save_module(
        Module(
            id="token-rotation",
            category="runbook",
            title="Token Rotation Runbook",
            summary="Rotate production tokens safely during incidents.",
            content=ModuleContent(
                overview="Rotate tokens with staged rollout and rollback checkpoints.",
                details="Detailed token rotation steps with verification, rollback, and owner handoff.",
                examples="Example incident rotation checklist.",
                references="https://example.invalid/runbook",
                caveats="Coordinate changes with approvers before production rollout.",
            ),
            metadata=ModuleMetadata(
                tags=["token", "rotation"],
                related_modules=["policy/change-approval"],
                confidence="high",
                stale_due_to_source_change=True,
                status="reviewed",
            ),
        ),
        kb,
    )

    projection = build_search_projection(kb)
    document = projection["documents"]["runbook/token-rotation"]

    assert document["title"] == "Token Rotation Runbook"
    assert document["summary"] == "Rotate production tokens safely during incidents."
    assert document["overview"] == "Rotate tokens with staged rollout and rollback checkpoints."
    assert document["details"].startswith("Detailed token rotation steps")
    assert document["examples"] == "Example incident rotation checklist."
    assert document["references"] == "https://example.invalid/runbook"
    assert document["caveats"] == "Coordinate changes with approvers before production rollout."
    assert document["tags"] == ["token", "rotation"]
    assert document["related_modules"] == ["policy/change-approval"]
    assert document["confidence"] == "high"
    assert document["stale_due_to_source_change"] is True
    assert document["status"] == "reviewed"
    assert "field_stems" in document
    assert "title" in document["field_stems"]
    assert "stems" in document


def test_bm25_scores_for_documents_uses_persisted_stems_when_available(tmp_path, monkeypatch):
    from knowledge_manager.search_projection import build_search_projection
    from knowledge_manager.storage import _bm25_scores_for_documents

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="projection bm25"), kb)
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

    projection = build_search_projection(kb)
    document = projection["documents"]["ops/rollback-guide"]

    monkeypatch.setattr(
        "knowledge_manager.storage._document_full_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("bm25 should reuse persisted stems instead of rebuilding full text")
        ),
    )

    scores = _bm25_scores_for_documents("rollback incidents", [document])

    assert scores["ops/rollback-guide"] > 0
