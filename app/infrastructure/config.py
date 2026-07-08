"""Configuração persistente do animes-tui (~/.config/animes-tui/config.json)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path.home() / ".config" / "animes-tui"
_CONFIG_FILE = _CONFIG_DIR / "config.json"

PLAYER_BROWSER = "browser"
PLAYER_MPV = "mpv"
PLAYER_VLC = "vlc"
PLAYER_GSTREAMER = "gstreamer"
PLAYER_AUTO = "auto"  # primeiro disponível: mpv → vlc → gstreamer → download

VALID_PLAYERS = frozenset({
    PLAYER_BROWSER,
    PLAYER_MPV,
    PLAYER_VLC,
    PLAYER_GSTREAMER,
    PLAYER_AUTO,
})

PLAYER_LABELS = {
    PLAYER_AUTO: "Automático",
    PLAYER_MPV: "mpv",
    PLAYER_VLC: "VLC",
    PLAYER_GSTREAMER: "GStreamer",
    PLAYER_BROWSER: "Navegador",
}

# Ordem de preferência no modo automático
PLAYER_AUTO_ORDER = (PLAYER_MPV, PLAYER_VLC, PLAYER_GSTREAMER)


@dataclass
class Config:
    enabled_sources: list[str] | None = None
    player: str = PLAYER_AUTO

    def __post_init__(self) -> None:
        if self.player not in VALID_PLAYERS:
            self.player = PLAYER_AUTO
        if self.enabled_sources is not None:
            self.enabled_sources = list(self.enabled_sources)

    def to_dict(self) -> dict:
        return {
            "enabled_sources": self.enabled_sources,
            "player": self.player,
        }

    @staticmethod
    def from_dict(data: dict) -> Config:
        return Config(
            enabled_sources=data.get("enabled_sources"),
            player=data.get("player", PLAYER_AUTO),
        )


def load() -> Config:
    """Load config from disk. Returns default Config if missing/corrupt."""
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
    """Persist config to disk."""
    try:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning("Falha ao salvar configuração: %s", e)
