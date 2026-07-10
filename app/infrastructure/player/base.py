"""Backend de player de vídeo — interface polimórfica."""

from __future__ import annotations

import logging
import subprocess
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.infrastructure.security import safe_player_url
from app.infrastructure.sources._utils import HEADERS

logger = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".cache" / "animes-tui" / "videos"
IPC_DIR = Path.home() / ".cache" / "animes-tui" / "ipc"

DEFAULT_UA = HEADERS.get(
    "User-Agent",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
)

PositionCallback = Callable[[float, float], None]
ProgressCallback = Callable[[int, int | None], None]
StatusCallback = Callable[[str], None]


@dataclass(frozen=True)
class PlayRequest:
    """Pedido de reprodução (stream remoto ou arquivo local).

    *referer* vem do :class:`~app.domain.play_context.PlayContext` da fonte.
    """

    target: str
    stream: bool
    referer: str = ""
    start_at: float = 0.0
    on_position: PositionCallback | None = None


class VideoBackend(ABC):
    """Um player concreto (mpv, VLC, …). Subclasses só implementam o que muda."""

    id: str = ""
    label: str = ""
    binary: str | None = None
    install_hint: str = ""
    selectable: bool = True  # aparece nas configurações
    supports_progress: bool = False

    def is_available(self) -> bool:
        if self.binary is None:
            return True
        import shutil

        return bool(shutil.which(self.binary))

    def play(self, request: PlayRequest) -> bool:
        target = self._sanitize_target(request)
        if target is None:
            return False
        return self._launch(
            PlayRequest(
                target=target,
                stream=request.stream,
                referer=request.referer,
                start_at=request.start_at,
                on_position=request.on_position,
            )
        )

    def _sanitize_target(self, request: PlayRequest) -> str | None:
        if request.stream:
            safe = safe_player_url(request.target)
            if not safe:
                logger.warning("Player recusou URL insegura: %s…", request.target[:80])
                return None
            return safe

        path = Path(request.target)
        if not path.is_file():
            return None
        try:
            path.resolve().relative_to(CACHE_DIR.resolve())
        except ValueError:
            logger.warning("Arquivo fora do cache recusado: %s", path)
            return None
        return str(path.resolve())

    @abstractmethod
    def _launch(self, request: PlayRequest) -> bool:
        """Lança o processo (target já sanitizado)."""

    def _start_monitor(
        self,
        proc: subprocess.Popen,
        on_position: PositionCallback | None,
        **ctx,
    ) -> None:
        if not on_position or not self.supports_progress:
            return

        def _run() -> None:
            try:
                self._monitor(proc, on_position, **ctx)
            except Exception:
                logger.debug("monitor de progresso falhou", exc_info=True)

        threading.Thread(target=_run, daemon=True).start()

    def _monitor(
        self,
        proc: subprocess.Popen,
        on_position: PositionCallback,
        **ctx,
    ) -> None:
        proc.wait()


def popen(args: list[str]) -> subprocess.Popen | None:
    try:
        return subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as e:
        logger.warning("Falha ao executar %s: %s", args[0], e)
        return None


def ensure_ipc_dir() -> Path:
    IPC_DIR.mkdir(parents=True, exist_ok=True)
    try:
        IPC_DIR.chmod(0o700)
    except OSError:
        pass
    return IPC_DIR


def which(name: str) -> str | None:
    import shutil

    return shutil.which(name)
