from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata
from knowledge_manager.storage import delete_module, generate_recommendations, save_index, save_module


def test_recommendation_index_persists_precomputed_link_candidates(tmp_path, monkeypatch):
    from knowledge_manager.recommendation_index import build_recommendation_index, load_recommendation_index

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="recommendation link candidates"), kb)
    save_module(
        Module(
            id="incident-core",
            category="ops",
            title="Incident Core",
            summary="Incident response summary.",
            content=ModuleContent(
                overview="Rollback and incident overview.",
                details="Incident response details long enough for validation.",
            ),
            metadata=ModuleMetadata(tags=["incident", "rollback"]),
        ),
        kb,
    )
    save_module(
        Module(
            id="incident-links",
            category="ops",
            title="Incident Links",
            summary="Incident companion summary.",
            content=ModuleContent(
                overview="Rollback and incident companion overview.",
                details="Companion details long enough for validation.",
            ),
            metadata=ModuleMetadata(tags=["incident", "rollback"]),
        ),
        kb,
    )

    payload = build_recommendation_index(kb)
    assert payload["link_candidates"] == [
        {
            "first": "ops/incident-core",
            "second": "ops/incident-links",
            "shared_tags": ["incident", "rollback"],
        }
    ]
    monkeypatch.setattr(
        "knowledge_manager.recommendation_index.iter_recommendation_link_candidates",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("recommendations should use persisted link candidates")
        ),
    )

    report = generate_recommendations(kb)

    assert len(report.suggested_links) >= 1
    assert load_recommendation_index(kb)["link_candidates"] == payload["link_candidates"]


def test_recommendation_index_updates_on_save_without_full_rebuild(tmp_path, monkeypatch):
    from knowledge_manager.recommendation_index import build_recommendation_index, load_recommendation_index

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="recommendation index"), kb)
    save_module(
        Module(
            id="incident-core",
            category="ops",
            title="Incident Core",
            summary="Incident response summary.",
            content=ModuleContent(
                overview="Rollback and incident overview.",
                details="Incident response details long enough for validation.",
            ),
            metadata=ModuleMetadata(tags=["incident", "rollback"]),
        ),
        kb,
    )
    build_recommendation_index(kb)

    def explode(*_args, **_kwargs):
        raise AssertionError("full recommendation index rebuild should not run on save")

    monkeypatch.setattr("knowledge_manager.recommendation_index.build_recommendation_index", explode)
    save_module(
        Module(
            id="incident-links",
            category="ops",
            title="Incident Links",
            summary="Incident companion summary.",
            content=ModuleContent(
                overview="Rollback and incident companion overview.",
                details="Companion details long enough for validation.",
            ),
            metadata=ModuleMetadata(tags=["incident", "rollback"]),
        ),
        kb,
    )

    payload = load_recommendation_index(kb)
    assert payload is not None
    assert "ops/incident-links" in payload["modules"]


def test_recommendation_index_updates_on_delete(tmp_path):
    from knowledge_manager.recommendation_index import build_recommendation_index, load_recommendation_index

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="recommendation index delete"), kb)
    save_module(
        Module(
            id="incident-core",
            category="ops",
            title="Incident Core",
            summary="Incident response summary.",
            content=ModuleContent(
                overview="Rollback and incident overview.",
                details="Incident response details long enough for validation.",
            ),
            metadata=ModuleMetadata(tags=["incident", "rollback"]),
        ),
        kb,
    )
    build_recommendation_index(kb)

    assert delete_module("incident-core", "ops", kb) is True

    payload = load_recommendation_index(kb)
    assert payload is not None
    assert "ops/incident-core" not in payload["modules"]


def test_generate_recommendations_uses_recommendation_index_modules(tmp_path, monkeypatch):
    from knowledge_manager.recommendation_index import build_recommendation_index

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="recommendation generation"), kb)
    save_module(
        Module(
            id="incident-core",
            category="ops",
            title="Incident Core",
            summary="Incident response summary.",
            content=ModuleContent(
                overview="Rollback and incident overview.",
                details="Incident response details long enough for validation.",
            ),
            metadata=ModuleMetadata(tags=["incident", "rollback"]),
        ),
        kb,
    )
    save_module(
        Module(
            id="incident-links",
            category="ops",
            title="Incident Links",
            summary="Incident companion summary.",
            content=ModuleContent(
                overview="Rollback and incident companion overview.",
                details="Companion details long enough for validation.",
            ),
            metadata=ModuleMetadata(tags=["incident", "rollback"]),
        ),
        kb,
    )
    build_recommendation_index(kb)

    def explode(*_args, **_kwargs):
        raise AssertionError("recommendations should use indexed module payloads instead of reloading files")

    monkeypatch.setattr("knowledge_manager.storage.load_module", explode)
    report = generate_recommendations(kb)

    assert len(report.suggested_links) >= 1


def test_generate_recommendations_reuses_telemetry_snapshot_per_run(tmp_path, monkeypatch):
    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="recommendation telemetry reuse"), kb)
    save_module(
        Module(
            id="incident-core",
            category="ops",
            title="Incident Core",
            summary="Incident response summary.",
            content=ModuleContent(
                overview="Rollback and incident overview.",
                details="Incident response details long enough for validation.",
            ),
            metadata=ModuleMetadata(tags=["incident", "rollback"]),
        ),
        kb,
    )
    save_module(
        Module(
            id="incident-links",
            category="ops",
            title="Incident Links",
            summary="Incident companion summary.",
            content=ModuleContent(
                overview="Rollback and incident companion overview.",
                details="Companion details long enough for validation.",
            ),
            metadata=ModuleMetadata(tags=["incident", "rollback"]),
        ),
        kb,
    )
    calls = {"count": 0}

    def counted_load_search_events(path):
        assert path == kb
        calls["count"] += 1
        return []

    monkeypatch.setattr("knowledge_manager.storage.load_search_events", counted_load_search_events)

    generate_recommendations(kb)

    assert calls["count"] == 1
