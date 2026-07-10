"""Circuit breaker — evita martelar fontes que falham repetidamente."""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

FAIL_THRESHOLD = 3
COOLDOWN_SECONDS = 120.0
HALF_OPEN_TIMEOUT = 8.0


class CircuitBreaker:
    def __init__(
        self, fail_threshold: int = FAIL_THRESHOLD, cooldown_seconds: float = COOLDOWN_SECONDS
    ):
        self._fail_threshold = fail_threshold
        self._cooldown = cooldown_seconds
        self._lock = threading.RLock()
        self._failures: dict[str, int] = {}
        self._open_until: dict[str, float] = {}

    def allow(self, identifier: str) -> bool:
        with self._lock:
            return self._allow_locked(identifier)

    def _allow_locked(self, identifier: str) -> bool:
        until = self._open_until.get(identifier, 0)
        if until and time.monotonic() < until:
            return False
        if until and time.monotonic() >= until:
            self._open_until.pop(identifier, None)
            self._failures.pop(identifier, None)
        return True

    def record_success(self, identifier: str) -> None:
        with self._lock:
            self._failures.pop(identifier, None)
            self._open_until.pop(identifier, None)

    def record_failure(self, identifier: str) -> None:
        with self._lock:
            count = self._failures.get(identifier, 0) + 1
            self._failures[identifier] = count
            if count >= self._fail_threshold:
                self._open_until[identifier] = time.monotonic() + self._cooldown
                logger.warning(
                    "Circuit breaker ABERTO para %s (%d falhas, cooldown %.0fs)",
                    identifier,
                    count,
                    self._cooldown,
                )

    def is_open(self, identifier: str) -> bool:
        with self._lock:
            return not self._allow_locked(identifier)

    def state(self, identifier: str) -> str:
        with self._lock:
            if not self._allow_locked(identifier):
                remaining = max(0, self._open_until.get(identifier, 0) - time.monotonic())
                return f"open ({remaining:.0f}s)"
            if self._failures.get(identifier, 0) > 0:
                return f"degraded ({self._failures[identifier]}/{self._fail_threshold})"
            return "closed"

    def reset(self, identifier: str | None = None) -> None:
        with self._lock:
            if identifier:
                self._failures.pop(identifier, None)
                self._open_until.pop(identifier, None)
            else:
                self._failures.clear()
                self._open_until.clear()
