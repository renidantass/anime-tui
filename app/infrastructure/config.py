"""Configuração persistente do animes-tui (~/.config/animes-tui/config.json)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path.home() / ".config" / "animes-tui"
_CONFIG_FILE = _CONFIG_DIR / "config.json"

# Default alinhado com player.registry.PLAYER_AUTO (evita import circular).
_DEFAULT_PLAYER = "auto"


@dataclass
class Config:
    enabled_sources: list[str] | None = None
    player: str = _DEFAULT_PLAYER

    def __post_init__(self) -> None:
        if not self.player or not isinstance(self.player, str):
            self.player = _DEFAULT_PLAYER
        else:
            self.player = self.player.strip() or _DEFAULT_PLAYER
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
            player=data.get("player", _DEFAULT_PLAYER),
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
