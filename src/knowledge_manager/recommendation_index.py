from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_RECOMMENDATION_CACHE: dict[str, tuple[int, int, dict[str, Any]]] = {}
MAX_TAG_DOCUMENTS = 200


def _index_path(kb_path: Path) -> Path:
    return kb_path / ".cache" / "recommendation_index.json"


def _module_key(category: str, module_id: str) -> str:
    return f"{category}/{module_id}"


def _write_payload(
    kb_path: Path,
    payload: dict[str, Any],
    *,
    refresh_link_candidates: bool = True,
) -> dict[str, Any]:
    if refresh_link_candidates:
        payload["link_candidates"] = _derive_link_candidates(payload)
    path = _index_path(kb_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    stat = path.stat()
    _RECOMMENDATION_CACHE[str(path)] = (int(stat.st_mtime_ns), int(stat.st_size), payload)
    return payload


def load_recommendation_index(kb_path: Path) -> dict[str, Any] | None:
    path = _index_path(kb_path)
    if not path.exists():
        return None
    stat = path.stat()
    cache_key = str(path)
    cached = _RECOMMENDATION_CACHE.get(cache_key)
    if cached is not None and cached[:2] == (int(stat.st_mtime_ns), int(stat.st_size)):
        return cached[2]
    payload = json.loads(path.read_text(encoding="utf-8"))
    _RECOMMENDATION_CACHE[cache_key] = (int(stat.st_mtime_ns), int(stat.st_size), payload)
    return payload


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
            for normalized in (
                _normalize_related_module(item) for item in module.metadata.related_modules
            )
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
    payload["link_candidates"] = [
        candidate
        for candidate in payload.get("link_candidates", [])
        if candidate.get("first") != key and candidate.get("second") != key
    ]


def _has_explicit_link(payload: dict[str, Any], first: str, second: str) -> bool:
    outbound_links = payload.get("outbound_links", {})
    return second in outbound_links.get(first, []) or first in outbound_links.get(second, [])


def _refresh_link_candidates_for_module(payload: dict[str, Any], key: str) -> None:
    payload["link_candidates"] = [
        candidate
        for candidate in payload.get("link_candidates", [])
        if candidate.get("first") != key and candidate.get("second") != key
    ]
    modules = set(payload.get("modules", {}))
    if key not in modules:
        return
    key_tags = {
        tag
        for tag in payload.get("module_tags", {}).get(key, [])
        if len(payload.get("tag_index", {}).get(tag, [])) <= MAX_TAG_DOCUMENTS
    }
    for other in sorted(modules - {key}):
        first, second = sorted((key, other))
        if _has_explicit_link(payload, first, second):
            continue
        shared_tags = sorted(key_tags.intersection(payload.get("module_tags", {}).get(other, [])))
        if shared_tags:
            payload["link_candidates"].append(
                {"first": first, "second": second, "shared_tags": shared_tags}
            )
    payload["link_candidates"].sort(key=lambda item: (item["first"], item["second"]))


def _empty_payload() -> dict[str, Any]:
    return {
        "modules": {},
        "module_tags": {},
        "tag_index": {},
        "outbound_links": {},
        "link_candidates": [],
        "candidate_policy": {
            "max_tag_documents": MAX_TAG_DOCUMENTS,
            "ignored_high_frequency_tags": [],
        },
    }


def _update_candidate_policy(payload: dict[str, Any]) -> None:
    modules = set(payload.get("modules", {}))
    ignored = sorted(
        tag
        for tag, keys in payload.get("tag_index", {}).items()
        if len([key for key in keys if key in modules]) > MAX_TAG_DOCUMENTS
    )
    payload["candidate_policy"] = {
        "max_tag_documents": MAX_TAG_DOCUMENTS,
        "ignored_high_frequency_tags": ignored,
    }
    ignored_set = set(ignored)
    candidates = []
    for candidate in payload.get("link_candidates", []):
        shared_tags = sorted(set(candidate.get("shared_tags", [])) - ignored_set)
        if shared_tags:
            candidates.append({**candidate, "shared_tags": shared_tags})
    payload["link_candidates"] = candidates


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
    previous_policy = payload.get("candidate_policy", {}).copy()
    _apply_module(payload, module)
    _update_candidate_policy(payload)
    if previous_policy != payload["candidate_policy"]:
        return _write_payload(kb_path, payload)
    _refresh_link_candidates_for_module(payload, _module_key(module.category, module.id))
    return _write_payload(kb_path, payload, refresh_link_candidates=False)


def remove_recommendation_index_for_module(
    kb_path: Path, category: str, module_id: str
) -> dict[str, Any] | None:
    payload = load_recommendation_index(kb_path)
    if payload is None:
        return None
    _remove_module(payload, category, module_id)
    _update_candidate_policy(payload)
    return _write_payload(kb_path, payload, refresh_link_candidates=True)


def iter_recommendation_link_candidates(
    payload: dict[str, Any]
) -> list[tuple[str, str, list[str]]]:
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

    ignored_tags: list[str] = []
    for tag, keys in payload.get("tag_index", {}).items():
        ordered = sorted(key for key in keys if key in modules)
        if len(ordered) > MAX_TAG_DOCUMENTS:
            ignored_tags.append(tag)
            continue
        for index, first in enumerate(ordered):
            for second in ordered[index + 1 :]:
                pair = (first, second)
                if pair in existing_pairs:
                    continue
                pair_tags.setdefault(pair, set()).add(tag)

    payload["candidate_policy"] = {
        "max_tag_documents": MAX_TAG_DOCUMENTS,
        "ignored_high_frequency_tags": sorted(ignored_tags),
    }
    return [
        (first, second, sorted(shared_tags))
        for (first, second), shared_tags in pair_tags.items()
        if shared_tags
    ]
