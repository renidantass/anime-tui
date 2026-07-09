"""Download e cache de streams de vídeo."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import requests

from app.infrastructure.player.base import CACHE_DIR, ProgressCallback
from app.infrastructure.security import is_safe_url
from app.infrastructure.sources._utils import HEADERS

logger = logging.getLogger(__name__)


def cache_path_for(key: str) -> Path:
    digest = hashlib.sha256(key.encode()).hexdigest()[:24]
    return CACHE_DIR / f"{digest}.mp4"


def download_video(
    stream_url: str,
    dest: Path,
    *,
    referer: str | None = None,
    origin: str | None = None,
    progress: ProgressCallback | None = None,
    session: requests.Session | None = None,
) -> Path:
    """Baixa o stream para *dest* (resume se parcial). Retorna o path final.

    *referer* / *origin* vêm do PlayContext da fonte (não hard-coded aqui).
    """
    if not is_safe_url(stream_url, allow_http=True, resolve_dns=True):
        raise ValueError("URL de download bloqueada por política de segurança")

    dest = dest.resolve()
    cache_root = CACHE_DIR.resolve()
    try:
        dest.relative_to(cache_root)
    except ValueError as e:
        raise ValueError("destino de cache inválido") from e

    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".part")

    own = session is None
    sess = session or requests.Session()
    sess.headers.update(HEADERS)

    headers: dict[str, str] = {}
    if referer:
        headers["Referer"] = referer
    if origin:
        headers["Origin"] = origin

    try:
        if dest.exists() and dest.stat().st_size > 0:
            logger.info("Cache hit: %s", dest.name)
            if progress:
                size = dest.stat().st_size
                progress(size, size)
            return dest

        start = partial.stat().st_size if partial.exists() else 0
        if start:
            headers["Range"] = f"bytes={start}-"

        resp = sess.get(stream_url, headers=headers, stream=True, timeout=60)
        try:
            if resp.status_code == 416:
                resp.close()
                partial.unlink(missing_ok=True)
                start = 0
                headers.pop("Range", None)
                resp = sess.get(stream_url, headers=headers, stream=True, timeout=60)

            resp.raise_for_status()

            total: int | None = None
            cr = resp.headers.get("Content-Range")
            if cr and "/" in cr:
                try:
                    total = int(cr.rsplit("/", 1)[1])
                except ValueError:
                    total = None
            elif resp.headers.get("Content-Length"):
                try:
                    total = start + int(resp.headers["Content-Length"])
                except ValueError:
                    total = None

            mode = "ab" if start and resp.status_code == 206 else "wb"
            if mode == "wb":
                start = 0

            downloaded = start
            with open(partial, mode) as f:
                for chunk in resp.iter_content(chunk_size=256 * 1024):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress:
                        progress(downloaded, total)
        finally:
            resp.close()

        partial.replace(dest)
        logger.info("Download concluído: %s (%s bytes)", dest.name, dest.stat().st_size)
        return dest
    finally:
        if own:
            sess.close()
