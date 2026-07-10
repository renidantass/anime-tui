"""Anishelf — bandeja do sistema para iniciar/parar o servidor web.

Dá duplo-clique no executável e controla pelo ícone na bandeja:
  Iniciar servidor → só liga o servidor
  Abrir AniShelf    → abre o navegador
  Parar servidor    → desliga o servidor
"""

from __future__ import annotations

import logging
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
PORT = 8765
URL = f"http://{HOST}:{PORT}"

logger = logging.getLogger(__name__)


def _static_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", "")) if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    return base / "app" / "presentation" / "web" / "static"


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
        app = create_app(lifespan=web_lifespan())
        static = _static_dir()
        if static.is_dir():
            from fastapi.staticfiles import StaticFiles

            app.mount("/", StaticFiles(directory=str(static), html=True), name="static")
        return app

    def _server_loop(self) -> None:
        config = uvicorn.Config(self._build_app(), host=HOST, port=PORT, log_level="warning")
        self._server = uvicorn.Server(config)
        try:
            self._server.run()
        except Exception:
            logger.exception("servidor caiu")

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
            self._tray.update_menu()

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(
                "Iniciar servidor",
                self._start,
                enabled=lambda item: not self._running,
                default=True,
            ),
            pystray.MenuItem("Abrir AniShelf", self._open_browser),
            pystray.MenuItem(
                "Parar servidor",
                self._stop,
                enabled=lambda item: self._running,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Sair", self._quit),
        )

    def run(self) -> None:
        configure_logging()
        icon = _make_icon(False)
        self._tray = pystray.Icon(
            "anishelf",
            icon,
            "Anishelf",
            menu=self._build_menu(),
        )
        self._tray.run()


def main() -> None:
    AnishelfApp().run()


if __name__ == "__main__":
    main()
