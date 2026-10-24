from __future__ import annotations

from knowledge_manager.file_locks import serialized_write

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from knowledge_manager.json_io import atomic_write_text


def _state_path(kb_path: Path) -> Path:
    return kb_path / ".cache" / "derived-index-state.json"


def _default_state() -> dict[str, Any]:
    return {
        "status": "ready",
        "generation": 0,
        "pending_operations": 0,
        "retry_count": 0,
        "updated_at": None,
        "last_success_at": None,
        "last_error_at": None,
        "last_error": None,
    }


def load_derived_index_state(kb_path: Path) -> dict[str, Any]:
    path = _state_path(kb_path)
    if not path.exists():
        return _default_state()
    try:
        import json

        state = json.loads(path.read_text(encoding="utf-8"))
        result = _default_state()
        result.update(state)
        return result
    except Exception:
        state = _default_state()
        state.update(
            {
                "status": "failed",
                "last_error": "derived index state is unreadable",
            }
        )
        return state


def _store(kb_path: Path, state: dict[str, Any]) -> dict[str, Any]:
    import json

    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    path = _state_path(kb_path)
    atomic_write_text(path, json.dumps(state, ensure_ascii=False, indent=2))
    return state


@serialized_write
def mark_derived_indexes_dirty(kb_path: Path) -> dict[str, Any]:
    state = load_derived_index_state(kb_path)
    state["status"] = "dirty"
    state["generation"] = int(state.get("generation", 0)) + 1
    state["pending_operations"] = int(state.get("pending_operations", 0)) + 1
    state["last_error"] = None
    return _store(kb_path, state)


@serialized_write
def mark_derived_indexes_ready(kb_path: Path) -> dict[str, Any]:
    state = load_derived_index_state(kb_path)
    state.update(
        {
            "status": "ready",
            "pending_operations": 0,
            "retry_count": 0,
            "last_success_at": datetime.now(timezone.utc).isoformat(),
            "last_error": None,
        }
    )
    return _store(kb_path, state)


@serialized_write
def mark_derived_indexes_operation_complete(kb_path: Path) -> dict[str, Any]:
    state = load_derived_index_state(kb_path)
    pending = max(0, int(state.get("pending_operations", 0)) - 1)
    state["pending_operations"] = pending
    if pending == 0:
        state["status"] = "ready"
        state["last_success_at"] = datetime.now(timezone.utc).isoformat()
        state["retry_count"] = 0
        state["last_error"] = None
    else:
        state["status"] = "dirty"
    return _store(kb_path, state)


@serialized_write
def mark_derived_indexes_failed(kb_path: Path, error: str) -> dict[str, Any]:
    state = load_derived_index_state(kb_path)
    state["status"] = "failed"
    state["retry_count"] = int(state.get("retry_count", 0)) + 1
    state["last_error_at"] = datetime.now(timezone.utc).isoformat()
    state["last_error"] = error[:1000]
    return _store(kb_path, state)
