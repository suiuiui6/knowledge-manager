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

    def get(self, module_id: str) -> Optional[Module]:
        if not self._enabled:
            return None
        with self._lock:
            if module_id not in self._cache:
                return None
            self._cache.move_to_end(module_id)
            return self._cache[module_id]

    def put(self, module: Module) -> None:
        if not self._enabled:
            return
        with self._lock:
            if module.id in self._cache:
                self._cache.move_to_end(module.id)
            self._cache[module.id] = module
            if len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def invalidate(self, module_id: str) -> None:
        with self._lock:
            self._cache.pop(module_id, None)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._cache)
