import threading
from collections import OrderedDict
from typing import Optional

from knowledge_manager.schemas import Module


class ModuleCache:
    def __init__(self, max_size: int = 50, enabled: bool = True):
        self._max_size = max_size
        self._enabled = enabled
        self._cache: OrderedDict[str, Module] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def _make_key(module_id: str, namespace: str = "default") -> str:
        return f"{namespace}:{module_id}"

    def get(self, module_id: str, namespace: str = "default") -> Optional[Module]:
        if not self._enabled:
            return None
        key = self._make_key(module_id, namespace)
        with self._lock:
            if key not in self._cache:
                return None
            self._cache.move_to_end(key)
            return self._cache[key]

    def put(self, module: Module, namespace: str = "default") -> None:
        if not self._enabled:
            return
        key = self._make_key(module.id, namespace)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = module
            if len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def invalidate(self, module_id: str, namespace: str = "default") -> None:
        key = self._make_key(module_id, namespace)
        with self._lock:
            self._cache.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._cache)
