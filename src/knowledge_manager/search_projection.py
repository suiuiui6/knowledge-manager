from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


_PROJECTION_CACHE: dict[str, tuple[int, int, dict[str, Any]]] = {}


def _projection_path(kb_path: Path) -> Path:
    return kb_path / ".cache" / "search_projection.json"


def _module_key(category: str, module_id: str) -> str:
    return f"{category}/{module_id}"


def _normalize_terms(module) -> list[str]:
    from knowledge_manager.storage import _WORD_RE, _module_full_text, _stem

    terms: list[str] = []
    for word in _WORD_RE.findall(_module_full_text(module).lower()):
        terms.extend(_stem(word).split())
    return terms


def _field_stem_payload(module) -> dict[str, list[str]]:
    from knowledge_manager.storage import _field_stems, _stem

    return {
        "title": sorted(_field_stems(module.title)),
        "tag": sorted({stem for tag in module.metadata.tags for stem in _stem(tag).split()}),
        "summary": sorted(_field_stems(module.summary)),
        "overview": sorted(_field_stems(module.content.overview)),
        "details": sorted(_field_stems(module.content.details)),
        "examples": sorted(_field_stems(module.content.examples)),
        "caveats": sorted(_field_stems(module.content.caveats)),
    }


def _project_module(module) -> dict[str, Any]:
    stems = _normalize_terms(module)
    return {
        "category": module.category,
        "module_id": module.id,
        "title": module.title,
        "summary": module.summary,
        "overview": module.content.overview,
        "details": module.content.details,
        "examples": module.content.examples,
        "references": module.content.references,
        "caveats": module.content.caveats,
        "tags": list(module.metadata.tags),
        "related_modules": list(module.metadata.related_modules),
        "confidence": module.metadata.confidence,
        "tenant_id": module.metadata.tenant_id,
        "workspace_id": module.metadata.workspace_id,
        "stale_due_to_source_change": module.metadata.stale_due_to_source_change,
        "expires_at": module.metadata.expires_at.isoformat() if module.metadata.expires_at else None,
        "status": module.metadata.status,
        "created_at": module.created_at.isoformat(),
        "updated_at": module.updated_at.isoformat(),
        "stems": stems,
        "field_stems": _field_stem_payload(module),
    }


def projection_document_complete(document: dict[str, Any]) -> bool:
    required_fields = {
        "category",
        "module_id",
        "title",
        "summary",
        "overview",
        "details",
        "examples",
        "references",
        "caveats",
        "tags",
        "related_modules",
        "confidence",
        "tenant_id",
        "stale_due_to_source_change",
        "status",
        "field_stems",
    }
    return required_fields.issubset(document.keys())


def _write_projection(kb_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    path = _projection_path(kb_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    stat = path.stat()
    _PROJECTION_CACHE[str(path)] = (int(stat.st_mtime_ns), int(stat.st_size), payload)
    return payload


def _load_projection_payload(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    stat = path.stat()
    cache_key = str(path)
    cached = _PROJECTION_CACHE.get(cache_key)
    if cached is not None:
        cached_mtime_ns, cached_size, cached_payload = cached
        if cached_mtime_ns == int(stat.st_mtime_ns) and cached_size == int(stat.st_size):
            return cached_payload
    payload = json.loads(path.read_text(encoding="utf-8"))
    _PROJECTION_CACHE[cache_key] = (int(stat.st_mtime_ns), int(stat.st_size), payload)
    return payload


def load_search_projection_readonly(kb_path: Path) -> dict[str, Any] | None:
    path = _projection_path(kb_path)
    return _load_projection_payload(path)


def load_search_projection(kb_path: Path) -> dict[str, Any] | None:
    payload = load_search_projection_readonly(kb_path)
    if payload is None:
        return None
    return copy.deepcopy(payload)


def build_search_projection(kb_path: Path) -> dict[str, Any]:
    from knowledge_manager.storage import list_modules

    documents: dict[str, dict[str, Any]] = {}
    inverted: dict[str, list[str]] = {}
    for module in list_modules(kb_path):
        key = _module_key(module.category, module.id)
        documents[key] = _project_module(module)
        stems = documents[key]["stems"]
        for stem in sorted(set(stems)):
            inverted.setdefault(stem, []).append(key)
    for stem in inverted:
        inverted[stem] = sorted(set(inverted[stem]))
    return _write_projection(kb_path, {"documents": documents, "inverted": inverted})


def _remove_from_projection(payload: dict[str, Any], category: str, module_id: str) -> None:
    key = _module_key(category, module_id)
    document = payload.get("documents", {}).pop(key, None)
    if document is None:
        return
    for stem in sorted(set(document.get("stems", []))):
        current = payload.get("inverted", {}).get(stem, [])
        remaining = [candidate for candidate in current if candidate != key]
        if remaining:
            payload["inverted"][stem] = remaining
        else:
            payload["inverted"].pop(stem, None)


def update_search_projection_for_module(kb_path: Path, module) -> dict[str, Any]:
    payload = load_search_projection(kb_path) or {"documents": {}, "inverted": {}}
    _remove_from_projection(payload, module.category, module.id)
    key = _module_key(module.category, module.id)
    payload["documents"][key] = _project_module(module)
    stems = payload["documents"][key]["stems"]
    for stem in sorted(set(stems)):
        current = payload["inverted"].setdefault(stem, [])
        if key not in current:
            current.append(key)
            current.sort()
    return _write_projection(kb_path, payload)


def remove_search_projection_for_module(kb_path: Path, category: str, module_id: str) -> dict[str, Any] | None:
    payload = load_search_projection(kb_path)
    if payload is None:
        return None
    _remove_from_projection(payload, category, module_id)
    return _write_projection(kb_path, payload)


def query_search_projection(kb_path: Path, query: str) -> list[str]:
    from knowledge_manager.storage import _WORD_RE, _stem

    payload = load_search_projection_readonly(kb_path)
    if payload is None:
        payload = build_search_projection(kb_path)

    scores: dict[str, int] = {}
    for word in _WORD_RE.findall(query.lower()):
        for stem in _stem(word).split():
            for key in payload["inverted"].get(stem, []):
                scores[key] = scores.get(key, 0) + 1
    return [key for key, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))]
