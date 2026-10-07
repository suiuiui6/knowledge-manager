from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _index_path(kb_path: Path) -> Path:
    return kb_path / ".cache" / "recommendation_index.json"


def _module_key(category: str, module_id: str) -> str:
    return f"{category}/{module_id}"


def _write_payload(kb_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    payload["link_candidates"] = _derive_link_candidates(payload)
    path = _index_path(kb_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def load_recommendation_index(kb_path: Path) -> dict[str, Any] | None:
    path = _index_path(kb_path)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_related_module(reference: str) -> str:
    if ":" in reference:
        ref_part, weight_str = reference.rsplit(":", 1)
        try:
            float(weight_str)
            return ref_part
        except ValueError:
            return reference
    return reference


def _apply_module(payload: dict[str, Any], module) -> None:
    key = _module_key(module.category, module.id)
    _remove_module(payload, module.category, module.id)

    tags = sorted(set(module.metadata.tags))
    related = sorted(
        {
            normalized
            for normalized in (_normalize_related_module(item) for item in module.metadata.related_modules)
            if "/" in normalized
        }
    )
    payload["modules"][key] = {"module": module.model_dump(mode="json")}
    payload["module_tags"][key] = tags
    payload["outbound_links"][key] = related
    for tag in tags:
        current = payload["tag_index"].setdefault(tag, [])
        if key not in current:
            current.append(key)
            current.sort()


def _remove_module(payload: dict[str, Any], category: str, module_id: str) -> None:
    key = _module_key(category, module_id)
    tags = payload.get("module_tags", {}).pop(key, [])
    for tag in tags:
        current = payload.get("tag_index", {}).get(tag, [])
        remaining = [candidate for candidate in current if candidate != key]
        if remaining:
            payload["tag_index"][tag] = remaining
        else:
            payload["tag_index"].pop(tag, None)
    payload.get("modules", {}).pop(key, None)
    payload.get("outbound_links", {}).pop(key, None)


def _empty_payload() -> dict[str, Any]:
    return {
        "modules": {},
        "module_tags": {},
        "tag_index": {},
        "outbound_links": {},
        "link_candidates": [],
    }


def _derive_link_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for first, second, shared_tags in iter_recommendation_link_candidates(payload):
        candidates.append(
            {
                "first": first,
                "second": second,
                "shared_tags": shared_tags,
            }
        )
    return candidates


def build_recommendation_index(kb_path: Path) -> dict[str, Any]:
    from knowledge_manager.storage import list_modules

    payload = _empty_payload()
    for module in list_modules(kb_path):
        _apply_module(payload, module)
    return _write_payload(kb_path, payload)


def update_recommendation_index_for_module(kb_path: Path, module) -> dict[str, Any]:
    payload = load_recommendation_index(kb_path) or _empty_payload()
    _apply_module(payload, module)
    return _write_payload(kb_path, payload)


def remove_recommendation_index_for_module(kb_path: Path, category: str, module_id: str) -> dict[str, Any] | None:
    payload = load_recommendation_index(kb_path)
    if payload is None:
        return None
    _remove_module(payload, category, module_id)
    return _write_payload(kb_path, payload)


def iter_recommendation_link_candidates(payload: dict[str, Any]) -> list[tuple[str, str, list[str]]]:
    pair_tags: dict[tuple[str, str], set[str]] = {}
    existing_pairs: set[tuple[str, str]] = set()
    modules = set(payload.get("modules", {}).keys())

    for source, targets in payload.get("outbound_links", {}).items():
        if source not in modules:
            continue
        for target in targets:
            if target not in modules:
                continue
            existing_pairs.add(tuple(sorted((source, target))))

    for tag, keys in payload.get("tag_index", {}).items():
        ordered = sorted(key for key in keys if key in modules)
        for index, first in enumerate(ordered):
            for second in ordered[index + 1:]:
                pair = (first, second)
                if pair in existing_pairs:
                    continue
                pair_tags.setdefault(pair, set()).add(tag)

    return [
        (first, second, sorted(shared_tags))
        for (first, second), shared_tags in pair_tags.items()
        if shared_tags
    ]
