"""Anishelf — bandeja do sistema para iniciar/parar o servidor web.

Dá duplo-clique no executável e controla pelo ícone na bandeja:
  Iniciar servidor → só liga o servidor
  Abrir AniShelf    → abre o navegador
  Parar servidor    → desliga o servidor
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import webbrowser
from pathlib import Path

import pystray
import uvicorn
from PIL import Image, ImageDraw

from app.infrastructure.logging_config import configure_logging
from app.presentation.web.server import create_app
from bootstrap import web_lifespan

HOST = "127.0.0.1"
PORT = 8080
URL = f"http://{HOST}:{PORT}"

logger = logging.getLogger(__name__)


def _static_dir() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", ""))
    else:
        base = Path(__file__).resolve().parent
    return base / "app" / "presentation" / "web" / "static"


def _log_file_path() -> Path | None:
    if getattr(sys, "frozen", False):
        log_dir = Path.home() / ".anishelf" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir / "anishelf.log"
    return None


def _make_icon(running: bool = False) -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    fg = (0, 240, 255) if running else (96, 100, 112)  # cyan / muted gray

    # outer ring
    d.ellipse([3, 3, size - 3, size - 3], fill=(18, 24, 42))
    d.ellipse([3, 3, size - 3, size - 3], outline=fg, width=3)

    # play triangle
    cx = size // 2 + 1
    cy = size // 2
    s = 11
    d.polygon(
        [(cx - s + 4, cy - s), (cx - s + 4, cy + s), (cx + s - 2, cy)],
        fill=fg,
    )

    return img


class AnishelfApp:
    def __init__(self) -> None:
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._tray: pystray.Icon | None = None

    @property
    def running(self) -> bool:
        return self._running

    # ── server ────────────────────────────────────────────────────────

    def _build_app(self):
        configure_logging()
        log_path = _log_file_path()
        if log_path:
            os.environ["LOG_FILE"] = str(log_path)
            configure_logging()
            logger.info("Logging para arquivo: %s", log_path)
        app = create_app(lifespan=web_lifespan())
        static = _static_dir()
        logger.info("Static dir: %s (exists=%s)", static, static.is_dir())
        if static.is_dir():
            from fastapi.staticfiles import StaticFiles

            app.mount("/", StaticFiles(directory=str(static), html=True), name="static")
        return app

    def _server_loop(self) -> None:
        logger.info("Iniciando servidor em %s:%s", HOST, PORT)
        try:
            app = self._build_app()
        except Exception:
            logger.exception("Falha ao construir app")
            self._running = False
            self._update_tray()
            return
        config = uvicorn.Config(app, host=HOST, port=PORT, log_level="warning")
        self._server = uvicorn.Server(config)
        try:
            self._server.run()
        except Exception:
            logger.exception("servidor caiu")
        finally:
            self._running = False
            self._update_tray()

    # ── actions ───────────────────────────────────────────────────────

    def _start(self, _icon=None) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._server_loop, daemon=True)
        self._thread.start()
        self._update_tray()
        logger.info("Servidor iniciado em %s", URL)

    def _stop(self, _icon=None) -> None:
        if not self._running or self._server is None:
            return
        self._server.should_exit = True
        self._running = False
        self._server = None
        self._thread = None
        self._update_tray()
        logger.info("Servidor parado")

    def _open_browser(self, _icon=None) -> None:
        webbrowser.open(URL)

    def _quit(self, _icon=None) -> None:
        self._stop()
        if self._tray:
            self._tray.visible = False
            self._tray.stop()

    # ── tray ──────────────────────────────────────────────────────────

    def _update_tray(self) -> None:
        if self._tray:
            self._tray.icon = _make_icon(self._running)

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(
                "Iniciar servidor",
                self._start,
                enabled=not self._running,
                default=True,
            ),
            pystray.MenuItem("Abrir AniShelf", self._open_browser),
            pystray.MenuItem(
                "Parar servidor",
                self._stop,
                enabled=self._running,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Sair", self._quit),
        )

    def run(self) -> None:
        icon = _make_icon(False)
        self._tray = pystray.Icon(
            "anishelf",
            icon,
            "Anishelf",
            menu=self._build_menu,
        )
        self._tray.run()


def main() -> None:
    if getattr(sys, "frozen", False):
        log_path = _log_file_path()
        if log_path:
            sys.stdout = sys.stderr = open(str(log_path), "a", encoding="utf-8")
    configure_logging()
    AnishelfApp().run()


if __name__ == "__main__":
    main()
