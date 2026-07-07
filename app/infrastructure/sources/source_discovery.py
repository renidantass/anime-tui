from __future__ import annotations

import logging
import pkgutil
import threading
from typing import TYPE_CHECKING

import requests

from app.application.interfaces import ISourceDiscovery
from app.application.dtos import SourceEntry
from app.infrastructure.sources._base import AnimeSource

if TYPE_CHECKING:
    from app.application.interfaces import IAnimeFeedReader

logger = logging.getLogger(__name__)


class SourceDiscovery(ISourceDiscovery):
    def __init__(self):
        self._sources: dict[str, SourceEntry] = {}
        self._readers: dict[str, IAnimeFeedReader] = {}
        self._bg_done = False

    def discover(self) -> dict[str, SourceEntry]:
        self._sources = {}
        self._readers = {}

        module_names = [
            name for _, name, _ in pkgutil.iter_modules(__path__)
            if not name.startswith("_")
        ]

        for mod_name in module_names:
            try:
                mod = __import__(f"app.infrastructure.sources.{mod_name}", fromlist=[mod_name])
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

                    self._sources[instance.identifier] = SourceEntry(
                        name=instance.name,
                        identifier=instance.identifier,
                        color=instance.color,
                        has_search=instance.has_search,
                        has_details=instance.has_details,
                    )
                    self._readers[instance.identifier] = instance

        self._bg_check()
        return dict(self._sources)

    def _bg_check(self):
        if self._bg_done:
            return

        def run():
            self._bg_done = True
            for ident, entry in list(self._sources.items()):
                reader = self._readers.get(ident)
                base_url = getattr(reader, 'base_url', '') if reader else ''
                if not base_url:
                    continue
                try:
                    resp = requests.get(base_url, timeout=8)
                    if resp.status_code != 200:
                        entry.available = False
                        entry.error = f"HTTP {resp.status_code}"
                except requests.RequestException as e:
                    entry.available = False
                    entry.error = f"{type(e).__name__}"

        t = threading.Thread(target=run, daemon=True)
        t.start()

    def get_all_entries(self) -> list[SourceEntry]:
        if not self._sources:
            self.discover()
        return list(self._sources.values())

    def get_enabled_entries(self) -> list[SourceEntry]:
        return [e for e in self.get_all_entries() if e.available]

    def is_available(self, identifier: str) -> bool:
        entry = self._sources.get(identifier)
        return entry is not None and entry.available

    def get_reader(self, identifier: str) -> IAnimeFeedReader | None:
        return self._readers.get(identifier)
