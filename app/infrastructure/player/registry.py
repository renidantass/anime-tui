"""Registro de backends de player (polimorfismo + descoberta)."""

from __future__ import annotations

from app.infrastructure.player.backends import (
    AutoBackend,
    BrowserBackend,
    FfplayBackend,
    GstreamerBackend,
    MpvBackend,
    VlcBackend,
)
from app.infrastructure.player.base import PlayRequest, VideoBackend

# Constantes públicas (ids estáveis no config.json)
PLAYER_AUTO = AutoBackend.id
PLAYER_MPV = MpvBackend.id
PLAYER_VLC = VlcBackend.id
PLAYER_GSTREAMER = GstreamerBackend.id
PLAYER_BROWSER = BrowserBackend.id
PLAYER_FFPLAY = FfplayBackend.id

# Ordem de preferência no modo automático (+ ffplay como último recurso)
_AUTO_ORDER: tuple[type[VideoBackend], ...] = (
    MpvBackend,
    VlcBackend,
    GstreamerBackend,
)
_FALLBACK_EXTRA: tuple[type[VideoBackend], ...] = (FfplayBackend,)

# Instâncias singleton
_INSTANCES: dict[str, VideoBackend] = {
    b.id: b
    for b in (
        AutoBackend(),
        MpvBackend(),
        VlcBackend(),
        GstreamerBackend(),
        BrowserBackend(),
        FfplayBackend(),
    )
}

VALID_PLAYERS = frozenset(_INSTANCES) - {PLAYER_FFPLAY}  # ffplay não é opção de config
PLAYER_LABELS = {bid: b.label for bid, b in _INSTANCES.items() if b.selectable}
PLAYER_AUTO_ORDER = tuple(cls.id for cls in _AUTO_ORDER)


def get_backend(name: str) -> VideoBackend | None:
    return _INSTANCES.get(name)


def selectable_backends() -> list[VideoBackend]:
    """Backends exibidos na UI de opções (inclui auto e browser)."""
    order = (
        PLAYER_AUTO,
        PLAYER_MPV,
        PLAYER_VLC,
        PLAYER_GSTREAMER,
        PLAYER_BROWSER,
    )
    return [_INSTANCES[k] for k in order if k in _INSTANCES]


def install_hint(name: str) -> str:
    b = _INSTANCES.get(name)
    return b.install_hint if b else f"instale {name}"


def is_player_available(name: str) -> bool:
    backend = _INSTANCES.get(name)
    if backend is None:
        return bool(__import__("shutil").which(name))
    return backend.is_available()


def auto_chain_available() -> bool:
    return any(_INSTANCES[c.id].is_available() for c in _AUTO_ORDER) or _INSTANCES[
        PLAYER_FFPLAY
    ].is_available()


def fallback_backends(preferred: str) -> list[VideoBackend]:
    """Cadeia de tentativa: preferido primeiro, depois auto-order + ffplay.

    Browser e Auto não entram como “lançadores” aqui — Auto expande a ordem;
    Browser é tratado à parte pelo orquestrador.
    """
    if preferred == PLAYER_BROWSER:
        return []
    if preferred == PLAYER_AUTO:
        names = [*PLAYER_AUTO_ORDER, PLAYER_FFPLAY]
    else:
        rest = [p for p in PLAYER_AUTO_ORDER if p != preferred]
        names = [preferred, *rest, PLAYER_FFPLAY]
    return [b for n in names if (b := _INSTANCES.get(n)) is not None]


def try_play(preferred: str, request: PlayRequest) -> bool:
    """Tenta a cadeia de backends até um aceitar o pedido."""
    for backend in fallback_backends(preferred):
        if backend.play(request):
            return True
    return False


def has_stream_player() -> bool:
    return is_player_available(PLAYER_AUTO)
