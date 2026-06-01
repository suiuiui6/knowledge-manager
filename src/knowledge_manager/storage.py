import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, List, Mapping, Optional, cast

from snowballstemmer import stemmer as _snowball_stemmer  # type: ignore[import-untyped]

from knowledge_manager.schemas import Index, Module


_FIELD_WEIGHTS = {"title": 5, "tag": 3, "summary": 2, "overview": 1}
_WORD_RE = re.compile(r"\w+")
_EN_STEMMER: Any = _snowball_stemmer("english")

_QUALITY_EXACT = 3
_QUALITY_STEM = 2
_QUALITY_PARTIAL = 1


def _stem(word: str) -> str:
    return cast(str, _EN_STEMMER.stemWord(word.lower()))


def _field_stems(text: str) -> set[str]:
    return {_stem(word) for word in _WORD_RE.findall(text)}


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

    def score_term(
        term: str,
        fields: Mapping[str, str | list[str]],
        field_stems: Mapping[str, set[str]],
        word_pattern: re.Pattern[str],
        partial_pattern: re.Pattern[str] | None,
    ) -> tuple[int, int]:
        for field_name in ("title", "tag", "summary", "overview"):
            field_value = fields[field_name]
            values = field_value if isinstance(field_value, list) else [field_value]
            if any(word_pattern.search(value) for value in values):
                return _FIELD_WEIGHTS[field_name], _QUALITY_EXACT

        term_stem = _stem(term)
        for field_name in ("title", "tag", "summary", "overview"):
            if term_stem in field_stems[field_name]:
                return _FIELD_WEIGHTS[field_name], _QUALITY_STEM

        if partial_pattern is not None:
            for field_name in ("title", "tag", "summary", "overview"):
                field_value = fields[field_name]
                values = field_value if isinstance(field_value, list) else [field_value]
                if any(partial_pattern.search(value) for value in values):
                    return _FIELD_WEIGHTS[field_name] // 2, _QUALITY_PARTIAL

        return 0, 0

    patterns = []
    for term in terms:
        word_boundary = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
        partial = re.compile(re.escape(term), re.IGNORECASE) if len(term) < 5 else None
        patterns.append((term, word_boundary, partial))

    scored: List[tuple[int, int, Module]] = []
    for module in list_modules(kb_path):
        fields: dict[str, str | list[str]] = {
            "title": module.title,
            "tag": module.metadata.tags,
            "summary": module.summary,
            "overview": module.content.overview,
        }
        field_stems = {
            "title": _field_stems(module.title),
            "tag": {_stem(tag) for tag in module.metadata.tags},
            "summary": _field_stems(module.summary),
            "overview": _field_stems(module.content.overview),
        }
        score = 0
        best_quality = 0

        for term, word_pattern, partial_pattern in patterns:
            term_score, quality = score_term(term, fields, field_stems, word_pattern, partial_pattern)
            score += term_score
            best_quality = max(best_quality, quality)

        if score > 0:
            scored.append((score, best_quality, module))

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [module for _, _, module in scored]


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
