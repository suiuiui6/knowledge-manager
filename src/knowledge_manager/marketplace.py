"""Marketplace client for Phase 4D: install, search, publish knowledge modules."""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from knowledge_manager.schemas import (
    InstallPlan,
    MarketplaceIndex,
    MarketplaceModule,
)


def _load_marketplace_index_from_path(path: Path) -> Optional[MarketplaceIndex]:
    """Load a marketplace index from a local directory (git repo checkout)."""
    index_file = path / "index.json"
    if not index_file.exists():
        return None
    try:
        return MarketplaceIndex.model_validate_json(index_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def fetch_marketplace_index(url: str) -> Optional[MarketplaceIndex]:
    """Fetch the marketplace index from a URL (HTTP) or local path.

    For HTTP URLs, downloads index.json. For local paths (or file://), reads directly.
    """
    if url.startswith("http://") or url.startswith("https://"):
        try:
            import httpx
            resp = httpx.get(f"{url.rstrip('/')}/index.json", timeout=httpx.Timeout(15.0))
            if resp.status_code != 200:
                return None
            return MarketplaceIndex.model_validate_json(resp.text)
        except ImportError:
            return None
        except Exception:
            return None
    else:
        return _load_marketplace_index_from_path(Path(url))


def search_marketplace(query: str, mp_index: MarketplaceIndex) -> List[MarketplaceModule]:
    """Search marketplace modules by keyword (case-insensitive title/summary/tags match)."""
    q = query.lower()
    results = []
    for key, mod in mp_index.modules.items():
        score = 0
        if q in mod.title.lower():
            score += 3
        if q in mod.summary.lower():
            score += 2
        if any(q in tag.lower() for tag in mod.tags):
            score += 1
        if q in mod.id.lower() or q in mod.category.lower():
            score += 1
        if score > 0:
            results.append((score, mod))
    results.sort(key=lambda x: -x[0])
    return [mod for _, mod in results]


def resolve_install_plan(
    module_ref: str,
    mp_index: MarketplaceIndex,
    max_depth: int = 3,
) -> InstallPlan:
    """Resolve a module and its dependencies into an install plan.

    Args:
        module_ref: Full marketplace reference (e.g. "community/auth/oauth2").
        mp_index: The marketplace index.
        max_depth: Maximum recursion depth for dependency resolution.
    """
    if module_ref not in mp_index.modules:
        raise ValueError(f"Module '{module_ref}' not found in marketplace index")

    installed: List[MarketplaceModule] = []
    dep_ids: List[str] = []
    _resolve_recursive(module_ref, mp_index, installed, dep_ids, depth=0, max_depth=max_depth)

    # Determine target category from the module reference (format: "category/id")
    parts = module_ref.split("/")
    target = parts[0] if len(parts) >= 2 else "general"

    return InstallPlan(
        modules=installed,
        target_category=target,
        dependencies_installed=dep_ids,
    )


def _resolve_recursive(
    ref: str,
    mp_index: MarketplaceIndex,
    installed: List[MarketplaceModule],
    dep_ids: List[str],
    depth: int,
    max_depth: int,
) -> None:
    """Recursively resolve dependencies, avoiding cycles."""
    if depth > max_depth or ref in {m.id for m in installed}:
        return

    mod = mp_index.modules.get(ref)
    if mod is None:
        return

    installed.append(mod)

    for dep_ref in mod.dependencies:
        if dep_ref in dep_ids:
            continue
        dep_ids.append(dep_ref)
        _resolve_recursive(dep_ref, mp_index, installed, dep_ids, depth + 1, max_depth)


def install_from_marketplace(
    module_ref: str,
    kb_path: Path,
    mp_url: Optional[str] = None,
) -> InstallPlan:
    """Install a module from the marketplace into the local KB's staging area.

    Args:
        module_ref: Full marketplace reference (e.g. "community/auth/oauth2").
        kb_path: Local knowledge base path.
        mp_url: Marketplace URL. If None, uses the configured marketplace URL.

    Returns the install plan that was executed.
    """
    from knowledge_manager.storage import save_to_staging
    from knowledge_manager.schemas import StagingMeta

    if mp_url is None:
        from knowledge_manager.storage import _load_config_safe
        cfg = _load_config_safe(kb_path)
        mp_url = cfg.marketplace.index_url if cfg else "https://github.com/knowledge-manager/marketplace"

    mp_index = fetch_marketplace_index(mp_url)
    if mp_index is None:
        raise RuntimeError(f"Could not fetch marketplace index from {mp_url}")

    plan = resolve_install_plan(module_ref, mp_index)

    staging = kb_path / ".staging"
    staging.mkdir(parents=True, exist_ok=True)

    for mp_mod in plan.modules:
        # Download module JSON from marketplace
        module_path = f"{mp_mod.category}/{mp_mod.id}.json"
        mp_path = mp_url.rstrip("/")
        if not (mp_path.startswith("http://") or mp_path.startswith("https://")):
            # Local filesystem marketplace
            source = Path(mp_path) / module_path
            if not source.exists():
                raise RuntimeError(f"Module file not found in marketplace: {module_path}")
            module_data = source.read_text(encoding="utf-8")
        else:
            try:
                import httpx
                resp = httpx.get(f"{mp_path}/{module_path}", timeout=httpx.Timeout(15.0))
                if resp.status_code != 200:
                    raise RuntimeError(f"Failed to download {module_path}: HTTP {resp.status_code}")
                module_data = resp.text
            except ImportError:
                raise RuntimeError("httpx is required for HTTP-based marketplace")

        # Write to staging
        from knowledge_manager.schemas import Module
        mod = Module.model_validate_json(module_data)
        save_to_staging(mod, staging)

        # Write staging metadata with marketplace source tracking
        meta = StagingMeta(
            module_id=mod.id,
            submitted_by="marketplace",
        )
        # Store marketplace source info in metadata (packed as JSON in submitted_by for now)
        from knowledge_manager.storage import save_staging_meta
        save_staging_meta(meta, staging)

    return plan


def sanitize_module_text(text: str, patterns: List[str]) -> str:
    """Apply sanitization patterns to a text, replacing sensitive content.

    Each pattern is a regex. Matches are replaced with '<redacted>'.
    """
    for pattern in patterns:
        text = re.sub(pattern, "<redacted>", text)
    return text


def check_publish_gate(module_json: str) -> List[str]:
    """Run pre-flight checks before publishing a module. Returns list of issues."""
    from knowledge_manager.schemas import Module
    issues = []
    try:
        mod = Module.model_validate_json(module_json)
    except Exception as e:
        issues.append(f"Invalid module JSON: {e}")
        return issues

    # Health score check
    if not mod.content.overview or not mod.content.details:
        issues.append("Missing required content fields (overview/details)")
    if mod.metadata.confidence not in ("high", "medium"):
        issues.append(f"Confidence must be 'high' or 'medium', got '{mod.metadata.confidence}'")
    if mod.metadata.status not in ("published",):
        issues.append("Module must be in 'published' status to publish")
    return issues
