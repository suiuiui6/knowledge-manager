from __future__ import annotations

import json
from pathlib import Path


def _index_path(kb_path: Path) -> Path:
    return kb_path / ".cache" / "lexical_index.json"


def _write_index_payload(kb_path: Path, payload: dict[str, object]) -> dict[str, object]:
    path = _index_path(kb_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def _module_key(category: str, module_id: str) -> str:
    return f"{category}/{module_id}"


def _module_terms(module) -> set[str]:
    from knowledge_manager.storage import _WORD_RE, _stem

    text = " ".join(
        [
            module.title,
            module.summary,
            module.content.overview,
            module.content.details,
            " ".join(module.metadata.tags),
        ]
    )
    terms: set[str] = set()
    for word in _WORD_RE.findall(text.lower()):
        terms.update(_stem(word).split())
    return terms


def load_lexical_index(kb_path: Path) -> dict[str, dict[str, list[str]]] | None:
    path = _index_path(kb_path)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "terms" in payload:
        return payload
    return {"terms": payload, "module_terms": {}}


def build_lexical_index(kb_path: Path) -> dict[str, dict[str, list[str]]]:
    from knowledge_manager.storage import list_modules

    inverted: dict[str, list[str]] = {}
    module_terms: dict[str, list[str]] = {}
    for module in list_modules(kb_path):
        key = _module_key(module.category, module.id)
        tokens = sorted(_module_terms(module))
        module_terms[key] = tokens
        for term in tokens:
            inverted.setdefault(term, []).append(key)
    for term in inverted:
        inverted[term] = sorted(set(inverted[term]))

    payload = {"terms": inverted, "module_terms": module_terms}
    return _write_index_payload(kb_path, payload)


def _remove_module_terms(payload: dict[str, dict[str, list[str]]], module_key: str) -> None:
    tokens = payload.get("module_terms", {}).pop(module_key, [])
    for term in tokens:
        current = payload.get("terms", {}).get(term, [])
        remaining = [candidate for candidate in current if candidate != module_key]
        if remaining:
            payload["terms"][term] = remaining
        else:
            payload["terms"].pop(term, None)


def update_lexical_index_for_module(kb_path: Path, module) -> dict[str, dict[str, list[str]]]:
    payload = load_lexical_index(kb_path) or {"terms": {}, "module_terms": {}}
    key = _module_key(module.category, module.id)
    _remove_module_terms(payload, key)
    tokens = sorted(_module_terms(module))
    payload["module_terms"][key] = tokens
    for term in tokens:
        current = payload["terms"].setdefault(term, [])
        if key not in current:
            current.append(key)
            current.sort()
    return _write_index_payload(kb_path, payload)


def delete_lexical_index_for_module(kb_path: Path, category: str, module_id: str) -> dict[str, dict[str, list[str]]] | None:
    payload = load_lexical_index(kb_path)
    if payload is None:
        return None
    _remove_module_terms(payload, _module_key(category, module_id))
    return _write_index_payload(kb_path, payload)


def query_lexical_index(kb_path: Path, query: str) -> list[str]:
    from knowledge_manager.storage import _WORD_RE, _stem

    payload = load_lexical_index(kb_path)
    if payload is None:
        payload = build_lexical_index(kb_path)
    inverted = payload["terms"]

    scores: dict[str, int] = {}
    for word in _WORD_RE.findall(query.lower()):
        for term in _stem(word).split():
            for module_key in inverted.get(term, []):
                scores[module_key] = scores.get(module_key, 0) + 1
    return [key for key, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))]
