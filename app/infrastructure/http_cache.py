"""Cache HTTP — respostas cacheadas com TTL para evitar requests duplicados."""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from urllib.parse import urlparse

from app.application._cache import TTLCache

logger = logging.getLogger(__name__)

_CACHE_TTL = 300.0
_MAX_ENTRIES = 1200

_cache = TTLCache(ttl=_CACHE_TTL, max_size=_MAX_ENTRIES)
_lock = threading.Lock()


def _cache_key(method: str, url: str) -> str:
    parsed = urlparse(url)
    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    raw = f"{method}:{normalized}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def get_cached(method: str, url: str) -> str | None:
    with _lock:
        return _cache.get(_cache_key(method, url))


def set_cached(method: str, url: str, body: str) -> None:
    with _lock:
        _cache.set(_cache_key(method, url), body)


def clear() -> None:
    with _lock:
        _cache.clear()
