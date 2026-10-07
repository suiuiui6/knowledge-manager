from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from knowledge_manager.schemas import Module


@dataclass
class CachedModuleSet:
    fingerprint: tuple[int, int]
    modules: list[Module]


class ModuleCache:
    def __init__(self) -> None:
        self._modules: dict[str, CachedModuleSet] = {}

    def get(self, kb_path: Path, fingerprint: tuple[int, int]) -> list[Module] | None:
        item = self._modules.get(str(kb_path.resolve()))
        if item is not None and item.fingerprint == fingerprint:
            return item.modules
        return None

    def put(self, kb_path: Path, fingerprint: tuple[int, int], modules: list[Module]) -> None:
        self._modules[str(kb_path.resolve())] = CachedModuleSet(
            fingerprint=fingerprint,
            modules=modules,
        )

    def invalidate(self, kb_path: Path) -> None:
        self._modules.pop(str(kb_path.resolve()), None)
