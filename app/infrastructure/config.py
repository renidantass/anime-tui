"""Configuração persistente do animes-tui (~/.config/animes-tui/config.json)."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path.home() / ".config" / "animes-tui"
_CONFIG_FILE = _CONFIG_DIR / "config.json"

_VALID_PLAYERS = frozenset(
    {
        "auto",
        "mpv",
        "vlc",
        "gstreamer",
        "browser",
        "ffplay",
    }
)

_URL_SCHEMES = frozenset({"http", "https"})


def _is_valid_http_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    try:
        p = urlparse(url.strip())
        return p.scheme in _URL_SCHEMES and bool(p.netloc)
    except Exception:
        return False


SOURCE_URL_DEFAULTS: dict[str, str] = {
    "animesonlinecc": "https://animesonlinecc.to",
    "animesonlinecloud": "https://animesonline.cloud",
    "goyabu": "https://goyabu.io",
    "topanimes": "https://topanimes.net",
    "animeyabu": "https://www.animeyabu.net",
}

_VALID_SOURCE_IDS = frozenset(SOURCE_URL_DEFAULTS.keys())


@dataclass
class Config:
    enabled_sources: list[str] | None = None
    player: str = "auto"
    source_urls: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.player or not isinstance(self.player, str):
            self.player = "auto"
        else:
            self.player = self.player.strip().lower() or "auto"
        if self.player not in _VALID_PLAYERS:
            logger.warning("Player '%s' inválido — usando auto", self.player)
            self.player = "auto"

        if self.enabled_sources is not None:
            self.enabled_sources = list(dict.fromkeys(self.enabled_sources))
            unknown = [s for s in self.enabled_sources if s not in _VALID_SOURCE_IDS]
            if unknown:
                logger.warning("Fontes desconhecidas em enabled_sources: %s", unknown)
                self.enabled_sources = [s for s in self.enabled_sources if s in _VALID_SOURCE_IDS]

        if not isinstance(self.source_urls, dict):
            self.source_urls = {}

        cleaned: dict[str, str] = {}
        for k, v in self.source_urls.items():
            if not isinstance(k, str) or not isinstance(v, str):
                continue
            url = v.strip().rstrip("/")
            if k in _VALID_SOURCE_IDS and _is_valid_http_url(url):
                cleaned[k] = url
            elif k in _VALID_SOURCE_IDS:
                logger.warning("URL inválida para fonte %s: '%s' — ignorada", k, v[:80])
        self.source_urls = cleaned

    def get_source_url(self, identifier: str) -> str:
        return self.source_urls.get(identifier) or SOURCE_URL_DEFAULTS.get(identifier, "")

    def to_dict(self) -> dict:
        return {
            "enabled_sources": self.enabled_sources,
            "player": self.player,
            "source_urls": self.source_urls,
        }

    @staticmethod
    def from_dict(data: dict) -> Config:
        return Config(
            enabled_sources=data.get("enabled_sources"),
            player=data.get("player", "auto"),
            source_urls=data.get("source_urls", {}),
        )


def load() -> Config:
    if not _CONFIG_FILE.exists():
        return Config()
    try:
        with open(_CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return Config.from_dict(data if isinstance(data, dict) else {})
    except Exception as e:
        logger.warning("Falha ao carregar configuração: %s — usando padrão", e)
        return Config()


def save(config: Config) -> None:
    try:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _CONFIG_FILE.with_name(f".{_CONFIG_FILE.name}.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
        tmp.replace(_CONFIG_FILE)
    except Exception as e:
        logger.warning("Falha ao salvar configuração: %s", e)
