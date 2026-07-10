"""Probe de stream HTTP + resolução de Blogger — operações de IO."""

from __future__ import annotations

import logging
from collections.abc import Callable

import requests

from app.application.constants import HEADERS
from app.application.security import is_blogger_url, is_safe_url
from app.domain import PlayContext

logger = logging.getLogger(__name__)


def probe_stream(url: str, headers: dict[str, str] | None = None) -> tuple[bool, str]:
    """Verifica se a URL responde como mídia (Range/HEAD)."""
    if not url or not is_safe_url(url, allow_http=True):
        return False, "URL insegura ou vazia"
    hdrs = dict(HEADERS)
    if headers:
        hdrs.update(headers)
    hdrs.setdefault("Range", "bytes=0-2047")
    try:
        with requests.get(
            url, headers=hdrs, timeout=(8, 20), stream=True, allow_redirects=True
        ) as r:
            if r.status_code not in (200, 206) and not (200 <= r.status_code < 400):
                return False, f"HTTP {r.status_code}"
            ct = (r.headers.get("Content-Type") or "").lower()
            if ct.startswith("text/html") or ("text/plain" in ct and "mpegurl" not in ct):
                return False, f"content-type não é mídia ({ct or '?'})"
            chunk = next(r.iter_content(chunk_size=512), b"")
            if not chunk and r.status_code not in (200, 206):
                return False, "corpo vazio"
            ok_ct = (
                not ct
                or ct.startswith("video/")
                or "mpegurl" in ct
                or "octet-stream" in ct
                or "binary" in ct
                or "mp2t" in ct
            )
            if not ok_ct and chunk:
                if chunk[:4] == b"\x00\x00\x00" or b"ftyp" in chunk[:32]:
                    return True, "ok (mp4 magic)"
                if chunk.lstrip().startswith(b"#EXTM3U"):
                    return True, "ok (m3u8)"
                return False, f"content-type suspeito ({ct or '?'})"
            return True, "ok"
    except requests.Timeout:
        return False, "timeout"
    except requests.RequestException as e:
        return False, str(e)[:120]


def finalize_with_blogger(
    ctx: PlayContext,
    resolve_blogger: Callable | None = None,
) -> PlayContext:
    """Resolve embeds Blogger via HTTP, delegando ao resolver injetado."""
    url = (ctx.url or "").strip()
    if not url:
        return ctx
    if not is_safe_url(url, allow_http=True):
        logger.warning("URL inicial bloqueada: %s…", url[:80])
        return PlayContext.page(url)
    if not is_blogger_url(url) or not resolve_blogger:
        return ctx
    sess = requests.Session()
    sess.headers.update(HEADERS)
    page = ctx.page_url or url
    resolved = resolve_blogger(url, page_url=page, session=sess)
    if resolved is None:
        resolved = resolve_blogger(url, page_url=page, session=None)
    if resolved is None:
        logger.warning("Não foi possível resolver embed Blogger: %s…", url[:80])
        return PlayContext(
            url=url,
            referer=ctx.referer,
            origin=ctx.origin,
            is_direct=False,
            page_url=page,
            cache_key=ctx.cache_key or url,
        )
    return resolved
