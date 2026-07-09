"""Players de vídeo: backends polimórficos + orquestração.

API pública estável (importável de ``app.infrastructure.player``).
"""

from app.infrastructure.player.base import (
    PositionCallback,
    ProgressCallback,
    StatusCallback,
)
from app.infrastructure.player.download import download_video
from app.infrastructure.player.open_video import open_video
from app.infrastructure.player.registry import (
    PLAYER_AUTO,
    PLAYER_AUTO_ORDER,
    PLAYER_BROWSER,
    PLAYER_GSTREAMER,
    PLAYER_LABELS,
    PLAYER_MPV,
    PLAYER_VLC,
    VALID_PLAYERS,
    has_stream_player,
    install_hint,
    is_player_available,
    selectable_backends,
    try_play,
)

__all__ = [
    "PLAYER_AUTO",
    "PLAYER_AUTO_ORDER",
    "PLAYER_BROWSER",
    "PLAYER_GSTREAMER",
    "PLAYER_LABELS",
    "PLAYER_MPV",
    "PLAYER_VLC",
    "VALID_PLAYERS",
    "PositionCallback",
    "ProgressCallback",
    "StatusCallback",
    "download_video",
    "has_stream_player",
    "install_hint",
    "is_player_available",
    "open_video",
    "selectable_backends",
    "try_play",
]
