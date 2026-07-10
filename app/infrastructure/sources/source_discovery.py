from __future__ import annotations

import importlib
import logging
import pkgutil
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import requests

from app.application.dtos import SourceEntry
from app.application.interfaces import ISourceDiscovery
from app.infrastructure.circuit_breaker import CircuitBreaker
from app.infrastructure.config import Config
from app.infrastructure.sources._base import AnimeSource
from app.infrastructure.sources._utils import HEADERS

if TYPE_CHECKING:
    from app.application.interfaces import IAnimeFeedReader

logger = logging.getLogger(__name__)

_RECENT_WINDOW = 40
_CHECK_TIMEOUT = 8
_HEALTH_LOG_COOLDOWN = 300


class SourceDiscovery(ISourceDiscovery):
    def __init__(self, config: Config | None = None):
        self._sources: dict[str, SourceEntry] = {}
        self._readers: dict[str, IAnimeFeedReader] = {}
        self._lock = threading.Lock()
        self._bg_done = False
        self._discovered = False
        self._checking = False
        self._config = config or Config()
        self._cb = CircuitBreaker()
        self._health_alerted: dict[str, float] = {}
        self._on_health_change: Callable[[str, str, bool], None] | None = None

    def discover(self) -> dict[str, SourceEntry]:
        if self._discovered:
            with self._lock:
                return dict(self._sources)
        self._discovered = True

        module_names = [
            name
            for _, name, _ in pkgutil.iter_modules(
                importlib.import_module("app.infrastructure.sources").__path__
            )
            if not name.startswith("_")
        ]

        for mod_name in module_names:
            try:
                mod = importlib.import_module(f"app.infrastructure.sources.{mod_name}")
            except Exception as e:
                logger.warning("Falha ao importar %s: %s", mod_name, e)
                continue

            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, AnimeSource)
                    and attr is not AnimeSource
                    and not getattr(attr, "abstract", False)
                ):
                    try:
                        instance = attr()
                    except Exception as e:
                        logger.warning("Falha ao instanciar %s: %s", attr_name, e)
                        continue

                    cfg_url = self._config.get_source_url(instance.identifier)
                    if cfg_url:
                        instance.base_url = cfg_url.rstrip("/")

                    with self._lock:
                        self._sources[instance.identifier] = SourceEntry(
                            name=instance.name,
                            identifier=instance.identifier,
                            color=instance.color,
                            has_search=instance.has_search,
                            has_details=instance.has_details,
                            base_url=instance.base_url,
                        )
                        self._readers[instance.identifier] = instance

        self._bg_check()
        with self._lock:
            return dict(self._sources)

    def _bg_check(self):
        if self._bg_done:
            return

        def run():
            try:
                self.check_all(mark_checking=True)
            finally:
                self._bg_done = True

        t = threading.Thread(target=run, daemon=True, name="source-health")
        t.start()

    def check_all(self, mark_checking: bool = False) -> list[SourceEntry]:
        """Health check síncrono de todas as fontes (atualiza uptime/latência)."""
        with self._lock:
            if self._checking:
                return list(self._sources.values())
            self._checking = True
            idents = list(self._sources.keys())
            if mark_checking:
                for ident in idents:
                    e = self._sources.get(ident)
                    if e:
                        e.status = "checking"

        try:
            for ident in idents:
                self._check_one(ident)
        finally:
            with self._lock:
                self._checking = False

        with self._lock:
            return list(self._sources.values())

    def check_one(self, identifier: str) -> SourceEntry | None:
        with self._lock:
            if identifier not in self._sources:
                return None
            self._sources[identifier].status = "checking"
        self._check_one(identifier)
        with self._lock:
            return self._sources.get(identifier)

    def _check_one(self, identifier: str) -> None:
        with self._lock:
            entry = self._sources.get(identifier)
            reader = self._readers.get(identifier)
        if not entry:
            return

        base_url = (entry.base_url or getattr(reader, "base_url", "") or "").strip()
        if not base_url:
            with self._lock:
                entry.available = False
                entry.error = "sem base_url"
                entry.status = "offline"
                entry.latency_ms = None
                entry.last_check_at = datetime.now(UTC).isoformat()
                self._record_result(entry, False)
            return

        if not self._cb.allow(identifier):
            entry.status = "circuit_open"
            entry.error = "circuit breaker"
            return

        ok = False
        err = ""
        latency: float | None = None
        t0 = time.perf_counter()
        try:
            resp = requests.get(
                base_url,
                timeout=_CHECK_TIMEOUT,
                headers=HEADERS,
                allow_redirects=True,
            )
            latency = (time.perf_counter() - t0) * 1000.0
            if 200 <= resp.status_code < 400:
                ok = True
            else:
                err = f"HTTP {resp.status_code}"
        except requests.Timeout:
            latency = (time.perf_counter() - t0) * 1000.0
            err = "timeout"
        except requests.RequestException as e:
            latency = (time.perf_counter() - t0) * 1000.0
            err = type(e).__name__

        if ok:
            self._cb.record_success(identifier)
        else:
            self._cb.record_failure(identifier)

        with self._lock:
            was_available = entry.available
            entry.available = ok
            entry.error = "" if ok else err
            entry.latency_ms = round(latency, 1) if latency is not None else None
            entry.last_check_at = datetime.now(UTC).isoformat()
            entry.status = "online" if ok else "offline"
            self._record_result(entry, ok)

        if was_available != ok:
            self._maybe_alert(identifier, entry.name, ok)

    @staticmethod
    def _record_result(entry: SourceEntry, ok: bool) -> None:
        entry.checks_total = int(entry.checks_total or 0) + 1
        if ok:
            entry.checks_ok = int(entry.checks_ok or 0) + 1
        recent = list(getattr(entry, "_recent", []) or [])
        recent.append(ok)
        if len(recent) > _RECENT_WINDOW:
            recent = recent[-_RECENT_WINDOW:]
        entry._recent = recent
        if recent:
            entry.uptime_percent = round(100.0 * sum(1 for x in recent if x) / len(recent), 1)
        elif entry.checks_total > 0:
            entry.uptime_percent = round(100.0 * entry.checks_ok / entry.checks_total, 1)
        else:
            entry.uptime_percent = None

    def get_all_entries(self) -> list[SourceEntry]:
        if not self._discovered:
            self.discover()
        with self._lock:
            return list(self._sources.values())

    def get_enabled_entries(self) -> list[SourceEntry]:
        """Todas as fontes descobertas (preferência do usuário fica no AnimeService)."""
        return self.get_all_entries()

    def is_available(self, identifier: str) -> bool:
        with self._lock:
            entry = self._sources.get(identifier)
        return entry is not None and entry.available

    def get_reader(self, identifier: str) -> IAnimeFeedReader | None:
        with self._lock:
            return self._readers.get(identifier)

    def health_ready(self) -> bool:
        return self._bg_done

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        return self._cb

    def set_health_callback(self, cb: Callable[[str, str, bool], None] | None) -> None:
        self._on_health_change = cb

    def allow_request(self, identifier: str) -> bool:
        return self._cb.allow(identifier)

    def record_source_success(self, identifier: str) -> None:
        self._cb.record_success(identifier)

    def record_source_failure(self, identifier: str) -> None:
        self._cb.record_failure(identifier)

    def is_circuit_open(self, identifier: str) -> bool:
        return self._cb.is_open(identifier)

    def circuit_state(self, identifier: str) -> str:
        return self._cb.state(identifier)

    def _maybe_alert(self, identifier: str, name: str, is_online: bool) -> None:
        now = time.monotonic()
        last = self._health_alerted.get(identifier, 0)
        if is_online and last:
            logger.info("Fonte %s voltou ao ar", name)
            self._health_alerted.pop(identifier, None)
            if self._on_health_change:
                self._on_health_change(identifier, name, True)
        elif not is_online and now - last > _HEALTH_LOG_COOLDOWN:
            logger.warning("Fonte OFFLINE: %s", name)
            self._health_alerted[identifier] = now
            if self._on_health_change:
                self._on_health_change(identifier, name, False)
