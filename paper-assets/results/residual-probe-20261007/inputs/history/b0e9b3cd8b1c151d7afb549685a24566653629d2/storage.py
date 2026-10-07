import json
import os
import re
import tempfile
from pathlib import Path
from typing import List, Optional

from knowledge_manager.schemas import Index, Module


_FIELD_WEIGHTS = {"title": 5, "tag": 3, "summary": 2, "overview": 1}


def _atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(data, encoding="utf-8")
    os.replace(tmp, path)


def save_module(module: Module, kb_path: Path) -> None:
    path = module.to_file_path(kb_path)
    _atomic_write(path, module.model_dump_json(indent=2))


def load_module(module_id: str, category: str, kb_path: Path) -> Optional[Module]:
    path = kb_path / category / f"{module_id}.json"
    if not path.exists():
        return None
    return Module.model_validate_json(path.read_text(encoding="utf-8"))


def delete_module(module_id: str, category: str, kb_path: Path) -> bool:
    path = kb_path / category / f"{module_id}.json"
    if not path.exists():
        return False
    path.unlink()
    return True


def list_modules(kb_path: Path) -> List[Module]:
    if not kb_path.exists():
        return []
    modules = []
    for json_file in kb_path.rglob("*.json"):
        if json_file.name == "index.json":
            continue
        try:
            modules.append(Module.model_validate_json(json_file.read_text(encoding="utf-8")))
        except Exception:
            pass
    return modules


def search_modules(query: str, kb_path: Path) -> List[Module]:
    terms = query.lower().split()
    if not terms:
        return []

    # For each term, create both word-boundary and partial-match patterns
    # Short terms (<5 chars) get partial matching to handle abbreviations
    patterns = []
    for t in terms:
        word_boundary = re.compile(rf"\b{re.escape(t)}\b", re.IGNORECASE)
        partial = re.compile(re.escape(t), re.IGNORECASE) if len(t) < 5 else None
        patterns.append((word_boundary, partial))

    scored: List[tuple] = []
    for m in list_modules(kb_path):
        score = 0
        is_word_boundary = False  # Track if any match was word-boundary

        for word_pat, partial_pat in patterns:
            best = 0
            matched_word_boundary = False

            # Try word boundary match first (full weight)
            if word_pat.search(m.title):
                best = _FIELD_WEIGHTS["title"]
                matched_word_boundary = True
            elif any(word_pat.search(tag) for tag in m.metadata.tags):
                best = max(best, _FIELD_WEIGHTS["tag"])
                matched_word_boundary = True
            elif word_pat.search(m.summary):
                best = max(best, _FIELD_WEIGHTS["summary"])
                matched_word_boundary = True
            elif word_pat.search(m.content.overview):
                best = max(best, _FIELD_WEIGHTS["overview"])
                matched_word_boundary = True

            # If no word boundary match and partial pattern exists, try partial match (half weight)
            if best == 0 and partial_pat:
                if partial_pat.search(m.title):
                    best = _FIELD_WEIGHTS["title"] // 2
                elif any(partial_pat.search(tag) for tag in m.metadata.tags):
                    best = max(best, _FIELD_WEIGHTS["tag"] // 2)
                elif partial_pat.search(m.summary):
                    best = max(best, _FIELD_WEIGHTS["summary"] // 2)
                elif partial_pat.search(m.content.overview):
                    best = max(best, _FIELD_WEIGHTS["overview"] // 2)

            score += best
            if matched_word_boundary:
                is_word_boundary = True

        if score > 0:
            # Use tuple (score, is_word_boundary, module) for sorting
            # Higher score first, then word-boundary matches before partial matches
            scored.append((score, is_word_boundary, m))

    # Sort by score (desc), then by word_boundary flag (True before False)
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [m for _, _, m in scored]


def save_index(index: Index, kb_path: Path) -> None:
    _atomic_write(kb_path / "index.json", index.model_dump_json(indent=2))


def load_index(kb_path: Path) -> Optional[Index]:
    path = kb_path / "index.json"
    if not path.exists():
        return None
    return Index.model_validate_json(path.read_text(encoding="utf-8"))


def rebuild_index(kb_path: Path) -> Index:
    index = load_index(kb_path) or Index()
    index.categories.clear()
    for module in list_modules(kb_path):
        index.add_module(module)
    save_index(index, kb_path)
    return index


def save_to_staging(module: Module, staging_path: Path) -> None:
    _atomic_write(staging_path / f"{module.id}.json", module.model_dump_json(indent=2))


def load_from_staging(module_id: str, staging_path: Path) -> Optional[Module]:
    path = staging_path / f"{module_id}.json"
    if not path.exists():
        return None
    return Module.model_validate_json(path.read_text(encoding="utf-8"))


def list_staging(staging_path: Path) -> List[Module]:
    if not staging_path.exists():
        return []
    modules = []
    for json_file in staging_path.glob("*.json"):
        try:
            modules.append(Module.model_validate_json(json_file.read_text(encoding="utf-8")))
        except Exception:
            pass
    return modules


def approve_from_staging(module_id: str, staging_path: Path, kb_path: Path) -> None:
    module = load_from_staging(module_id, staging_path)
    if module is None:
        raise FileNotFoundError(f"Staging module not found: {module_id}")
    save_module(module, kb_path)
    (staging_path / f"{module_id}.json").unlink()
