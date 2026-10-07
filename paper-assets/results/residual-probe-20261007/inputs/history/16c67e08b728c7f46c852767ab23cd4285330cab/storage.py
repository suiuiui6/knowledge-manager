import hashlib
import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, NamedTuple, Optional, cast

from snowballstemmer import stemmer as _snowball_stemmer  # type: ignore[import-untyped]

from knowledge_manager.schemas import Config, Index, Module, StagingMeta


_FIELD_WEIGHTS = {"title": 5, "tag": 3, "summary": 2, "overview": 1, "details": 1, "examples": 0, "caveats": 0}
_WORD_RE = re.compile(r"\w+")
_EN_STEMMER: Any = _snowball_stemmer("english")
_CJK_RE = re.compile(r"[一-鿿㐀-䶿豈-﫿]")

_QUALITY_EXACT = 3
_QUALITY_STEM = 2
_QUALITY_PARTIAL = 1

# BM25 parameters
_BM25_K1 = 1.2
_BM25_B = 0.75

# Graph expansion discount (applied to heuristic score of triggering module)
_EXPANSION_DISCOUNT = 0.4

# Confidence multiplier
_CONFIDENCE_WEIGHT = {"high": 1.0, "medium": 0.85, "low": 0.7}

# Intent-based field weight adjustments (added to base weights)
_INTENT_ADJUSTMENTS: Dict[str, Dict[str, float]] = {
    "how-to": {"examples": 5},
    "decision-record": {"details": 4, "caveats": 4},
    "reference": {"title": 2, "overview": 1},
    "general": {},
}

# Intent classification patterns
_INTENT_PATTERNS: Dict[str, List[str]] = {
    "how-to": [
        r"\bhow\s+(to|do|can|should|would|does|is|are)\b",
        r"\bguide\b", r"\btutorial\b", r"\bexample\b", r"\bpattern\b",
        r"\bimplement", r"\bset\s+up\b", r"\bconfigure\b", r"\bbuild\b",
        r"\bcreate\b", r"\bdeploy\b", r"\bmigrate\b", r"\bdebug\b",
    ],
    "decision-record": [
        r"\bwhy\b", r"\bdecision\b", r"\btradeoff\b", r"\btrade.off\b",
        r"\barchitecture\b", r"\bchose\b", r"\bchosen\b", r"\bADR\b",
        r"\balternative\b", r"\bapproach\b", r"\brationale\b",
        r"\bvs\b", r"\bversus\b", r"\bcompared to\b",
    ],
    "reference": [
        r"\bwhat is\b", r"\bdefinition\b", r"\bdefine\b", r"\bapi\b",
        r"\bconfig\b", r"\bparameter\b", r"\bendpoint\b", r"\bschema\b",
        r"\bsyntax\b", r"\breference\b", r"\bdocumentation\b",
    ],
}


def _stem(word: str) -> str:
    """Stem/tokenize a word. Chinese text is segmented with jieba; English uses snowball."""
    if _CJK_RE.search(word):
        try:
            import jieba
            return " ".join(jieba.cut(word))
        except ImportError:
            return word.lower()
    return cast(str, _EN_STEMMER.stemWord(word.lower()))


def _classify_intent(query: str) -> str:
    """Classify query intent: 'how-to', 'reference', 'decision-record', or 'general'."""
    q = query.lower()
    scores: Dict[str, int] = {}
    for intent, patterns in _INTENT_PATTERNS.items():
        scores[intent] = sum(1 for p in patterns if re.search(p, q, re.IGNORECASE))
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


def _module_full_text(module: Module) -> str:
    return " ".join([
        module.title,
        " ".join(module.metadata.tags),
        module.summary,
        module.content.overview,
        module.content.details,
        module.content.examples,
        module.content.references,
        module.content.caveats,
    ])


def _field_stems(text: str) -> set[str]:
    stems: set[str] = set()
    for word in _WORD_RE.findall(text):
        stemmed = _stem(word)
        # _stem may return space-separated tokens for Chinese text
        stems.update(stemmed.split())
    return stems


def _atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(data, encoding="utf-8")
    os.replace(tmp, path)


def save_module(module: Module, kb_path: Path) -> None:
    path = module.to_file_path(kb_path)
    existed = path.exists()
    _atomic_write(path, module.model_dump_json(indent=2))
    # Emit webhook event
    event = "module.updated" if existed else "module.created"
    from knowledge_manager.webhooks import emit_event
    emit_event(kb_path, event, module.id, module.category, {"title": module.title})


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
    from knowledge_manager.webhooks import emit_event
    emit_event(kb_path, "module.deleted", module_id, category)
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


class SearchResult(NamedTuple):
    module: Module
    source: str  # "direct" or "related"


def _bm25_scores(query: str, modules: List[Module]) -> Dict[str, float]:
    """Compute BM25 scores for modules given a query string.

    Returns a dict mapping module.id to BM25 score. Built from scratch each call
    for simplicity — acceptable for small-to-medium knowledge bases.
    """
    if not modules or not query.strip():
        return {}

    query_stems: List[str] = []
    for w in _WORD_RE.findall(query.lower()):
        query_stems.extend(_stem(w).split())
    if not query_stems:
        return {}

    doc_tfs: List[Dict[str, int]] = []
    doc_ids: List[str] = []
    df: Dict[str, int] = {}
    doc_lengths: List[int] = []

    for module in modules:
        text = _module_full_text(module)
        words = [w.lower() for w in _WORD_RE.findall(text)]
        stemmed: List[str] = []
        for w in words:
            stemmed.extend(_stem(w).split())

        tf: Dict[str, int] = {}
        for s in stemmed:
            tf[s] = tf.get(s, 0) + 1

        doc_tfs.append(tf)
        doc_ids.append(module.id)
        doc_lengths.append(len(stemmed))

        for term in set(stemmed):
            df[term] = df.get(term, 0) + 1

    N = len(modules)
    total_len = sum(doc_lengths)
    if total_len == 0:
        return {}
    avgdl = total_len / N

    scores: Dict[str, float] = {}
    for i, tf_map in enumerate(doc_tfs):
        score = 0.0
        dl = doc_lengths[i]
        for term in query_stems:
            df_t = df.get(term, 0)
            if df_t == 0:
                continue
            idf = math.log((N - df_t + 0.5) / (df_t + 0.5) + 1)
            tf = tf_map.get(term, 0)
            if tf == 0:
                continue
            score += (
                idf
                * (tf * (_BM25_K1 + 1))
                / (tf + _BM25_K1 * (1 - _BM25_B + _BM25_B * dl / avgdl))
            )
        scores[doc_ids[i]] = score

    return scores


def search_modules(query: str, kb_path: Path, category: str | None = None, limit: int = 15, boost_ids: List[str] | None = None, include_archived: bool = False) -> List[SearchResult]:
    terms: list[str] = []
    for w in _WORD_RE.findall(query.lower()):
        if _CJK_RE.search(w):
            # Chinese: segment with jieba into individual word tokens
            terms.extend(_stem(w).split())
        else:
            # English: keep raw word for exact boundary matching
            terms.append(w.lower())
    if not terms:
        return []

    all_modules = list_modules(kb_path)
    if not include_archived:
        all_modules = [m for m in all_modules if m.metadata.status != "archived"]
    bm25 = _bm25_scores(query, all_modules)

    # Build tag synonym map from co-occurring tags across all modules
    tag_synonyms: Dict[str, set[str]] = {}
    for m in all_modules:
        tag_words = set()
        for tag in m.metadata.tags:
            tag_words.update(_WORD_RE.findall(tag.lower()))
        for tw in tag_words:
            if tw not in tag_synonyms:
                tag_synonyms[tw] = set()
            tag_synonyms[tw].update(tag_words - {tw})

    # Load user-configured synonyms from config
    cfg = _load_config_safe(kb_path)
    user_synonyms: Dict[str, List[str]] = cfg.synonyms if cfg else {}

    # Expand query with tag synonyms (0.3 weight) and user synonyms (0.5 weight)
    synonym_terms: Dict[str, float] = {}
    for term in terms:
        if term in tag_synonyms:
            for syn in tag_synonyms[term]:
                if syn not in terms and syn not in synonym_terms:
                    synonym_terms[syn] = 0.3
        if term in user_synonyms:
            for syn in user_synonyms[term]:
                if syn not in terms and syn not in synonym_terms:
                    synonym_terms[syn] = 0.5

    # Build adjacency graph from module metadata (always fresh, no index dependency)
    graph: Dict[str, List[str]] = {}
    for m in all_modules:
        if m.metadata.related_modules:
            graph[f"{m.category}/{m.id}"] = list(m.metadata.related_modules)

    def score_term(
        term: str,
        fields: Mapping[str, str | list[str]],
        field_stems: Mapping[str, set[str]],
        word_pattern: re.Pattern[str],
        partial_pattern: re.Pattern[str] | None,
        weights: Dict[str, float] | None = None,
    ) -> tuple[int, int]:
        w = weights if weights is not None else _FIELD_WEIGHTS
        field_names = list(w.keys())
        for field_name in field_names:
            if field_name not in fields:
                continue
            field_value = fields[field_name]
            values = field_value if isinstance(field_value, list) else [field_value]
            if any(word_pattern.search(value) for value in values):
                return int(w[field_name]), _QUALITY_EXACT

        term_stems = _stem(term).split()
        for field_name in field_names:
            f_stems = field_stems.get(field_name, set())
            if term_stems and all(ts in f_stems for ts in term_stems):
                return int(w[field_name]), _QUALITY_STEM

        if partial_pattern is not None:
            for field_name in field_names:
                if field_name not in fields:
                    continue
                field_value = fields[field_name]
                values = field_value if isinstance(field_value, list) else [field_value]
                if any(partial_pattern.search(value) for value in values):
                    return max(1, int(w[field_name]) // 2), _QUALITY_PARTIAL

        return 0, 0

    # Classify query intent and compute adjusted field weights
    intent = _classify_intent(query)
    intent_adjustments = _INTENT_ADJUSTMENTS.get(intent, {})
    effective_weights = dict(_FIELD_WEIGHTS)
    for field, adj in intent_adjustments.items():
        effective_weights[field] = effective_weights.get(field, 0) + adj

    patterns = []
    for term in terms:
        word_boundary = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
        partial = re.compile(re.escape(term), re.IGNORECASE) if len(term) < 5 else None
        patterns.append((term, word_boundary, partial, 1.0))
    for syn, weight in synonym_terms.items():
        word_boundary = re.compile(rf"\b{re.escape(syn)}\b", re.IGNORECASE)
        partial = re.compile(re.escape(syn), re.IGNORECASE) if len(syn) < 5 else None
        patterns.append((syn, word_boundary, partial, weight))

    scored: List[tuple[float, float, int, Module, str]] = []
    for module in all_modules:
        fields: dict[str, str | list[str]] = {
            "title": module.title,
            "tag": module.metadata.tags,
            "summary": module.summary,
            "overview": module.content.overview,
            "details": module.content.details,
            "examples": module.content.examples,
            "caveats": module.content.caveats,
        }
        field_stems = {
            "title": _field_stems(module.title),
            "tag": {s for tag in module.metadata.tags for s in _stem(tag).split()},
            "summary": _field_stems(module.summary),
            "overview": _field_stems(module.content.overview),
            "details": _field_stems(module.content.details),
            "examples": _field_stems(module.content.examples),
            "caveats": _field_stems(module.content.caveats),
        }
        score = 0
        best_quality = 0

        for term, word_pattern, partial_pattern, weight in patterns:
            term_score, quality = score_term(term, fields, field_stems, word_pattern, partial_pattern, effective_weights)
            score += int(term_score * weight)
            best_quality = max(best_quality, quality)

        if score > 0:
            scored.append((bm25.get(module.id, 0.0), score, best_quality, module, "direct"))

    # 1-hop graph expansion: add related modules with discounted scores
    direct_matches = list(scored)
    direct_ids = {m.id for _, _, _, m, _ in direct_matches}
    for bm25_score, heur_score, _, trigger_module, _ in direct_matches:
        module_key = f"{trigger_module.category}/{trigger_module.id}"
        for neighbor_ref in graph.get(module_key, []):
            # Parse optional edge weight: "category/id:0.8" → weight=0.8 (default 1.0)
            edge_weight = 1.0
            raw_ref = neighbor_ref
            if ":" in raw_ref:
                ref_part, weight_str = raw_ref.rsplit(":", 1)
                try:
                    edge_weight = float(weight_str)
                    raw_ref = ref_part
                except ValueError:
                    pass
            parts = raw_ref.split("/", 1)
            if len(parts) != 2:
                continue
            n_cat, n_id = parts
            if n_id in direct_ids:
                continue
            neighbor = load_module(n_id, n_cat, kb_path)
            if neighbor is None:
                continue
            expanded_heuristic = heur_score * _EXPANSION_DISCOUNT * edge_weight
            expanded_bm25 = bm25.get(n_id, 0.0)
            scored.append((expanded_bm25, expanded_heuristic, 0, neighbor, "related"))
            direct_ids.add(n_id)

    # Filter by category if specified
    if category is not None:
        scored = [(b, s, q, m, src) for b, s, q, m, src in scored if m.category == category]

    # Compute Bayesian priors from historical telemetry (if available)
    priors = compute_bayesian_priors(kb_path)
    query_stems = []
    for t in terms:
        query_stems.extend(_stem(t).split())

    def _bayesian_bonus(module: Module) -> float:
        """Average P(module_id | query_term) across all query terms."""
        module_key = f"{module.category}/{module.id}"
        total = 0.0
        count = 0
        for term in query_stems:
            if term in priors and module_key in priors[term]:
                total += priors[term][module_key]
                count += 1
        return total / count if count > 0 else 0.0

    # Session boost: 1.2x multiplier for recently loaded modules in this session
    boost_set = set(boost_ids) if boost_ids else set()

    def _session_boost(module_id: str, heur_score: float) -> float:
        return heur_score * 1.2 if module_id in boost_set else heur_score

    def _effective_confidence(module: Module) -> float:
        """Deprecated modules get confidence penalty (treated as low)."""
        conf = module.metadata.confidence
        if module.metadata.status == "deprecated":
            conf = "low"
        return _CONFIDENCE_WEIGHT.get(conf, 0.85)

    # Primary: confidence-weighted heuristic score (with session boost).
    # Secondary: match quality. Tertiary: Bayesian prior. Fourth: BM25.
    scored.sort(
        key=lambda item: (
            _session_boost(item[3].id, item[1]) * _effective_confidence(item[3]),
            item[2],
            _bayesian_bonus(item[3]),
            item[0],
        ),
        reverse=True,
    )
    results = [SearchResult(module, source) for _, _, _, module, source in scored]

    # Record search event for future learning
    result_ids = [f"{r.module.category}/{r.module.id}" for r in results[:20]]
    record_search_event(query, result_ids, kb_path)

    return results[:limit]


def generate_changelog(kb_path: Path) -> dict | None:
    """Generate changelog from git log since the last changelog entry."""
    import subprocess

    # Find last changelog date
    changelog_dir = kb_path / ".changelog"
    changelog_dir.mkdir(parents=True, exist_ok=True)
    existing_dates = sorted([f.stem for f in changelog_dir.glob("*.json")])

    since_arg = ""
    if existing_dates:
        since_arg = f"--since={existing_dates[-1]}"

    # Get git log
    cmd = ["git", "-C", str(kb_path), "log", "--format=%H||%an||%s"]
    if since_arg:
        cmd.append(since_arg)
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return None

    commits = []
    for line in result.stdout.strip().split("\n"):
        parts = line.split("||", 2)
        if len(parts) != 3:
            continue
        commit_hash, author, message = parts

        # Get changed files — use git show (handles root commits, where
        # diff-tree returns nothing because there is no parent to diff against)
        show_result = subprocess.run(
            ["git", "-C", str(kb_path), "show", "--name-only", "--format=", commit_hash],
            capture_output=True, text=True, check=False,
        )
        changed_files = [f for f in show_result.stdout.strip().split("\n") if f.endswith(".json") and f not in ("index.json", "config.json")]

        if not changed_files:
            continue

        changes = {"added": [], "modified": [], "deleted": []}
        for f in changed_files:
            # Determine if added/modified/deleted by checking parent
            parent_result = subprocess.run(
                ["git", "-C", str(kb_path), "cat-file", "-e", f"{commit_hash}~1:{f}"],
                capture_output=True, check=False,
            )
            if parent_result.returncode != 0:
                changes["added"].append(f.replace(".json", ""))
            else:
                changes["modified"].append(f.replace(".json", ""))

        commits.append({
            "hash": commit_hash[:7],
            "author": author,
            "message": message,
            "changes": changes,
        })

    if not commits:
        return None

    from datetime import date
    changelog = {
        "date": date.today().isoformat(),
        "commits": commits,
    }
    # Save to .changelog/
    changelog_file = changelog_dir / f"{changelog['date']}.json"
    import json
    changelog_file.write_text(json.dumps(changelog, indent=2), encoding="utf-8")
    return changelog


def load_changelogs(kb_path: Path, days: int = 7) -> list[dict]:
    """Load changelog entries from the last N days."""
    changelog_dir = kb_path / ".changelog"
    if not changelog_dir.exists():
        return []

    from datetime import date, timedelta
    cutoff = date.today() - timedelta(days=days)
    import json

    changelogs = []
    for f in sorted(changelog_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            entry_date = date.fromisoformat(data.get("date", ""))
            if entry_date >= cutoff:
                changelogs.append(data)
        except (json.JSONDecodeError, ValueError):
            pass
    return changelogs


def load_module_changelog(kb_path: Path, module_key: str) -> list[dict]:
    """Load changelog entries for a specific module (category/id)."""
    changelog_dir = kb_path / ".changelog"
    if not changelog_dir.exists():
        return []

    import json
    entries = []
    for f in sorted(changelog_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            for commit in data.get("commits", []):
                all_changes = []
                for kind in ("added", "modified", "deleted"):
                    all_changes.extend(commit["changes"].get(kind, []))
                if module_key in all_changes:
                    entries.append({
                        "date": data["date"],
                        "hash": commit["hash"],
                        "author": commit["author"],
                        "message": commit["message"],
                    })
        except (json.JSONDecodeError, ValueError):
            pass
    return entries


def sanitize_config(config: Config) -> Config:
    """Return a copy of config with all api_key values replaced by '<LOCAL>' placeholder."""
    sanitized = config.model_copy(deep=True)
    for provider in sanitized.llm_providers.values():
        if provider.api_key:
            provider.api_key = "<LOCAL>"
    return sanitized


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
    # Auto-generate descriptions for categories that lack one
    for cat_name, cat in index.categories.items():
        if cat.description:
            continue
        all_tags: set[str] = set()
        titles: list[str] = []
        for m in cat.modules:
            all_tags.update(m.tags)
            titles.append(m.title)
        parts = [f"Topics: {', '.join(sorted(all_tags)[:8])}"]
        if titles:
            parts.append(f"Modules include: {'; '.join(titles[:5])}")
        cat.description = ". ".join(parts)
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


def save_staging_meta(meta: StagingMeta, staging_path: Path) -> None:
    _atomic_write(staging_path / f"{meta.module_id}.meta.json", meta.model_dump_json(indent=2))


def load_staging_meta(module_id: str, staging_path: Path) -> StagingMeta | None:
    path = staging_path / f"{module_id}.meta.json"
    if not path.exists():
        return None
    return StagingMeta.model_validate_json(path.read_text(encoding="utf-8"))


def delete_staging_meta(module_id: str, staging_path: Path) -> None:
    path = staging_path / f"{module_id}.meta.json"
    if path.exists():
        path.unlink()


def list_staging_meta(staging_path: Path) -> List[StagingMeta]:
    if not staging_path.exists():
        return []
    metas = []
    for json_file in staging_path.glob("*.meta.json"):
        try:
            metas.append(StagingMeta.model_validate_json(json_file.read_text(encoding="utf-8")))
        except Exception:
            pass
    return metas


def approve_from_staging(module_id: str, staging_path: Path, kb_path: Path) -> None:
    module = load_from_staging(module_id, staging_path)
    if module is None:
        raise FileNotFoundError(f"Staging module not found: {module_id}")
    save_module(module, kb_path)
    (staging_path / f"{module_id}.json").unlink()


# --- Telemetry & Bayesian ranking ---

_BAYESIAN_SMOOTHING = 0.5


def _telemetry_dir(kb_path: Path) -> Path:
    return kb_path / ".telemetry"


def _load_config_safe(kb_path: Path) -> Optional[Config]:
    cfg_path = kb_path / "config.json"
    if not cfg_path.exists():
        return None
    try:
        return Config.model_validate_json(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _telemetry_enabled(kb_path: Path, config: Config | None = None) -> bool:
    if config is None:
        config = _load_config_safe(kb_path)
    if config is None:
        return True
    return config.telemetry.enabled


def _hash_query(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()


def record_search_event(
    query: str, results_shown: List[str], kb_path: Path, config: Config | None = None
) -> None:
    """Record a search event for telemetry. Skips if telemetry is disabled."""
    if not _telemetry_enabled(kb_path, config):
        return
    tdir = _telemetry_dir(kb_path)
    tdir.mkdir(parents=True, exist_ok=True)
    query_stems: List[str] = []
    for w in _WORD_RE.findall(query.lower()):
        query_stems.extend(_stem(w).split())
    event = {
        "type": "search",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "query_hash": _hash_query(query),
        "query_terms": query_stems,
        "results_shown": results_shown,
    }
    with open(tdir / "search_events.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def record_load_event(
    module_id: str, category: str, kb_path: Path, config: Config | None = None
) -> None:
    """Record a module load event for telemetry. Skips if telemetry is disabled."""
    if not _telemetry_enabled(kb_path, config):
        return
    tdir = _telemetry_dir(kb_path)
    tdir.mkdir(parents=True, exist_ok=True)
    event = {
        "type": "load",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "module_id": module_id,
        "category": category,
    }
    with open(tdir / "search_events.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def load_search_events(kb_path: Path) -> List[dict]:
    """Load all telemetry events from disk."""
    tdir = _telemetry_dir(kb_path)
    events_file = tdir / "search_events.jsonl"
    if not events_file.exists():
        return []
    events = []
    for line in events_file.read_text(encoding="utf-8").strip().split("\n"):
        if line:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return events


def save_rank_model(priors: Dict[str, Dict[str, float]], event_count: int, kb_path: Path) -> None:
    """Persist computed Bayesian priors to disk for fast reload."""
    tdir = _telemetry_dir(kb_path)
    tdir.mkdir(parents=True, exist_ok=True)
    model = {
        "event_count": event_count,
        "smoothing": _BAYESIAN_SMOOTHING,
        "priors": priors,
    }
    with open(tdir / "rank_model.json", "w", encoding="utf-8") as f:
        json.dump(model, f, indent=2)


def load_rank_model(kb_path: Path, expected_event_count: int) -> Dict[str, Dict[str, float]] | None:
    """Load cached Bayesian priors if event count matches (i.e., cache is fresh)."""
    model_file = _telemetry_dir(kb_path) / "rank_model.json"
    if not model_file.exists():
        return None
    try:
        model = json.loads(model_file.read_text(encoding="utf-8"))
        if model.get("event_count") != expected_event_count:
            return None
        return model.get("priors", {})
    except (json.JSONDecodeError, KeyError):
        return None


def compute_bayesian_priors(kb_path: Path) -> Dict[str, Dict[str, float]]:
    """Compute P(module_id | query_term) priors from historical search→load events.

    Returns a dict mapping stemmed query terms to {module_key: probability} dicts.
    Uses time-window matching: a load confirms the most recent prior search whose
    results contained the loaded module.
    """
    events = load_search_events(kb_path)
    if not events:
        return {}

    # Return cached priors if event count hasn't changed
    cached = load_rank_model(kb_path, len(events))
    if cached is not None:
        return cached

    searches: List[dict] = []
    loads: List[dict] = []
    for e in events:
        if e.get("type") == "search":
            searches.append(e)
        elif e.get("type") == "load":
            loads.append(e)

    if not searches or not loads:
        return {}

    # Collect all unique module keys for smoothing
    all_module_keys: set[str] = set()
    for s in searches:
        all_module_keys.update(s.get("results_shown", []))
    for l in loads:
        all_module_keys.add(f"{l['category']}/{l['module_id']}")

    # Count: for each load, find the most recent prior search containing that module
    #   term → module_key → positive_count
    #   term → total_search_count
    term_positive: Dict[str, Dict[str, int]] = {}
    term_total: Dict[str, int] = {}

    for load in loads:
        module_key = f"{load['category']}/{load['module_id']}"
        load_ts = load["timestamp"]
        best_search = None
        for s in searches:
            if s["timestamp"] < load_ts and module_key in s.get("results_shown", []):
                if best_search is None or s["timestamp"] > best_search["timestamp"]:
                    best_search = s
        if best_search is None:
            continue
        for term in best_search.get("query_terms", []):
            if term not in term_positive:
                term_positive[term] = {}
                term_total[term] = 0
            term_positive[term][module_key] = term_positive[term].get(module_key, 0) + 1

    # Count total searches per term
    for s in searches:
        for term in s.get("query_terms", []):
            term_total[term] = term_total.get(term, 0) + 1

    # Compute smoothed probabilities
    num_modules = len(all_module_keys) if all_module_keys else 1
    priors: Dict[str, Dict[str, float]] = {}
    for term, total in term_total.items():
        priors[term] = {}
        positives = term_positive.get(term, {})
        for mk in all_module_keys:
            count = positives.get(mk, 0)
            priors[term][mk] = (count + _BAYESIAN_SMOOTHING) / (total + _BAYESIAN_SMOOTHING * num_modules)

    # Persist to disk cache
    save_rank_model(priors, len(events), kb_path)
    return priors


# ── Phase 3A: Health scoring ──


def _freshness_score(module: Any, now: datetime | None = None) -> float:
    """Score module freshness based on days since update (0-100)."""
    now = now or datetime.now(timezone.utc)
    updated = module.updated_at
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    days = (now - updated).days

    # Check expires_at first
    if module.metadata.expires_at is not None:
        exp = module.metadata.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if now >= exp:
            return 0.0

    # Check review_interval_days
    if module.metadata.review_interval_days is not None:
        if days > module.metadata.review_interval_days:
            return 0.0

    if days <= 30:
        return 100.0
    elif days <= 60:
        return 75.0
    elif days <= 90:
        return 50.0
    elif days <= 180:
        return 25.0
    else:
        return 0.0


def _usage_score(module_id: str, category: str, kb_path: Path) -> float:
    """Score module usage based on recent load events (0-100)."""
    from datetime import timedelta
    events = load_search_events(kb_path)
    now = datetime.now(timezone.utc)
    cutoff_30 = now - timedelta(days=30)
    cutoff_60 = now - timedelta(days=60)
    cutoff_90 = now - timedelta(days=90)

    latest_load = None
    load_count_30d = 0

    for evt in events:
        if evt.get("type") != "load":
            continue
        if evt.get("module_id") != module_id:
            continue
        if evt.get("category") != category:
            continue
        try:
            ts = datetime.fromisoformat(evt["timestamp"])
        except (ValueError, KeyError):
            continue
        if ts >= cutoff_30:
            load_count_30d += 1
        if latest_load is None or ts > latest_load:
            latest_load = ts

    if latest_load is None:
        return 0.0

    if latest_load >= cutoff_30:
        return 100.0
    elif latest_load >= cutoff_60:
        return 70.0
    elif latest_load >= cutoff_90:
        return 40.0
    else:
        return 0.0


def _load_count_30d(module_id: str, category: str, kb_path: Path) -> int:
    """Count load events for a module in the last 30 days."""
    from datetime import timedelta
    events = load_search_events(kb_path)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=30)
    count = 0
    for evt in events:
        if evt.get("type") != "load":
            continue
        if evt.get("module_id") != module_id:
            continue
        if evt.get("category") != category:
            continue
        try:
            ts = datetime.fromisoformat(evt["timestamp"])
        except (ValueError, KeyError):
            continue
        if ts >= cutoff:
            count += 1
    return count


def _last_load_time(module_id: str, category: str, kb_path: Path) -> datetime | None:
    """Get the most recent load time for a module."""
    events = load_search_events(kb_path)
    latest = None
    for evt in events:
        if evt.get("type") != "load":
            continue
        if evt.get("module_id") != module_id:
            continue
        if evt.get("category") != category:
            continue
        try:
            ts = datetime.fromisoformat(evt["timestamp"])
        except (ValueError, KeyError):
            continue
        if latest is None or ts > latest:
            latest = ts
    return latest


def _completeness_score(module: Any) -> float:
    """Score module completeness based on content field population (0-100)."""
    score = 0.0
    c = module.content
    if c.overview:
        score += 30
    if c.details and len(c.details) >= 20:
        score += 30
    if c.examples:
        score += 20
    if c.caveats:
        score += 10
    if c.references:
        score += 10
    return score


def compute_module_health(module: Any, kb_path: Path) -> Any:
    """Compute health score for a single module."""
    from knowledge_manager.schemas import HealthScore, ModuleHealth

    freshness = _freshness_score(module)
    usage = _usage_score(module.id, module.category, kb_path)
    completeness = _completeness_score(module)
    overall = freshness * 0.35 + usage * 0.35 + completeness * 0.30

    issues = []
    if usage == 0:
        issues.append("zombie")
    if freshness == 0:
        if module.metadata.expires_at and module.metadata.expires_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
            issues.append("expired")
        else:
            issues.append("stale")
    if completeness < 70:
        issues.append("incomplete")

    now = datetime.now(timezone.utc)
    updated = module.updated_at
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    days_since_update = (now - updated).days

    return ModuleHealth(
        module_id=module.id,
        category=module.category,
        title=module.title,
        status=module.metadata.status,
        score=HealthScore(freshness=freshness, usage=usage, completeness=completeness, overall=round(overall, 1)),
        issues=issues,
        last_load=_last_load_time(module.id, module.category, kb_path),
        load_count_30d=_load_count_30d(module.id, module.category, kb_path),
        days_since_update=days_since_update,
    )


def generate_health_report(kb_path: Path) -> Any:
    """Generate a full knowledge base health report."""
    from knowledge_manager.schemas import KBHealthReport, CategoryHealth

    index = load_index(kb_path)
    if index is None:
        return KBHealthReport()

    all_health: list = []
    category_scores: dict[str, list[float]] = {}
    category_at_risk: dict[str, int] = {}

    for cat_name, cat_data in index.categories.items():
        category_scores[cat_name] = []
        category_at_risk[cat_name] = 0
        for mod_summary in cat_data.modules:
            module = load_module(mod_summary.id, cat_name, kb_path)
            if module is None:
                continue
            h = compute_module_health(module, kb_path)
            all_health.append(h)
            category_scores[cat_name].append(h.score.overall)
            if h.score.overall < 40:
                category_at_risk[cat_name] += 1

    total_modules = len(all_health)
    total_categories = len(index.categories)
    overall_score = round(sum(h.score.overall for h in all_health) / total_modules, 1) if total_modules > 0 else 0.0

    breakdown = {}
    for cat_name in index.categories:
        scores = category_scores.get(cat_name, [])
        avg = round(sum(scores) / len(scores), 1) if scores else 0.0
        breakdown[cat_name] = CategoryHealth(
            name=cat_name,
            total_modules=len(scores),
            avg_score=avg,
            at_risk_count=category_at_risk.get(cat_name, 0),
        )

    at_risk = sorted(
        [h for h in all_health if h.score.overall < 40 or h.issues],
        key=lambda h: h.score.overall,
    )

    return KBHealthReport(
        total_modules=total_modules,
        total_categories=total_categories,
        overall_score=overall_score,
        category_breakdown=breakdown,
        at_risk_modules=at_risk,
    )


# ── Phase 3B: Usage analytics ──


def aggregate_usage_stats(kb_path: Path, period_days: int = 30) -> Any:
    """Aggregate usage statistics from telemetry events."""
    from datetime import timedelta
    from knowledge_manager.schemas import UsageStats, ModuleUsageEntry, UnmatchedQueryEntry, DailyActivityPoint

    events = load_search_events(kb_path)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=period_days)

    # Filter events within period
    period_events = []
    for evt in events:
        try:
            ts = datetime.fromisoformat(evt["timestamp"])
        except (ValueError, KeyError):
            continue
        if ts >= cutoff:
            period_events.append(evt)

    # Count searches and loads
    searches = [e for e in period_events if e.get("type") == "search"]
    loads = [e for e in period_events if e.get("type") == "load"]
    total_searches = len(searches)
    total_loads = len(loads)

    # Conversion rate: searches that resulted in at least one load within 30s
    sessions: dict[str, list[dict]] = {}
    for e in period_events:
        sid = e.get("session_id", "default")
        sessions.setdefault(sid, []).append(e)

    conversions = 0
    for sid, evts in sessions.items():
        search_times = [datetime.fromisoformat(e["timestamp"]) for e in evts if e.get("type") == "search"]
        load_times = [datetime.fromisoformat(e["timestamp"]) for e in evts if e.get("type") == "load"]
        for st in search_times:
            for lt in load_times:
                if timedelta(seconds=0) <= (lt - st) <= timedelta(seconds=30):
                    conversions += 1
                    break
            else:
                continue
            break

    conversion_rate = round(conversions / total_searches * 100, 1) if total_searches else 0.0
    total_sessions = len(sessions)
    avg_searches = round(total_searches / total_sessions, 1) if total_sessions else 0.0

    # Top modules by load count
    load_counts: dict[tuple[str, str], int] = {}
    for e in loads:
        mid = e.get("module_id", "")
        cat = e.get("category", "")
        if mid and cat:
            key = (cat, mid)
            load_counts[key] = load_counts.get(key, 0) + 1

    top_modules = []
    index = load_index(kb_path)
    for (cat, mid), count in sorted(load_counts.items(), key=lambda x: -x[1])[:10]:
        title = mid
        if index and cat in index.categories:
            for m in index.categories[cat].modules:
                if m.id == mid:
                    title = m.title
                    break
        top_modules.append(ModuleUsageEntry(module_id=mid, category=cat, title=title, load_count=count, trend="stable"))

    # Unmatched queries (searches with no results shown)
    unmatched: dict[str, tuple[list[str], int]] = {}
    for e in searches:
        results_shown = e.get("results_shown", [])
        if not results_shown:
            qhash = e.get("query_hash", "unknown")
            terms = e.get("query_terms", [])
            if qhash in unmatched:
                unmatched[qhash] = (terms, unmatched[qhash][1] + 1)
            else:
                unmatched[qhash] = (terms, 1)

    unmatched_queries = [
        UnmatchedQueryEntry(query_hash=h, query_terms=t, count=c)
        for h, (t, c) in sorted(unmatched.items(), key=lambda x: -x[1][1])[:5]
    ]

    # Daily activity
    daily: dict[str, tuple[int, int]] = {}
    for e in period_events:
        try:
            day = datetime.fromisoformat(e["timestamp"]).strftime("%Y-%m-%d")
        except (ValueError, KeyError):
            continue
        if day not in daily:
            daily[day] = (0, 0)
        s, l = daily[day]
        if e.get("type") == "search":
            daily[day] = (s + 1, l)
        elif e.get("type") == "load":
            daily[day] = (s, l + 1)

    daily_activity = [
        DailyActivityPoint(date=d, searches=s, loads=l)
        for d, (s, l) in sorted(daily.items())
    ]

    return UsageStats(
        period_days=period_days,
        total_searches=total_searches,
        total_loads=total_loads,
        conversion_rate=conversion_rate,
        total_sessions=total_sessions,
        avg_searches_per_session=avg_searches,
        top_modules=top_modules,
        unmatched_queries=unmatched_queries,
        daily_activity=daily_activity,
    )


# ── Phase 3C: Graph analysis ──


def analyze_graph(kb_path: Path) -> Any:
    """Analyze the knowledge graph: hubs, orphans, broken links."""
    from knowledge_manager.schemas import GraphStats, HubEntry, OrphanEntry, BrokenLinkEntry

    index = load_index(kb_path)
    if index is None:
        return GraphStats()

    graph = index.graph
    # Build title lookup
    titles: dict[str, str] = {}
    all_modules: set[str] = set()
    for cat_name, cat in index.categories.items():
        for m in cat.modules:
            key = f"{cat_name}/{m.id}"
            all_modules.add(key)
            titles[key] = m.title

    total_nodes = len(all_modules)
    total_edges = sum(len(targets) for targets in graph.values())

    # In-degree calculation
    in_degree: dict[str, int] = {m: 0 for m in all_modules}
    for src, targets in graph.items():
        for t in targets:
            if t in in_degree:
                in_degree[t] += 1

    # Hub modules (top 5 by in-degree)
    hubs = sorted(
        [HubEntry(
            module_id=k.split("/", 1)[1] if "/" in k else k,
            category=k.split("/", 1)[0] if "/" in k else "",
            title=titles.get(k, k),
            in_degree=in_degree.get(k, 0),
            out_degree=len(graph.get(k, [])),
        ) for k in all_modules if in_degree.get(k, 0) > 0],
        key=lambda h: -h.in_degree,
    )[:5]

    # Orphan modules (no in-degree and no out-degree in graph)
    ok_keys: set[str] = set()
    for k in all_modules:
        if k in graph and graph[k]:
            ok_keys.add(k)  # has outgoing edges
    for targets in graph.values():
        for t in targets:
            if t in all_modules:
                ok_keys.add(t)  # has incoming edges

    orphans = sorted([
        OrphanEntry(
            module_id=k.split("/", 1)[1] if "/" in k else k,
            category=k.split("/", 1)[0] if "/" in k else "",
            title=titles.get(k, ""),
            status="published",
        ) for k in all_modules if k not in ok_keys
    ], key=lambda o: o.module_id)

    # Broken links
    broken = []
    for src, targets in graph.items():
        for t in targets:
            if t not in all_modules:
                broken.append(BrokenLinkEntry(source=src, target=t, target_status="missing"))
            else:
                # Check if target is deprecated or archived
                for cat_name, cat in index.categories.items():
                    for m in cat.modules:
                        mk = f"{cat_name}/{m.id}"
                        if mk == t and m.tags:  # just get status via index lookup
                            pass

    # Check for deprecated/archived links
    for cat_name, cat in index.categories.items():
        for m in cat.modules:
            mk = f"{cat_name}/{m.id}"
            if mk in graph or any(mk in targets for targets in graph.values()):
                mod = load_module(m.id, cat_name, kb_path)
                if mod and mod.metadata.status in ("deprecated", "archived"):
                    for src, targets in graph.items():
                        if mk in targets and src in titles:
                            broken.append(BrokenLinkEntry(
                                source=src, target=mk,
                                target_status=mod.metadata.status,
                            ))

    # Density
    n = total_nodes
    max_edges = n * (n - 1) if n > 1 else 1
    density = round(total_edges / max_edges, 4)

    return GraphStats(
        total_nodes=total_nodes,
        total_edges=total_edges,
        density=density,
        hub_modules=hubs,
        orphan_modules=orphans,
        broken_links=broken,
        clusters=[],
    )


def detect_clusters(kb_path: Path) -> list[Any]:
    """Detect connected components in the knowledge graph."""
    from knowledge_manager.schemas import ClusterEntry

    index = load_index(kb_path)
    if index is None:
        return []

    graph = index.graph
    all_nodes = set()
    for cat_name, cat in index.categories.items():
        for m in cat.modules:
            all_nodes.add(f"{cat_name}/{m.id}")

    # Build undirected adjacency
    adj: dict[str, set[str]] = {n: set() for n in all_nodes}
    for src, targets in graph.items():
        if src not in adj:
            adj[src] = set()
        for t in targets:
            if t in adj:
                adj[src].add(t)
                adj[t].add(src)

    visited: set[str] = set()
    clusters = []

    def dfs(node: str, comp: list[str]):
        visited.add(node)
        comp.append(node)
        for neighbor in adj.get(node, []):
            if neighbor not in visited:
                dfs(neighbor, comp)

    for node in all_nodes:
        if node not in visited:
            comp: list[str] = []
            dfs(node, comp)
            if len(comp) >= 2:
                # Derive label from shared tags or dominant category
                categories = [n.split("/", 1)[0] for n in comp]
                dominant = max(set(categories), key=categories.count) if categories else "general"
                clusters.append(ClusterEntry(
                    id=f"cluster-{len(clusters) + 1}",
                    label=dominant,
                    module_count=len(comp),
                    modules=sorted(comp),
                ))

    return sorted(clusters, key=lambda c: -c.module_count)


# ── Phase 3D: Recommendations ──


def generate_recommendations(kb_path: Path) -> Any:
    """Generate actionable recommendations for knowledge base improvement."""
    from knowledge_manager.schemas import (
        RecommendationReport, Recommendation, RecommendationType,
    )

    index = load_index(kb_path)
    if index is None:
        return RecommendationReport()

    archive_candidates = []
    enrichment_needed = []
    suggested_links = []
    review_reminders = []

    now = datetime.now(timezone.utc)

    # Build tag index for link suggestions
    module_tags: dict[str, set[str]] = {}
    for cat_name, cat in index.categories.items():
        for m in cat.modules:
            key = f"{cat_name}/{m.id}"
            mod = load_module(m.id, cat_name, kb_path)
            if mod:
                module_tags[key] = set(mod.metadata.tags)

    for cat_name, cat in index.categories.items():
        for m in cat.modules:
            key = f"{cat_name}/{m.id}"
            mod = load_module(m.id, cat_name, kb_path)
            if mod is None:
                continue

            h = compute_module_health(mod, kb_path)
            status = mod.metadata.status

            # Archive candidates
            archive_score = 0.0
            archive_reasons = []
            if "zombie" in h.issues and h.score.overall < 20:
                archive_score = 0.9
                archive_reasons.append("ZOMBIE")
            if h.score.usage == 0 and (h.days_since_update > 180):
                archive_score = max(archive_score, 0.7)
                archive_reasons.append(f"STALE ({h.days_since_update}d)")
            if mod.metadata.expires_at and mod.metadata.expires_at.replace(tzinfo=timezone.utc) <= now:
                archive_score = max(archive_score, 0.95)
                archive_reasons.append("EXPIRED")
            if h.score.overall < 20 and status != "archived":
                archive_score = max(archive_score, 0.6)
                archive_reasons.append("LOW_SCORE")

            if archive_score > 0.5 and status not in ("archived", "deprecated"):
                archive_candidates.append(Recommendation(
                    type=RecommendationType.ARCHIVE,
                    module_id=m.id, category=cat_name, title=m.title,
                    score=archive_score,
                    reason=", ".join(archive_reasons),
                    detail={"health_score": h.score.overall, "issues": h.issues},
                ))

            # Enrichment suggestions
            if h.score.completeness < 80:
                missing = []
                if not mod.content.examples:
                    missing.append("examples")
                if not mod.content.caveats:
                    missing.append("caveats")
                if not mod.content.references:
                    missing.append("references")
                if missing:
                    enrichment_needed.append(Recommendation(
                        type=RecommendationType.ENRICH,
                        module_id=m.id, category=cat_name, title=m.title,
                        score=round((80 - h.score.completeness) / 80, 2),
                        reason=f"Missing: {', '.join(missing)}",
                        detail={"missing_fields": missing},
                    ))

            # Review reminders
            if mod.metadata.review_interval_days and h.days_since_update > mod.metadata.review_interval_days:
                review_reminders.append(Recommendation(
                    type=RecommendationType.REVIEW,
                    module_id=m.id, category=cat_name, title=m.title,
                    score=0.8,
                    reason=f"review_interval ({mod.metadata.review_interval_days}d) expired",
                    detail={"days_overdue": h.days_since_update - mod.metadata.review_interval_days},
                ))

    # Link suggestions — find modules with shared tags not already linked
    existing_links: set[tuple[str, str]] = set()
    for src, targets in index.graph.items():
        for t in targets:
            existing_links.add((src, t))
            existing_links.add((t, src))

    seen_pairs: set[tuple[str, str]] = set()
    for k1, tags1 in module_tags.items():
        for k2, tags2 in module_tags.items():
            if k1 >= k2:
                continue
            pair = (k1, k2)
            if pair in existing_links or pair in seen_pairs:
                continue
            shared = tags1 & tags2
            if len(shared) >= 2:
                seen_pairs.add(pair)
                suggested_links.append(Recommendation(
                    type=RecommendationType.LINK,
                    module_id=k1, category="", title=f"{k1} ↔ {k2}",
                    score=min(1.0, len(shared) / 5.0),
                    reason=f"Shared tags: {', '.join(sorted(shared)[:3])}",
                    detail={"module_a": k1, "module_b": k2, "shared_tags": sorted(shared)},
                ))

    suggested_links.sort(key=lambda r: -r.score)

    return RecommendationReport(
        archive_candidates=sorted(archive_candidates, key=lambda r: -r.score)[:10],
        enrichment_needed=sorted(enrichment_needed, key=lambda r: -r.score)[:10],
        suggested_links=suggested_links[:10],
        review_reminders=sorted(review_reminders, key=lambda r: -r.score)[:5],
    )


# ── Phase 4B: Federation ──


def load_federation(kb_path: Path) -> dict:
    """Load and validate all federation namespace indices.

    Returns a dict mapping namespace name → {index, path, description, search_default}.
    Returns empty dict if no federation namespaces are configured.
    """
    import logging
    _logger = logging.getLogger("knowledge_manager")

    cfg = _load_config_safe(kb_path)
    if cfg is None or not cfg.federation.namespaces:
        return {}

    namespaces: dict = {}
    for ns_name, ns_cfg in cfg.federation.namespaces.items():
        ns_path = (kb_path / ns_cfg.kb_path).resolve()
        if not ns_path.exists():
            _logger.warning("Federation namespace '%s': path %s does not exist, skipping", ns_name, ns_path)
            continue
        ns_index = load_index(ns_path)
        if ns_index is None:
            _logger.warning("Federation namespace '%s': no index.json at %s, skipping", ns_name, ns_path)
            continue
        namespaces[ns_name] = {
            "index": ns_index,
            "path": ns_path,
            "description": ns_cfg.description,
            "search_default": ns_cfg.search_default,
        }
    return namespaces


# ── M1: Knowledge tree functions ──


def get_tree(kb_path: Path) -> "TreeNode":
    from knowledge_manager.schemas import TreeNode, TreeNodeType

    index = load_index(kb_path)
    if index is None:
        return TreeNode(id="root", type=TreeNodeType.ROOT, title="Empty KB")
    tree_val = getattr(index, "tree", None)
    if tree_val is not None:
        if isinstance(tree_val, dict):
            from knowledge_manager.schemas import TreeNode as TN
            try:
                return TN.model_validate(tree_val)
            except Exception:
                pass
        return tree_val
    return _build_tree_from_categories(index)


def get_subtree(cat: str, mod_id: str, kb_path: Path) -> "TreeNode | None":
    from knowledge_manager.schemas import TreeNode, TreeNodeType

    module = load_module(mod_id, cat, kb_path)
    if module is None:
        return None
    node = TreeNode(
        id=f"{cat}/{mod_id}",
        type=TreeNodeType.MODULE,
        title=module.title,
        summary=module.summary,
        path=f"{cat}/{mod_id}",
        confidence=module.metadata.confidence,
        status=module.metadata.status,
        tags=module.metadata.tags,
    )
    for ref in module.metadata.related_modules:
        parts = ref.split("/", 1)
        if len(parts) == 2:
            related = load_module(parts[1], parts[0], kb_path)
            if related:
                node.children.append(TreeNode(
                    id=ref,
                    type=TreeNodeType.MODULE,
                    title=related.title,
                    summary=related.summary,
                    path=ref,
                    confidence=related.metadata.confidence,
                    status=related.metadata.status,
                    tags=related.metadata.tags,
                ))
    return node


def _build_tree_from_categories(index: "Index") -> "TreeNode":
    from knowledge_manager.schemas import TreeNode, TreeNodeType

    stats = index.stats
    root = TreeNode(
        id="root",
        type=TreeNodeType.ROOT,
        title="Knowledge Base",
        summary=f"{stats.total_modules} modules across {stats.categories} categories",
    )
    for cat_name, cat in index.categories.items():
        cat_node = TreeNode(
            id=cat_name,
            type=TreeNodeType.CATEGORY,
            title=cat_name,
            summary=cat.description,
            path=cat_name,
            module_count=len(cat.modules),
            word_count=sum(m.word_count for m in cat.modules),
        )
        for mod in cat.modules:
            cat_node.children.append(TreeNode(
                id=f"{cat_name}/{mod.id}",
                type=TreeNodeType.MODULE,
                title=mod.title,
                summary=mod.summary,
                path=f"{cat_name}/{mod.id}",
                tags=mod.tags,
            ))
        root.children.append(cat_node)
    root.module_count = stats.total_modules
    root.word_count = stats.total_words
    return root


def save_tree(tree: "TreeNode", kb_path: Path) -> None:
    from knowledge_manager.schemas import TreeNode as TNode

    index = load_index(kb_path)
    if index is None:
        index = _create_empty_index()
    index.tree = tree
    save_index(index, kb_path)


def find_modules_under(node: "TreeNode") -> list[str]:
    from knowledge_manager.schemas import TreeNodeType

    keys: list[str] = []

    def _collect(n: "TreeNode") -> None:
        if n.type == TreeNodeType.MODULE:
            keys.append(n.path or n.id)
        for child in n.children:
            _collect(child)

    _collect(node)
    return keys


def _create_empty_index() -> "Index":
    from knowledge_manager.schemas import Index
    return Index(description="")