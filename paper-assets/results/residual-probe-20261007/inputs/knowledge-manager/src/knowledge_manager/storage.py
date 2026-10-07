import copy
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

from knowledge_manager.materialized_views import (
    invalidate_materialized_views,
    load_fresh_materialized_view,
    store_materialized_view,
)
from knowledge_manager.module_cache import ModuleCache
from knowledge_manager.policy import evaluate_module_policy, merge_agent_routing_policy
from knowledge_manager.schemas import (
    Config,
    Index,
    Module,
    RoutingPolicyConfig,
    StagingMeta,
)
from knowledge_manager.tenancy import TenantContext, module_visible_to_tenant


_FIELD_WEIGHTS = {"title": 5, "tag": 3, "summary": 2, "overview": 1, "details": 1, "examples": 0, "caveats": 0}
_WORD_RE = re.compile(r"\w+")
_EN_STEMMER: Any = _snowball_stemmer("english")
_CJK_RE = re.compile(r"[一-鿿㐀-䶿豈-﫿]")

_QUALITY_EXACT = 3
_QUALITY_STEM = 2
_QUALITY_PARTIAL = 1

# BM25 parameters
_BM25_K1 = 1.2
_SEARCH_EVENTS_CACHE: dict[str, tuple[int, int, list[dict[str, Any]]]] = {}
_PRIORS_CACHE: dict[str, tuple[tuple[int, str], Dict[str, Dict[str, float]]]] = {}
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

_MODULE_CACHE = ModuleCache()


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


def _search_document_from_module(module: Module) -> dict[str, Any]:
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
        "field_stems": {
            "title": sorted(_field_stems(module.title)),
            "tag": sorted({s for tag in module.metadata.tags for s in _stem(tag).split()}),
            "summary": sorted(_field_stems(module.summary)),
            "overview": sorted(_field_stems(module.content.overview)),
            "details": sorted(_field_stems(module.content.details)),
            "examples": sorted(_field_stems(module.content.examples)),
            "caveats": sorted(_field_stems(module.content.caveats)),
        },
    }


def _document_full_text(document: Mapping[str, Any]) -> str:
    return " ".join(
        [
            str(document.get("title", "")),
            " ".join(str(tag) for tag in document.get("tags", [])),
            str(document.get("summary", "")),
            str(document.get("overview", "")),
            str(document.get("details", "")),
            str(document.get("examples", "")),
            str(document.get("references", "")),
            str(document.get("caveats", "")),
        ]
    )


def _module_from_search_document(document: Mapping[str, Any]) -> Module:
    return Module.model_validate(
        {
            "id": document["module_id"],
            "category": document["category"],
            "title": document.get("title", ""),
            "summary": document.get("summary", ""),
            "created_at": document.get("created_at"),
            "updated_at": document.get("updated_at"),
            "content": {
                "overview": document.get("overview", ""),
                "details": document.get("details", ""),
                "examples": document.get("examples", ""),
                "references": document.get("references", ""),
                "caveats": document.get("caveats", ""),
            },
            "metadata": {
                "tags": document.get("tags", []),
                "related_modules": document.get("related_modules", []),
                "confidence": document.get("confidence", "medium"),
                "tenant_id": document.get("tenant_id", ""),
                "workspace_id": document.get("workspace_id", ""),
                "stale_due_to_source_change": document.get("stale_due_to_source_change", False),
                "expires_at": document.get("expires_at"),
                "status": document.get("status", "published"),
            },
        }
    )


def _projection_doc_visible_to_tenant(document: Mapping[str, Any], tenant: TenantContext | None) -> bool:
    if tenant is None:
        return True
    module_tenant = str(document.get("tenant_id", ""))
    if module_tenant == tenant.tenant_id:
        return True
    return tenant.allow_global_reads and not module_tenant


def _document_key(document: Mapping[str, Any]) -> str:
    return f"{document.get('category', '')}/{document.get('module_id', '')}"


def _atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(data, encoding="utf-8")
    os.replace(tmp, path)


def _invalidate_module_cache(kb_path: Path) -> None:
    _MODULE_CACHE.invalidate(kb_path)


def _module_set_fingerprint(kb_path: Path) -> tuple[int, int]:
    files = [
        path
        for path in kb_path.rglob("*.json")
        if path.name != "index.json" and not any(part.startswith(".") for part in path.relative_to(kb_path).parts[:-1])
    ]
    total_mtime = sum(int(path.stat().st_mtime_ns) for path in files)
    return len(files), total_mtime


def _upsert_index_entry(module: Module, kb_path: Path) -> None:
    index = load_index(kb_path) or Index()
    index.remove_module(module.id, module.category)
    index.add_module(module)
    save_index(index, kb_path)


def _remove_index_entry(module_id: str, category: str, kb_path: Path) -> None:
    index = load_index(kb_path)
    if index is None:
        return
    removed = index.remove_module(module_id, category)
    if removed:
        save_index(index, kb_path)


def _run_noncritical_save_side_effects(module: Module, kb_path: Path, existed: bool) -> None:
    # M5: also write Markdown
    try:
        from knowledge_manager.sync import MarkdownSync

        MarkdownSync.sync_on_save(module, kb_path)
    except Exception:
        pass

    event = "module.updated" if existed else "module.created"
    try:
        from knowledge_manager.webhooks import emit_event

        emit_event(kb_path, event, module.id, module.category, {"title": module.title})
    except Exception:
        pass

    try:
        from knowledge_manager.lexical_index import update_lexical_index_for_module

        update_lexical_index_for_module(kb_path, module)
    except Exception:
        pass

    try:
        from knowledge_manager.search_projection import update_search_projection_for_module

        update_search_projection_for_module(kb_path, module)
    except Exception:
        pass

    try:
        from knowledge_manager.recommendation_index import update_recommendation_index_for_module

        update_recommendation_index_for_module(kb_path, module)
    except Exception:
        pass


def _run_noncritical_delete_side_effects(module_id: str, category: str, kb_path: Path) -> None:
    try:
        from knowledge_manager.webhooks import emit_event

        emit_event(kb_path, "module.deleted", module_id, category)
    except Exception:
        pass

    try:
        from knowledge_manager.lexical_index import delete_lexical_index_for_module

        delete_lexical_index_for_module(kb_path, category, module_id)
    except Exception:
        pass

    try:
        from knowledge_manager.search_projection import remove_search_projection_for_module

        remove_search_projection_for_module(kb_path, category, module_id)
    except Exception:
        pass

    try:
        from knowledge_manager.recommendation_index import remove_recommendation_index_for_module

        remove_recommendation_index_for_module(kb_path, category, module_id)
    except Exception:
        pass


def run_deferred_maintenance_action(kb_path: Path, action: str, payload: Mapping[str, Any]) -> None:
    if action == "module_saved":
        module_payload = payload.get("module")
        if module_payload is None:
            raise ValueError("module_saved maintenance payload requires module")
        module = Module.model_validate(module_payload)
        _run_noncritical_save_side_effects(module, kb_path, bool(payload.get("existed")))
        return
    if action == "module_deleted":
        module_id = str(payload.get("module_id") or "")
        category = str(payload.get("category") or "")
        if not module_id or not category:
            raise ValueError("module_deleted maintenance payload requires module_id and category")
        _run_noncritical_delete_side_effects(module_id, category, kb_path)
        return
    raise ValueError(f"Unsupported maintenance action: {action}")


def schedule_maintenance_job(kb_path: Path, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    from knowledge_manager.job_worker import enqueue_local_maintenance

    return enqueue_local_maintenance(kb_path, action=action, payload=payload)


def save_module(
    module: Module,
    kb_path: Path,
    defer_noncritical: bool = True,
    maintenance_state: list[dict[str, Any]] | None = None,
) -> None:
    path = module.to_file_path(kb_path)
    existed = path.exists()
    if existed:
        existing = load_module(module.id, module.category, kb_path)
        if existing is not None:
            before = existing.model_dump(mode="json")
            after = module.model_dump(mode="json")
            before.pop("updated_at", None)
            after.pop("updated_at", None)
            if before != after:
                module.updated_at = datetime.now(timezone.utc)
            else:
                module.updated_at = existing.updated_at
    _atomic_write(path, module.model_dump_json(indent=2))
    _upsert_index_entry(module, kb_path)
    _invalidate_module_cache(kb_path)
    invalidate_materialized_views(kb_path)
    if defer_noncritical:
        state = schedule_maintenance_job(
            kb_path,
            action="module_saved",
            payload={"module": module.model_dump(mode="json"), "existed": existed},
        )
    else:
        _run_noncritical_save_side_effects(module, kb_path, existed)
        state = {"deferred": False, "action": "module_saved"}
    if maintenance_state is not None:
        maintenance_state.append(state)


def load_module(module_id: str, category: str, kb_path: Path) -> Optional[Module]:
    path = kb_path / category / f"{module_id}.json"
    if not path.exists():
        return None
    return Module.model_validate_json(path.read_text(encoding="utf-8"))


def delete_module(
    module_id: str,
    category: str,
    kb_path: Path,
    defer_noncritical: bool = True,
    maintenance_state: list[dict[str, Any]] | None = None,
) -> bool:
    path = kb_path / category / f"{module_id}.json"
    if not path.exists():
        return False
    path.unlink()
    _remove_index_entry(module_id, category, kb_path)
    _invalidate_module_cache(kb_path)
    invalidate_materialized_views(kb_path)
    if defer_noncritical:
        state = schedule_maintenance_job(
            kb_path,
            action="module_deleted",
            payload={"module_id": module_id, "category": category},
        )
    else:
        _run_noncritical_delete_side_effects(module_id, category, kb_path)
        state = {"deferred": False, "action": "module_deleted"}
    if maintenance_state is not None:
        maintenance_state.append(state)
    return True


def list_modules(kb_path: Path, tenant: TenantContext | None = None) -> List[Module]:
    if not kb_path.exists():
        return []
    fingerprint = _module_set_fingerprint(kb_path)
    modules = _MODULE_CACHE.get(kb_path, fingerprint)
    if modules is None:
        loaded: list[Module] = []
        for json_file in kb_path.rglob("*.json"):
            if json_file.name == "index.json":
                continue
            if any(part.startswith(".") for part in json_file.relative_to(kb_path).parts[:-1]):
                continue
            try:
                loaded.append(Module.model_validate_json(json_file.read_text(encoding="utf-8")))
            except Exception:
                pass
        _MODULE_CACHE.put(kb_path, fingerprint, loaded)
        modules = loaded
    return [module for module in modules if module_visible_to_tenant(module, tenant)]


def get_supersession_chain(module_id: str, category: str, kb_path: Path) -> list[str]:
    module = load_module(module_id, category, kb_path)
    if module is None:
        return []

    chain: list[str] = []
    pending = list(module.metadata.supersedes)
    seen: set[str] = set()
    while pending:
        ref = pending.pop(0)
        if ref in seen:
            continue
        seen.add(ref)
        chain.append(ref)
        if "/" not in ref:
            continue
        ref_category, ref_id = ref.split("/", 1)
        ref_module = load_module(ref_id, ref_category, kb_path)
        if ref_module is not None:
            pending.extend(ref_module.metadata.supersedes)
    return chain


def mark_source_documents_changed(source_versions: dict[str, str], kb_path: Path) -> list[str]:
    affected: list[str] = []
    for module in list_modules(kb_path):
        if module.metadata.stale_due_to_source_change:
            continue
        for ref in module.metadata.source_documents:
            current_version = source_versions.get(ref.external_id)
            if current_version and current_version != ref.version:
                module.metadata.stale_due_to_source_change = True
                module.updated_at = datetime.now(timezone.utc)
                save_module(module, kb_path)
                affected.append(f"{module.category}/{module.id}")
                break
    if affected:
        rebuild_index(kb_path)
    return affected


class SearchResult(NamedTuple):
    module: Module
    source: str  # "direct", "related", or "policy"
    reasons: list[str]


def _merge_hybrid_results(
    lexical_results: list[SearchResult],
    vector_hits: list[tuple[str, float]],
    kb_path: Path,
) -> list[SearchResult]:
    merged: list[SearchResult] = list(lexical_results)
    index_by_key = {
        f"{item.module.category}/{item.module.id}": idx for idx, item in enumerate(merged)
    }

    for module_key, score in vector_hits:
        if "/" not in module_key:
            continue
        reason = f"vector_support:{round(score, 3)}"
        if module_key in index_by_key:
            idx = index_by_key[module_key]
            current = merged[idx]
            if reason not in current.reasons:
                merged[idx] = SearchResult(
                    current.module,
                    current.source,
                    current.reasons + [reason],
                )
            continue
        category, module_id = module_key.split("/", 1)
        module = load_module(module_id, category, kb_path)
        if module is None:
            continue
        index_by_key[module_key] = len(merged)
        merged.append(SearchResult(module, "vector_fallback", [reason]))
    return merged


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


def _bm25_scores_for_documents(query: str, documents: list[Mapping[str, Any]]) -> Dict[str, float]:
    """Compute BM25 scores directly from search documents."""
    if not documents or not query.strip():
        return {}

    query_stems: List[str] = []
    for w in _WORD_RE.findall(query.lower()):
        query_stems.extend(_stem(w).split())
    if not query_stems:
        return {}

    doc_tfs: List[Dict[str, int]] = []
    doc_keys: List[str] = []
    df: Dict[str, int] = {}
    doc_lengths: List[int] = []

    for document in documents:
        stored_stems = document.get("stems", [])
        if stored_stems:
            stemmed = [str(stem) for stem in stored_stems]
        else:
            text = _document_full_text(document)
            words = [w.lower() for w in _WORD_RE.findall(text)]
            stemmed = []
            for w in words:
                stemmed.extend(_stem(w).split())

        tf: Dict[str, int] = {}
        for s in stemmed:
            tf[s] = tf.get(s, 0) + 1

        doc_tfs.append(tf)
        doc_keys.append(_document_key(document))
        doc_lengths.append(len(stemmed))

        for term in set(stemmed):
            df[term] = df.get(term, 0) + 1

    total_len = sum(doc_lengths)
    if total_len == 0:
        return {}

    avgdl = total_len / len(documents)
    scores: Dict[str, float] = {}
    for i, tf_map in enumerate(doc_tfs):
        score = 0.0
        dl = doc_lengths[i]
        for term in query_stems:
            df_t = df.get(term, 0)
            if df_t == 0:
                continue
            idf = math.log((len(documents) - df_t + 0.5) / (df_t + 0.5) + 1)
            tf = tf_map.get(term, 0)
            if tf == 0:
                continue
            score += (
                idf
                * (tf * (_BM25_K1 + 1))
                / (tf + _BM25_K1 * (1 - _BM25_B + _BM25_B * dl / avgdl))
            )
        scores[doc_keys[i]] = score
    return scores


def search_modules(
    query: str,
    kb_path: Path,
    category: str | None = None,
    limit: int = 15,
    boost_ids: List[str] | None = None,
    include_archived: bool = False,
    agent_id: str | None = None,
    task_type: str | None = None,
    risk_level: str | None = None,
    enable_vector_fallback: bool = False,
    tenant: TenantContext | None = None,
) -> List[SearchResult]:
    candidate_set: set[str] | None = None
    use_projection = False
    projection_documents: dict[str, dict[str, Any]] = {}
    raw_query_terms = _WORD_RE.findall(query.lower())
    if raw_query_terms and all(len(term) >= 5 or _CJK_RE.search(term) for term in raw_query_terms):
        try:
            from knowledge_manager.search_projection import (
                build_search_projection,
                load_search_projection_readonly,
                projection_document_complete,
                query_search_projection,
            )

            candidate_keys = query_search_projection(kb_path, query)
            if candidate_keys:
                candidate_cap = max(limit * 20, 200)
                candidate_set = set(candidate_keys[:candidate_cap])
                projection_payload = load_search_projection_readonly(kb_path)
                if projection_payload is None:
                    projection_payload = build_search_projection(kb_path)
                projection_documents = projection_payload.get("documents", {})
                if any(
                    (document := projection_documents.get(key)) is None or not projection_document_complete(document)
                    for key in candidate_set
                ):
                    projection_payload = build_search_projection(kb_path)
                    projection_documents = projection_payload.get("documents", {})
                use_projection = bool(projection_documents)
        except Exception:
            candidate_set = None
            projection_documents = {}

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

    def _document_field_stems(document: Mapping[str, Any]) -> dict[str, set[str]]:
        stored = document.get("field_stems", {})
        computed = {
            "title": _field_stems(str(document.get("title", ""))),
            "tag": {s for tag in document.get("tags", []) for s in _stem(str(tag)).split()},
            "summary": _field_stems(str(document.get("summary", ""))),
            "overview": _field_stems(str(document.get("overview", ""))),
            "details": _field_stems(str(document.get("details", ""))),
            "examples": _field_stems(str(document.get("examples", ""))),
            "caveats": _field_stems(str(document.get("caveats", ""))),
        }
        for field_name, values in stored.items():
            computed[field_name] = set(values)
        return computed

    candidate_items: list[tuple[str, dict[str, Any], dict[str, set[str]]]] = []
    if use_projection and candidate_set is not None:
        for key in sorted(candidate_set):
            document = projection_documents.get(key)
            if document is None or not _projection_doc_visible_to_tenant(document, tenant):
                continue
            candidate_items.append((key, document, _document_field_stems(document)))
    else:
        all_modules = list_modules(kb_path, tenant=tenant)
        if candidate_set is not None:
            all_modules = [
                module
                for module in all_modules
                if f"{module.category}/{module.id}" in candidate_set
            ]
        for module in all_modules:
            document = _search_document_from_module(module)
            candidate_items.append((_document_key(document), document, _document_field_stems(document)))
    cfg = _load_config_safe(kb_path)
    user_synonyms: Dict[str, List[str]] = cfg.synonyms if cfg else {}
    routing_policy: RoutingPolicyConfig = cfg.routing_policy if cfg else RoutingPolicyConfig()
    effective_policy = merge_agent_routing_policy(
        routing_policy,
        routing_policy.agent_overrides.get(agent_id) if agent_id else None,
    )
    allowed_statuses: set[str] | None = None
    if task_type:
        task_allowed = effective_policy.task_type_allowed_statuses.get(task_type, [])
        if task_allowed:
            allowed_statuses = set(task_allowed)
    if risk_level:
        risk_allowed = effective_policy.risk_level_allowed_statuses.get(risk_level, [])
        if risk_allowed:
            risk_allowed_set = set(risk_allowed)
            allowed_statuses = risk_allowed_set if allowed_statuses is None else allowed_statuses & risk_allowed_set

    def _document_allowed_by_policy(document: Mapping[str, Any]) -> bool:
        status = str(document.get("status", "published"))
        if not include_archived and status == "archived":
            return False
        if allowed_statuses is not None and status not in allowed_statuses:
            return False
        if effective_policy.suppress_stale_sources and document.get("stale_due_to_source_change"):
            return False
        if effective_policy.suppress_expired:
            expires_at = document.get("expires_at")
            if expires_at:
                try:
                    expires = datetime.fromisoformat(str(expires_at))
                    if expires.tzinfo is None:
                        expires = expires.replace(tzinfo=timezone.utc)
                    if expires <= datetime.now(timezone.utc):
                        return False
                except ValueError:
                    pass
        return True

    candidate_items = [
        item
        for item in candidate_items
        if _document_allowed_by_policy(item[1])
    ]
    bm25 = _bm25_scores_for_documents(query, [item[1] for item in candidate_items])

    # Build tag synonym map from co-occurring tags across all modules
    tag_synonyms: Dict[str, set[str]] = {}
    for _module_key, document, _field_stem_map in candidate_items:
        tag_words = set()
        for tag in document.get("tags", []):
            tag_words.update(_WORD_RE.findall(str(tag).lower()))
        for tw in tag_words:
            if tw not in tag_synonyms:
                tag_synonyms[tw] = set()
            tag_synonyms[tw].update(tag_words - {tw})

    # Load user-configured synonyms from config
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
    for module_key, document, _field_stem_map in candidate_items:
        related_modules = list(document.get("related_modules", []))
        if related_modules:
            graph[module_key] = related_modules

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

    scored: List[tuple[float, float, int, str, dict[str, Any], str, list[str]]] = []
    prioritized_categories = list(effective_policy.category_priorities.get(intent, []))
    if task_type:
        for category_name in reversed(effective_policy.task_type_category_priorities.get(task_type, [])):
            if category_name in prioritized_categories:
                prioritized_categories.remove(category_name)
            prioritized_categories.insert(0, category_name)
    category_priority_bonus = {
        category_name: max(0, len(prioritized_categories) - index) * 4
        for index, category_name in enumerate(prioritized_categories)
    }
    for module_key, document, field_stems in candidate_items:
        fields: dict[str, str | list[str]] = {
            "title": str(document.get("title", "")),
            "tag": list(document.get("tags", [])),
            "summary": str(document.get("summary", "")),
            "overview": str(document.get("overview", "")),
            "details": str(document.get("details", "")),
            "examples": str(document.get("examples", "")),
            "caveats": str(document.get("caveats", "")),
        }
        score = 0
        best_quality = 0
        reasons: list[str] = []

        for term, word_pattern, partial_pattern, weight in patterns:
            term_score, quality = score_term(term, fields, field_stems, word_pattern, partial_pattern, effective_weights)
            score += int(term_score * weight)
            best_quality = max(best_quality, quality)

        category_name = str(document.get("category", ""))
        if score > 0 and category_name in category_priority_bonus:
            score += category_priority_bonus[category_name]
            reasons.append(f"category_priority:{category_name}")
        if score > 0:
            reasons.append(f"intent:{intent}")
        if score > 0 and task_type and category_name in effective_policy.task_type_category_priorities.get(task_type, []):
            reasons.append(f"task_type:{task_type}")
        if score > 0 and agent_id:
            reasons.append(f"agent:{agent_id}")

        if score > 0:
            scored.append((bm25.get(module_key, 0.0), score, best_quality, module_key, document, "direct", reasons))

    # 1-hop graph expansion: add related modules with discounted scores
    direct_matches = list(scored)
    direct_keys = {module_key for _, _, _, module_key, _, _, _ in direct_matches}
    for _bm25_score, heur_score, _, module_key, trigger_document, _, trigger_reasons in direct_matches:
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
            neighbor_key = f"{n_cat}/{n_id}"
            if neighbor_key in direct_keys:
                continue
            neighbor_document = projection_documents.get(neighbor_key) if use_projection else None
            if neighbor_document is not None:
                expanded_document = neighbor_document
            else:
                neighbor = load_module(n_id, n_cat, kb_path)
                if neighbor is None:
                    continue
                expanded_document = _search_document_from_module(neighbor)
            if not _projection_doc_visible_to_tenant(expanded_document, tenant):
                continue
            expanded_heuristic = heur_score * _EXPANSION_DISCOUNT * edge_weight
            expanded_bm25 = bm25.get(n_id, 0.0)
            scored.append(
                (
                    expanded_bm25,
                    expanded_heuristic,
                    0,
                    neighbor_key,
                    expanded_document,
                    "related",
                    trigger_reasons + [f"graph_related:{module_key}"],
                )
            )
            direct_keys.add(neighbor_key)

    # Filter by category if specified
    if category is not None:
        scored = [
            (b, s, q, module_key, document, src, reasons)
            for b, s, q, module_key, document, src, reasons in scored
            if document.get("category") == category
        ]

    # Compute Bayesian priors from historical telemetry (if available)
    priors = compute_bayesian_priors(kb_path)
    query_stems = []
    for t in terms:
        query_stems.extend(_stem(t).split())

    def _bayesian_bonus(module_key: str) -> float:
        """Average P(module_id | query_term) across all query terms."""
        total = 0.0
        count = 0
        for term in query_stems:
            if term in priors and module_key in priors[term]:
                total += priors[term][module_key]
                count += 1
        return total / count if count > 0 else 0.0

    # Session boost: 1.2x multiplier for recently loaded modules in this session
    boost_set = set(boost_ids) if boost_ids else set()

    def _session_boost(module_key: str, module_id: str, heur_score: float) -> float:
        return heur_score * 1.2 if module_key in boost_set or module_id in boost_set else heur_score

    def _effective_confidence(document: Mapping[str, Any]) -> float:
        """Deprecated modules get confidence penalty (treated as low)."""
        conf = str(document.get("confidence", "medium"))
        if document.get("status") == "deprecated":
            conf = "low"
        return _CONFIDENCE_WEIGHT.get(conf, 0.85)

    # Primary: confidence-weighted heuristic score (with session boost).
    # Secondary: match quality. Tertiary: Bayesian prior. Fourth: BM25.
    scored.sort(
        key=lambda item: (
            _session_boost(item[3], str(item[4].get("module_id", "")), item[1]) * _effective_confidence(item[4]),
            item[2],
            _bayesian_bonus(item[3]),
            item[0],
        ),
        reverse=True,
    )
    scored_results = scored[:limit]
    results = [
        SearchResult(_module_from_search_document(document), source, reasons)
        for _, _, _, _, document, source, reasons in scored_results
    ]

    if enable_vector_fallback:
        from knowledge_manager.vector_index import VectorIndex

        vector_index = VectorIndex(kb_path)
        vector_hits = vector_index.search(query, top_k=limit)
        results = _merge_hybrid_results(results, vector_hits, kb_path)

    seen_keys = {f"{result.module.category}/{result.module.id}" for result in results}
    primary_categories = [result.module.category for result in results if result.source == "direct"]
    policy_decision = evaluate_module_policy(
        results[0].module if results else None,
        effective_policy,
        primary_categories=primary_categories,
        risk_level=risk_level,
    )
    for companion_key in policy_decision.mandatory_companions:
        if companion_key in seen_keys:
            continue
        parts = companion_key.split("/", 1)
        if len(parts) != 2:
            continue
        comp_category, comp_id = parts
        companion_document = projection_documents.get(companion_key) if use_projection else None
        if companion_document is not None:
            companion = _module_from_search_document(companion_document)
        else:
            companion = load_module(comp_id, comp_category, kb_path)
        if companion is None:
            continue
        companion_decision = evaluate_module_policy(
            companion,
            effective_policy,
            allowed_statuses=allowed_statuses,
        )
        if not companion_decision.allowed and companion_key not in effective_policy.risk_level_companions.get(risk_level or "", []):
            continue
        companion_reasons = [f"mandatory_companion:{companion_key}"]
        if risk_level and companion_key in effective_policy.risk_level_companions.get(risk_level, []):
            companion_reasons.append(f"risk_level:{risk_level}")
        for primary_category in primary_categories:
            if companion_key in effective_policy.mandatory_companions.get(primary_category, []):
                companion_reasons.append(f"primary_category:{primary_category}")
        companion_reasons.extend(companion_decision.reasons)
        results.append(SearchResult(companion, "policy", companion_reasons))
        seen_keys.add(companion_key)

    if results:
        result_ids = [f"{r.module.category}/{r.module.id}" for r in results[:20]]
        record_search_event(query, result_ids, kb_path)
        return results[:limit]

    record_search_event(query, [], kb_path)
    return []


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
    invalidate_materialized_views(kb_path)


def load_index(kb_path: Path) -> Optional[Index]:
    path = kb_path / "index.json"
    if not path.exists():
        return None
    return Index.model_validate_json(path.read_text(encoding="utf-8"))


def rebuild_index(kb_path: Path) -> Index:
    _invalidate_module_cache(kb_path)
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
    try:
        from knowledge_manager.lexical_index import build_lexical_index

        build_lexical_index(kb_path)
    except Exception:
        pass
    invalidate_materialized_views(kb_path)
    return index


def save_to_staging(module: Module, staging_path: Path) -> None:
    _atomic_write(staging_path / f"{module.id}.json", module.model_dump_json(indent=2))
    invalidate_materialized_views(staging_path.parent)


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
    invalidate_materialized_views(staging_path.parent)


def load_staging_meta(module_id: str, staging_path: Path) -> StagingMeta | None:
    path = staging_path / f"{module_id}.meta.json"
    if not path.exists():
        return None
    return StagingMeta.model_validate_json(path.read_text(encoding="utf-8"))


def delete_staging_meta(module_id: str, staging_path: Path) -> None:
    path = staging_path / f"{module_id}.meta.json"
    if path.exists():
        path.unlink()
        invalidate_materialized_views(staging_path.parent)


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
    _invalidate_module_cache(kb_path)
    (staging_path / f"{module_id}.json").unlink()
    invalidate_materialized_views(kb_path)


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
    events_file = tdir / "search_events.jsonl"
    with open(events_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    cache_key = str(events_file)
    _SEARCH_EVENTS_CACHE.pop(cache_key, None)


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
    events_file = tdir / "search_events.jsonl"
    with open(events_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    cache_key = str(events_file)
    _SEARCH_EVENTS_CACHE.pop(cache_key, None)
    _PRIORS_CACHE.pop(cache_key, None)
    invalidate_materialized_views(kb_path, ["health", "recommendations"])


def _load_search_events_payload(kb_path: Path) -> list[dict[str, Any]]:
    tdir = _telemetry_dir(kb_path)
    events_file = tdir / "search_events.jsonl"
    if not events_file.exists():
        return []
    stat = events_file.stat()
    cache_key = str(events_file)
    cached = _SEARCH_EVENTS_CACHE.get(cache_key)
    if cached is not None:
        cached_mtime_ns, cached_size, cached_events = cached
        if cached_mtime_ns == int(stat.st_mtime_ns) and cached_size == int(stat.st_size):
            return cached_events
    events: list[dict[str, Any]] = []
    for line in events_file.read_text(encoding="utf-8").strip().split("\n"):
        if line:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    _SEARCH_EVENTS_CACHE[cache_key] = (int(stat.st_mtime_ns), int(stat.st_size), events)
    return events


def load_search_events_readonly(kb_path: Path) -> list[dict[str, Any]]:
    """Load telemetry events using a parsed in-process cache when the file is unchanged."""
    return _load_search_events_payload(kb_path)


def load_search_events(kb_path: Path) -> List[dict]:
    """Load all telemetry events from disk."""
    return copy.deepcopy(load_search_events_readonly(kb_path))


def save_rank_model(priors: Dict[str, Dict[str, float]], event_count: int, kb_path: Path) -> None:
    """Persist computed Bayesian priors to disk for fast reload."""
    tdir = _telemetry_dir(kb_path)
    tdir.mkdir(parents=True, exist_ok=True)
    events = load_search_events_readonly(kb_path)
    load_events = [event for event in events if event.get("type") == "load"]
    model = {
        "event_count": event_count,
        "load_event_count": len(load_events),
        "latest_load_timestamp": load_events[-1]["timestamp"] if load_events else "",
        "smoothing": _BAYESIAN_SMOOTHING,
        "priors": priors,
    }
    with open(tdir / "rank_model.json", "w", encoding="utf-8") as f:
        json.dump(model, f, indent=2)


def load_rank_model(
    kb_path: Path,
    expected_event_count: int,
    *,
    expected_load_event_count: int | None = None,
    expected_latest_load_timestamp: str | None = None,
) -> Dict[str, Dict[str, float]] | None:
    """Load cached Bayesian priors if event count matches (i.e., cache is fresh)."""
    model_file = _telemetry_dir(kb_path) / "rank_model.json"
    if not model_file.exists():
        return None
    try:
        model = json.loads(model_file.read_text(encoding="utf-8"))
        if expected_load_event_count is not None:
            if model.get("load_event_count", model.get("event_count")) != expected_load_event_count:
                return None
            if (model.get("latest_load_timestamp", "") or "") != (expected_latest_load_timestamp or ""):
                return None
        else:
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
    events_file = _telemetry_dir(kb_path) / "search_events.jsonl"
    events = load_search_events_readonly(kb_path)
    if not events:
        return {}
    load_events = [event for event in events if event.get("type") == "load"]
    load_fingerprint = (
        len(load_events),
        str(load_events[-1].get("timestamp", "")) if load_events else "",
    )
    cache_key = str(events_file)
    cached = _PRIORS_CACHE.get(cache_key)
    if cached is not None:
        cached_load_fingerprint, cached_priors = cached
        if cached_load_fingerprint == load_fingerprint:
            return cached_priors

    cached = load_rank_model(
        kb_path,
        len(events),
        expected_load_event_count=load_fingerprint[0],
        expected_latest_load_timestamp=load_fingerprint[1],
    )
    if cached is not None:
        _PRIORS_CACHE[cache_key] = (load_fingerprint, cached)
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
    _PRIORS_CACHE[cache_key] = (load_fingerprint, priors)
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


def _load_event_stats(kb_path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    cutoff_30 = now - timedelta(days=30)
    stats: dict[tuple[str, str], dict[str, Any]] = {}
    for evt in load_search_events_readonly(kb_path):
        if evt.get("type") != "load":
            continue
        module_id = evt.get("module_id")
        category = evt.get("category")
        if not module_id or not category:
            continue
        try:
            ts = datetime.fromisoformat(evt["timestamp"])
        except (ValueError, KeyError):
            continue
        key = (str(module_id), str(category))
        current = stats.setdefault(key, {"latest_load": None, "load_count_30d": 0})
        if ts >= cutoff_30:
            current["load_count_30d"] += 1
        latest = current["latest_load"]
        if latest is None or ts > latest:
            current["latest_load"] = ts
    return stats


def _usage_score(
    module_id: str,
    category: str,
    kb_path: Path,
    load_stats: Mapping[tuple[str, str], Mapping[str, Any]] | None = None,
) -> float:
    """Score module usage based on recent load events (0-100)."""
    from datetime import timedelta

    if load_stats is None:
        load_stats = _load_event_stats(kb_path)
    record = load_stats.get((module_id, category))
    if record is None:
        return 0.0
    latest_load = record.get("latest_load")
    if latest_load is None:
        return 0.0

    now = datetime.now(timezone.utc)
    cutoff_30 = now - timedelta(days=30)
    cutoff_60 = now - timedelta(days=60)
    cutoff_90 = now - timedelta(days=90)
    if latest_load >= cutoff_30:
        return 100.0
    if latest_load >= cutoff_60:
        return 70.0
    if latest_load >= cutoff_90:
        return 40.0
    return 0.0


def _load_count_30d(
    module_id: str,
    category: str,
    kb_path: Path,
    load_stats: Mapping[tuple[str, str], Mapping[str, Any]] | None = None,
) -> int:
    """Count load events for a module in the last 30 days."""
    if load_stats is None:
        load_stats = _load_event_stats(kb_path)
    record = load_stats.get((module_id, category))
    if record is None:
        return 0
    return int(record.get("load_count_30d", 0))


def _last_load_time(
    module_id: str,
    category: str,
    kb_path: Path,
    load_stats: Mapping[tuple[str, str], Mapping[str, Any]] | None = None,
) -> datetime | None:
    """Get the most recent load time for a module."""
    if load_stats is None:
        load_stats = _load_event_stats(kb_path)
    record = load_stats.get((module_id, category))
    if record is None:
        return None
    latest = record.get("latest_load")
    return latest if isinstance(latest, datetime) else None


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


def compute_module_health(
    module: Any,
    kb_path: Path,
    load_stats: Mapping[tuple[str, str], Mapping[str, Any]] | None = None,
) -> Any:
    """Compute health score for a single module."""
    from knowledge_manager.schemas import HealthScore, ModuleHealth

    if load_stats is None:
        load_stats = _load_event_stats(kb_path)
    freshness = _freshness_score(module)
    usage = _usage_score(module.id, module.category, kb_path, load_stats=load_stats)
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
        last_load=_last_load_time(module.id, module.category, kb_path, load_stats=load_stats),
        load_count_30d=_load_count_30d(module.id, module.category, kb_path, load_stats=load_stats),
        days_since_update=days_since_update,
    )


def _generate_health_report_uncached(kb_path: Path) -> Any:
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


def generate_health_report(kb_path: Path) -> Any:
    from knowledge_manager.schemas import KBHealthReport

    cached = load_fresh_materialized_view(kb_path, "health")
    if cached is not None:
        return KBHealthReport.model_validate(cached)
    report = _generate_health_report_uncached(kb_path)
    return store_materialized_view(kb_path, "health", report)


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


def _generate_recommendations_uncached(kb_path: Path) -> Any:
    """Generate actionable recommendations for knowledge base improvement."""
    from knowledge_manager.schemas import (
        RecommendationReport, Recommendation, RecommendationType,
    )

    index = load_index(kb_path)
    if index is None:
        return RecommendationReport()

    try:
        from knowledge_manager.recommendation_index import (
            build_recommendation_index,
            iter_recommendation_link_candidates,
            load_recommendation_index,
        )

        recommendation_payload = load_recommendation_index(kb_path)
        if recommendation_payload is None:
            recommendation_payload = build_recommendation_index(kb_path)
    except Exception:
        recommendation_payload = None

    modules_by_key: dict[str, Module] = {}
    if recommendation_payload is not None:
        for module_key, payload in recommendation_payload.get("modules", {}).items():
            try:
                modules_by_key[module_key] = Module.model_validate(payload["module"])
            except Exception:
                continue
    if not modules_by_key:
        for cat_name, cat in index.categories.items():
            for summary in cat.modules:
                module = load_module(summary.id, cat_name, kb_path)
                if module is not None:
                    modules_by_key[f"{cat_name}/{summary.id}"] = module

    archive_candidates = []
    enrichment_needed = []
    suggested_links = []
    review_reminders = []

    now = datetime.now(timezone.utc)
    load_stats = _load_event_stats(kb_path)

    for module_key, mod in modules_by_key.items():
        cat_name, _module_id = module_key.split("/", 1)
        h = compute_module_health(mod, kb_path, load_stats=load_stats)
        status = mod.metadata.status

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
                module_id=mod.id, category=cat_name, title=mod.title,
                score=archive_score,
                reason=", ".join(archive_reasons),
                detail={"health_score": h.score.overall, "issues": h.issues},
            ))

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
                    module_id=mod.id, category=cat_name, title=mod.title,
                    score=round((80 - h.score.completeness) / 80, 2),
                    reason=f"Missing: {', '.join(missing)}",
                    detail={"missing_fields": missing},
                ))

        if mod.metadata.review_interval_days and h.days_since_update > mod.metadata.review_interval_days:
            review_reminders.append(Recommendation(
                type=RecommendationType.REVIEW,
                module_id=mod.id, category=cat_name, title=mod.title,
                score=0.8,
                reason=f"review_interval ({mod.metadata.review_interval_days}d) expired",
                detail={"days_overdue": h.days_since_update - mod.metadata.review_interval_days},
            ))

    if recommendation_payload is not None:
        link_candidates = [
            (item["first"], item["second"], item["shared_tags"])
            for item in recommendation_payload.get("link_candidates", [])
            if item.get("first") and item.get("second") and item.get("shared_tags")
        ]
        if not link_candidates:
            link_candidates = iter_recommendation_link_candidates(recommendation_payload)
    else:
        module_tags = {
            module_key: set(module.metadata.tags) for module_key, module in modules_by_key.items()
        }
        existing_links: set[tuple[str, str]] = set()
        for src, targets in index.graph.items():
            for target in targets:
                existing_links.add((src, target))
                existing_links.add((target, src))
        link_candidates = []
        for k1, tags1 in module_tags.items():
            for k2, tags2 in module_tags.items():
                if k1 >= k2:
                    continue
                if (k1, k2) in existing_links:
                    continue
                shared = sorted(tags1 & tags2)
                if shared:
                    link_candidates.append((k1, k2, shared))

    for k1, k2, shared in link_candidates:
        if len(shared) >= 2:
            suggested_links.append(Recommendation(
                type=RecommendationType.LINK,
                module_id=k1, category="", title=f"{k1} ↔ {k2}",
                score=min(1.0, len(shared) / 5.0),
                reason=f"Shared tags: {', '.join(shared[:3])}",
                detail={"module_a": k1, "module_b": k2, "shared_tags": shared},
            ))

    suggested_links.sort(key=lambda r: -r.score)

    return RecommendationReport(
        archive_candidates=sorted(archive_candidates, key=lambda r: -r.score)[:10],
        enrichment_needed=sorted(enrichment_needed, key=lambda r: -r.score)[:10],
        suggested_links=suggested_links[:10],
        review_reminders=sorted(review_reminders, key=lambda r: -r.score)[:5],
    )


def generate_recommendations(kb_path: Path) -> Any:
    from knowledge_manager.schemas import RecommendationReport

    cached = load_fresh_materialized_view(kb_path, "recommendations")
    if cached is not None:
        return RecommendationReport.model_validate(cached)
    report = _generate_recommendations_uncached(kb_path)
    return store_materialized_view(kb_path, "recommendations", report)


def _generate_ops_report_uncached(kb_path: Path, staging_meta: list[Any] | None = None) -> Any:
    """Generate an operator-focused report across sources, lifecycle, and routing suppression."""
    from knowledge_manager.schemas import (
        LifecycleBacklog,
        OpsReport,
        PolicySuppressedModule,
        SourceBacklogEntry,
    )
    from knowledge_manager.source_ingestion import load_source_registry

    modules = list_modules(kb_path)
    registry = load_source_registry(kb_path)
    if staging_meta is None:
        staging_meta = list_staging_meta(kb_path / ".staging")
    cfg = _load_config_safe(kb_path)
    routing_policy = cfg.routing_policy if cfg else RoutingPolicyConfig()

    source_backlog: list[SourceBacklogEntry] = []
    for source_id, definition in registry.sources.items():
        stale_count = 0
        for module in modules:
            if module.metadata.stale_due_to_source_change and any(
                doc.source_id == source_id for doc in module.metadata.source_documents
            ):
                stale_count += 1
        source_backlog.append(
            SourceBacklogEntry(
                source_id=source_id,
                source_type=definition.type,
                last_synced_at=definition.sync.last_synced_at,
                tracked_pages=len(definition.sync.page_versions),
                stale_module_count=stale_count,
                sync_error=definition.sync.last_error,
            )
        )

    status_counts: dict[str, int] = {}
    for module in modules:
        status_counts[module.metadata.status] = status_counts.get(module.metadata.status, 0) + 1

    staging_status_counts: dict[str, int] = {}
    for meta in staging_meta:
        staging_status_counts[meta.status] = staging_status_counts.get(meta.status, 0) + 1

    suppressed: list[PolicySuppressedModule] = []
    risk_allowed = set(routing_policy.risk_level_allowed_statuses.get("high", [])) or None
    for module in modules:
        reasons = evaluate_module_policy(
            module,
            routing_policy,
            allowed_statuses=risk_allowed,
        ).reasons
        if reasons:
            suppressed.append(
                PolicySuppressedModule(
                    module_id=module.id,
                    category=module.category,
                    title=module.title,
                    reasons=reasons,
                )
            )

    return OpsReport(
        source_backlog=sorted(source_backlog, key=lambda item: (-item.stale_module_count, item.source_id)),
        lifecycle_backlog=LifecycleBacklog(
            status_counts=status_counts,
            staging_status_counts=staging_status_counts,
        ),
        policy_suppressed_modules=sorted(
            suppressed, key=lambda item: (item.category, item.module_id)
        ),
    )


def generate_ops_report(kb_path: Path, staging_meta: list[Any] | None = None) -> Any:
    from knowledge_manager.schemas import OpsReport

    cached = load_fresh_materialized_view(kb_path, "ops")
    if cached is not None:
        return OpsReport.model_validate(cached)
    report = _generate_ops_report_uncached(kb_path, staging_meta=staging_meta)
    return store_materialized_view(kb_path, "ops", report)


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
