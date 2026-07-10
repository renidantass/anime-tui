"""Entrypoint da interface web — wiring + servidor."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from fastapi.staticfiles import StaticFiles
from bootstrap import web_lifespan
from app.presentation.web.server import create_app
from app.infrastructure.logging_config import configure_logging

STATIC_DIR = Path(__file__).resolve().parent / "app" / "presentation" / "web" / "static"

configure_logging()
logger = logging.getLogger(__name__)

app = create_app(lifespan=web_lifespan())

if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


def main() -> None:
    parser = argparse.ArgumentParser(description="Animes Web — UI estilo Netflix")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    import uvicorn

    target = "web_main:app" if args.reload else app
    logger.info("Animes Web -> http://%s:%s", args.host, args.port)
    uvicorn.run(
        target,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
