"""Executor de thread pool compartilhado para serviços de aplicação."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

_executor: ThreadPoolExecutor | None = None


def get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None or getattr(_executor, "_shutdown", False):
        _executor = ThreadPoolExecutor(max_workers=20)
    return _executor
