"""Executor de thread pool compartilhado para serviços de aplicação."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

_executor = ThreadPoolExecutor(max_workers=20)


def get_executor() -> ThreadPoolExecutor:
    return _executor
