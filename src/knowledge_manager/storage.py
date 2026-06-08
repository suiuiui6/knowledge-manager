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

from knowledge_manager.schemas import Config, Index, Module


_FIELD_WEIGHTS = {"title": 5, "tag": 3, "summary": 2, "overview": 1, "details": 1, "examples": 0, "caveats": 0}
_WORD_RE = re.compile(r"\w+")
_EN_STEMMER: Any = _snowball_stemmer("english")

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

    query_stems = [_stem(w) for w in _WORD_RE.findall(query.lower())]
    if not query_stems:
        return {}

    doc_tfs: List[Dict[str, int]] = []
    doc_ids: List[str] = []
    df: Dict[str, int] = {}
    doc_lengths: List[int] = []

    for module in modules:
        text = _module_full_text(module)
        words = [w.lower() for w in _WORD_RE.findall(text)]
        stemmed = [_stem(w) for w in words]

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


def search_modules(query: str, kb_path: Path, category: str | None = None, limit: int = 15, boost_ids: List[str] | None = None) -> List[SearchResult]:
    terms = query.lower().split()
    if not terms:
        return []

    all_modules = list_modules(kb_path)
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

        term_stem = _stem(term)
        for field_name in field_names:
            if term_stem in field_stems.get(field_name, set()):
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
            "tag": {_stem(tag) for tag in module.metadata.tags},
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
    query_stems = [_stem(t) for t in terms]

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

    # Primary: confidence-weighted heuristic score (with session boost).
    # Secondary: match quality. Tertiary: Bayesian prior. Fourth: BM25.
    scored.sort(
        key=lambda item: (
            _session_boost(item[3].id, item[1]) * _CONFIDENCE_WEIGHT.get(item[3].metadata.confidence, 0.85),
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
    query_stems = [_stem(w) for w in _WORD_RE.findall(query.lower())]
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

