from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
import statistics
import time
from typing import Any, Iterable, Iterator


class HotspotTimer:
    def __init__(self) -> None:
        self._durations_ms: dict[str, list[float]] = defaultdict(list)

    @contextmanager
    def section(self, name: str) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            self.record(name, (time.perf_counter() - started) * 1000.0)

    def record(self, name: str, duration_ms: float) -> None:
        self._durations_ms[name].append(duration_ms)

    def summary(self) -> dict[str, dict[str, float | int]]:
        return {
            name: {
                "count": len(samples),
                "mean_ms": round(statistics.mean(samples), 3),
                "max_ms": round(max(samples), 3),
            }
            for name, samples in self._durations_ms.items()
            if samples
        }


def summarize_maintenance_states(states: Iterable[dict[str, Any]]) -> dict[str, Any]:
    actions: dict[str, int] = {}
    deferred = 0
    total = 0
    for state in states:
        total += 1
        if state.get("deferred"):
            deferred += 1
        action = str(state.get("action") or "unknown")
        actions[action] = actions.get(action, 0) + 1
    return {
        "total": total,
        "deferred": deferred,
        "inline": total - deferred,
        "actions": actions,
    }
