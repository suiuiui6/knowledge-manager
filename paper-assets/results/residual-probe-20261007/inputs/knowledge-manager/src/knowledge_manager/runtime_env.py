from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class RuntimeEnvError(ValueError):
    """Raised when deployment-owned runtime environment variables are invalid."""


VALID_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}


@dataclass(frozen=True)
class RuntimeEnvSettings:
    kb_path: Path
    ui_host: str
    ui_port: int
    log_level: str


def _parse_ui_port(raw_value: str) -> int:
    try:
        port = int(raw_value)
    except ValueError as exc:
        raise RuntimeEnvError(f"KM_UI_PORT must be an integer between 1 and 65535; got {raw_value!r}") from exc
    if not 1 <= port <= 65535:
        raise RuntimeEnvError(f"KM_UI_PORT must be an integer between 1 and 65535; got {raw_value!r}")
    return port


def _parse_log_level(raw_value: str) -> str:
    level = raw_value.upper()
    if level not in VALID_LOG_LEVELS:
        allowed = ", ".join(sorted(VALID_LOG_LEVELS))
        raise RuntimeEnvError(f"KM_LOG_LEVEL must be one of {allowed}; got {raw_value!r}")
    return level


def load_runtime_env_settings() -> RuntimeEnvSettings:
    kb_path = Path(os.environ.get("KM_KB_PATH", Path.cwd()))
    ui_host = os.environ.get("KM_UI_HOST", "127.0.0.1")
    ui_port = _parse_ui_port(os.environ.get("KM_UI_PORT", "8420"))
    log_level = _parse_log_level(os.environ.get("KM_LOG_LEVEL", "WARNING"))
    return RuntimeEnvSettings(
        kb_path=kb_path,
        ui_host=ui_host,
        ui_port=ui_port,
        log_level=log_level,
    )
