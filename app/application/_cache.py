"""TTL cache genérico com poda automática."""

from __future__ import annotations

import time


class TTLCache:
    def __init__(self, ttl: float = 600.0, max_size: int = 800) -> None:
        self._ttl = ttl
        self._max_size = max_size
        self._store: dict[str, tuple[float, object]] = {}

    def get(self, key: str):
        entry = self._store.get(key)
        if entry and entry[0] > time.monotonic():
            return entry[1]
        return None

    def set(self, key: str, value: object) -> None:
        self._store[key] = (time.monotonic() + self._ttl, value)
        if len(self._store) > self._max_size:
            self._prune()

    def _prune(self) -> None:
        now = time.monotonic()
        expired = [k for k, (exp, _) in self._store.items() if exp <= now]
        for k in expired:
            del self._store[k]
        if len(self._store) > self._max_size:
            oldest = sorted(self._store.items(), key=lambda kv: kv[1][0])[:200]
            for k, _ in oldest:
                del self._store[k]

    def clear(self) -> None:
        self._store.clear()
