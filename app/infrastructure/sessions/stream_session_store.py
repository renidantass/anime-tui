"""Sessões temporárias de stream (token → URL + headers)."""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field

logger = __import__("logging").getLogger(__name__)

_PURGE_INTERVAL = 300.0


@dataclass
class StreamSession:
    url: str
    headers: dict[str, str]
    page_url: str = ""
    created_at: float = field(default_factory=time.time)
    anime_title: str = ""
    episode_title: str = ""
    episode_number: str = ""
    episode_link: str = ""
    source_name: str = ""
    anime_image: str = ""
    season_number: int = 1
    source_color: str = ""


class StreamSessionStore:
    def __init__(self, ttl_seconds: float = 3600.0, max_sessions: int = 200):
        self._ttl = ttl_seconds
        self._max = max_sessions
        self._lock = threading.Lock()
        self._sessions: dict[str, StreamSession] = {}
        self._start_purger()

    def _start_purger(self) -> None:
        def _purge_loop() -> None:
            while True:
                time.sleep(_PURGE_INTERVAL)
                with self._lock:
                    self._purge_locked()

        t = threading.Thread(target=_purge_loop, daemon=True, name="stream-purge")
        t.start()

    def create(self, session: StreamSession) -> str:
        token = secrets.token_urlsafe(24)
        with self._lock:
            self._purge_locked()
            if len(self._sessions) >= self._max:
                oldest = min(self._sessions.items(), key=lambda kv: kv[1].created_at)
                del self._sessions[oldest[0]]
            self._sessions[token] = session
        return token

    def get(self, token: str) -> StreamSession | None:
        with self._lock:
            self._purge_locked()
            return self._sessions.get(token)

    def _purge_locked(self) -> None:
        now = time.time()
        expired = [k for k, v in self._sessions.items() if now - v.created_at > self._ttl]
        for k in expired:
            del self._sessions[k]
