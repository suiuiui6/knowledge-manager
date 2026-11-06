import json
from pathlib import Path

from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata
from knowledge_manager.storage import (
    delete_module,
    generate_recommendations,
    save_index,
    save_module,
)


def test_dense_tags_do_not_expand_quadratically_and_keep_specific_matches():
    from knowledge_manager.recommendation_index import iter_recommendation_link_candidates

    keys = [f"ops/module-{n:05d}" for n in range(300)]
    payload = {
        "modules": dict.fromkeys(keys, {}),
        "tag_index": {"common": keys, "specific": keys[-2:]},
        "outbound_links": {},
    }
    pairs = iter_recommendation_link_candidates(payload)
    assert pairs == [(keys[-2], keys[-1], ["specific"])]


def test_recommendation_candidate_policy_records_dense_tag_exclusions(tmp_path, monkeypatch):
    from knowledge_manager import recommendation_index as rec

    monkeypatch.setattr(rec, "MAX_TAG_DOCUMENTS", 2, raising=False)
    payload = rec._empty_payload()
    for n in range(3):
        module = Module(
            id=f"m-{n}",
            category="ops",
            title=f"Module title {n}",
            summary="Dense recommendation tag summary.",
            content=ModuleContent(
                overview="Dense recommendation overview.",
                details="Dense recommendation details for schema validation.",
            ),
            metadata=ModuleMetadata(tags=["common"]),
        )
        rec._apply_module(payload, module)
    written = rec._write_payload(tmp_path, payload)
    assert written["link_candidates"] == []
    assert written["candidate_policy"]["ignored_high_frequency_tags"] == ["common"]


def test_incremental_dense_tag_candidates_are_bounded(tmp_path, monkeypatch):
    from knowledge_manager import recommendation_index as rec

    monkeypatch.setattr(rec, "MAX_TAG_DOCUMENTS", 2, raising=False)
    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="dense incremental recommendation index"), kb)

    def make_module(module_id):
        return Module(
            id=module_id,
            category="ops",
            title=f"Module {module_id}",
            summary="Dense incremental recommendation summary.",
            content=ModuleContent(
                overview="Dense incremental overview.",
                details="Dense incremental details for schema validation.",
            ),
            metadata=ModuleMetadata(tags=["common"]),
        )

    save_module(make_module("one"), kb)
    save_module(make_module("two"), kb)
    save_module(make_module("three"), kb)
    payload = rec.load_recommendation_index(kb)
    assert payload is not None
    assert payload["link_candidates"] == []
    assert payload["candidate_policy"]["ignored_high_frequency_tags"] == ["common"]

    assert delete_module("three", "ops", kb)
    payload = rec.load_recommendation_index(kb)
    assert payload["link_candidates"] == [
        {"first": "ops/one", "second": "ops/two", "shared_tags": ["common"]}
    ]
    assert payload["candidate_policy"]["ignored_high_frequency_tags"] == []


def test_recommendation_index_persists_precomputed_link_candidates(tmp_path, monkeypatch):
    from knowledge_manager.recommendation_index import (
        build_recommendation_index,
        load_recommendation_index,
    )

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
    from knowledge_manager.recommendation_index import (
        build_recommendation_index,
        load_recommendation_index,
    )

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

    monkeypatch.setattr(
        "knowledge_manager.recommendation_index.build_recommendation_index", explode
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

    payload = load_recommendation_index(kb)
    assert payload is not None
    assert "ops/incident-links" in payload["modules"]


def test_recommendation_index_updates_link_candidates_incrementally(tmp_path):
    from knowledge_manager.recommendation_index import load_recommendation_index

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="incremental recommendation candidates"), kb)

    def make_module(module_id, tags):
        return Module(
            id=module_id,
            category="ops",
            title=f"Module {module_id}",
            summary="Recommendation summary long enough.",
            content=ModuleContent(
                overview="Recommendation overview long enough.",
                details="Recommendation details long enough for validation.",
            ),
            metadata=ModuleMetadata(tags=tags),
        )

    save_module(make_module("core", ["incident"]), kb)
    save_module(make_module("companion", ["incident"]), kb)
    save_module(make_module("other", ["policy"]), kb)
    payload = load_recommendation_index(kb)
    assert payload is not None
    assert payload["link_candidates"] == [
        {"first": "ops/companion", "second": "ops/core", "shared_tags": ["incident"]}
    ]

    save_module(make_module("other", ["incident"]), kb)
    payload = load_recommendation_index(kb)
    assert payload is not None
    assert payload["link_candidates"] == [
        {"first": "ops/companion", "second": "ops/core", "shared_tags": ["incident"]},
        {"first": "ops/companion", "second": "ops/other", "shared_tags": ["incident"]},
        {"first": "ops/core", "second": "ops/other", "shared_tags": ["incident"]},
    ]

    assert delete_module("companion", "ops", kb) is True
    payload = load_recommendation_index(kb)
    assert payload is not None
    assert payload["link_candidates"] == [
        {"first": "ops/core", "second": "ops/other", "shared_tags": ["incident"]}
    ]


def test_recommendation_index_updates_on_delete(tmp_path):
    from knowledge_manager.recommendation_index import (
        build_recommendation_index,
        load_recommendation_index,
    )

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
        raise AssertionError(
            "recommendations should use indexed module payloads instead of reloading files"
        )

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
    events_file = kb / ".telemetry" / "search_events.jsonl"
    events_file.parent.mkdir(parents=True)
    events_file.write_text(
        json.dumps(
            {
                "type": "load",
                "timestamp": "2026-10-23T00:00:00+00:00",
                "module_id": "incident-core",
                "category": "ops",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    read_calls = {"count": 0}
    real_read_text = Path.read_text

    def counted_read_text(path_obj, *args, **kwargs):
        if path_obj == events_file:
            read_calls["count"] += 1
        return real_read_text(path_obj, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counted_read_text)

    generate_recommendations(kb)

    assert read_calls["count"] == 1
