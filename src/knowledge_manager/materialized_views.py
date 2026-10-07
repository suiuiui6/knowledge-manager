from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _views_dir(kb_path: Path) -> Path:
    return kb_path / ".cache" / "views"


def _view_path(kb_path: Path, name: str) -> Path:
    return _views_dir(kb_path) / f"{name}.snapshot.json"


def _state_path(kb_path: Path) -> Path:
    return _views_dir(kb_path) / "state.json"


def _is_snapshot_file(path: Path) -> bool:
    return ".cache" in path.parts and "views" in path.parts and path.name.endswith(".snapshot.json")


def _is_view_state_file(path: Path) -> bool:
    return ".cache" in path.parts and "views" in path.parts and path.name == "state.json"


def _atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(data, encoding="utf-8")
    os.replace(tmp, path)


def _scan_materialized_fingerprint(kb_path: Path) -> tuple[int, int]:
    if not kb_path.exists():
        return (0, 0)

    files: list[Path] = []
    for path in kb_path.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix == ".tmp" or path.name.endswith(".tmp"):
            continue
        if _is_snapshot_file(path):
            continue
        if _is_view_state_file(path):
            continue
        files.append(path)
    total_mtime = sum(int(path.stat().st_mtime_ns) for path in files)
    return (len(files), total_mtime)


def _load_materialized_state(kb_path: Path) -> dict[str, Any] | None:
    path = _state_path(kb_path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _store_materialized_state(kb_path: Path, revision: int) -> dict[str, Any]:
    payload = {
        "revision": revision,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _atomic_write(_state_path(kb_path), json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


def _ensure_materialized_state(kb_path: Path) -> dict[str, Any]:
    state = _load_materialized_state(kb_path)
    if state is not None and isinstance(state.get("revision"), int):
        return state
    return _store_materialized_state(kb_path, 0)


def materialized_fingerprint(kb_path: Path) -> tuple[int, int]:
    state = _load_materialized_state(kb_path)
    if state is not None and isinstance(state.get("revision"), int):
        return (int(state["revision"]), 0)
    return _scan_materialized_fingerprint(kb_path)


def _serialize_payload(payload: Any) -> Any:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(mode="json")
    return payload


def load_materialized_view(kb_path: Path, name: str) -> dict[str, Any] | None:
    path = _view_path(kb_path, name)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_fresh_materialized_view(kb_path: Path, name: str) -> Any | None:
    view = load_materialized_view(kb_path, name)
    if view is None:
        return None
    if tuple(view.get("fingerprint", ())) != materialized_fingerprint(kb_path):
        return None
    return view.get("payload")


def store_materialized_view(kb_path: Path, name: str, payload: Any) -> Any:
    path = _view_path(kb_path, name)
    state = _ensure_materialized_state(kb_path)
    view = {
        "name": name,
        "fingerprint": [int(state.get("revision", 0)), 0],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "payload": _serialize_payload(payload),
    }
    _atomic_write(path, json.dumps(view, ensure_ascii=False, indent=2))
    return payload


def invalidate_materialized_views(kb_path: Path, names: list[str] | None = None) -> None:
    targets = names or ["health", "recommendations", "ops", "admin_dashboard"]
    state = _ensure_materialized_state(kb_path)
    _store_materialized_state(kb_path, int(state.get("revision", 0)) + 1)
    for name in targets:
        path = _view_path(kb_path, name)
        if path.exists():
            path.unlink()
