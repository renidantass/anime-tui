"""Entrypoint da interface web (estilo Netflix)."""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Animes Web — UI estilo Netflix")
    parser.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Porta (default: 8765)")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Auto-reload em desenvolvimento",
    )
    args = parser.parse_args()

    import uvicorn

    print(f"\n  Animes Web → http://{args.host}:{args.port}\n")
    uvicorn.run(
        "web.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
