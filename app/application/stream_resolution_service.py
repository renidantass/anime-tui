"""Resolução de stream com fallback entre múltiplas fontes.

Serviço de aplicação — compartilhado entre TUI e Web.
"""

from __future__ import annotations

import logging
from typing import Callable

import requests

from app.application.dtos import PlayCandidate, ResolvedPlay
from app.domain import PlayContext
from app.infrastructure.blogger_extractor import is_blogger_url
from app.infrastructure.security import is_safe_url
from app.infrastructure.sources._playback import resolve_blogger_context
from app.infrastructure.sources._utils import HEADERS

logger = logging.getLogger(__name__)


class StreamResolutionService:
    """Resolve streams com fallback automático entre fontes candidatas."""

    def finalize_play_context(self, ctx: PlayContext) -> PlayContext:
        """Resolve embeds Blogger e valida URL — espelha open_video._finalize_context."""
        url = (ctx.url or "").strip()
        if not url:
            return ctx

        if not is_safe_url(url, allow_http=True, resolve_dns=False):
            logger.warning("URL inicial bloqueada: %s…", url[:80])
            return PlayContext.page(url)

        sess = requests.Session()
        sess.headers.update(HEADERS)

        if not is_blogger_url(url):
            return ctx

        page = ctx.page_url or url
        resolved = resolve_blogger_context(url, page_url=page, session=sess)
        if resolved is None:
            resolved = resolve_blogger_context(url, page_url=page, session=None)
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

    def build_upstream_headers(self, ctx: PlayContext) -> dict[str, str]:
        headers = dict(HEADERS)
        headers.update(ctx.http_headers())
        if "User-Agent" not in headers:
            headers["User-Agent"] = HEADERS["User-Agent"]
        return headers

    def probe_stream(
        self, url: str, headers: dict[str, str] | None = None
    ) -> tuple[bool, str]:
        """Verifica se a URL responde como mídia (Range/HEAD).

        Returns:
            (ok, reason)
        """
        if not url or not is_safe_url(url, allow_http=True, resolve_dns=True):
            return False, "URL insegura ou vazia"

        hdrs = dict(HEADERS)
        if headers:
            hdrs.update(headers)
        hdrs.setdefault("Range", "bytes=0-2047")

        try:
            with requests.get(
                url,
                headers=hdrs,
                timeout=(8, 20),
                stream=True,
                allow_redirects=True,
            ) as r:
                if r.status_code not in (200, 206) and not (200 <= r.status_code < 400):
                    return False, f"HTTP {r.status_code}"

                ct = (r.headers.get("Content-Type") or "").lower()
                ok_ct = (
                    not ct
                    or ct.startswith("video/")
                    or "mpegurl" in ct
                    or "octet-stream" in ct
                    or "binary" in ct
                    or "mp2t" in ct
                    or "application/x-mpegurl" in ct
                )
                if ct.startswith("text/html") or (
                    "text/plain" in ct and "mpegurl" not in ct
                ):
                    return False, f"content-type não é mídia ({ct or '?'})"

                chunk = next(r.iter_content(chunk_size=512), b"")
                if not chunk and r.status_code not in (200, 206):
                    return False, "corpo vazio"

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

    def order_candidates(
        self,
        *,
        candidates: list[PlayCandidate],
        preferred_source: str | None,
        episode_link: str,
        source_color: str = "",
    ) -> list[PlayCandidate]:
        """Ordena fontes: preferred primeiro, depois demais (sem duplicar link)."""
        ordered: list[PlayCandidate] = []
        seen_links: set[str] = set()

        def add(c: PlayCandidate) -> None:
            link = (c.link or "").strip()
            if not link or link in seen_links:
                return
            if not is_safe_url(link, allow_http=True, resolve_dns=False):
                return
            seen_links.add(link)
            ordered.append(
                PlayCandidate(name=c.name or "", link=link, color=c.color or "")
            )

        pref = (preferred_source or "").strip()
        if pref:
            for c in candidates:
                if c.name == pref:
                    add(c)
                    break

        for c in candidates:
            add(c)

        if not ordered and episode_link:
            add(
                PlayCandidate(
                    name=pref,
                    link=episode_link,
                    color=source_color,
                )
            )

        return ordered

    def resolve_with_fallback(
        self,
        *,
        candidates: list[PlayCandidate],
        get_context: Callable[[str, str | None], PlayContext | None],
        require_probe: bool = True,
    ) -> ResolvedPlay | None:
        """Tenta cada fonte até achar stream direto disponível.

        Preferência: stream playable (is_direct + probe). Se nenhuma for playable,
        devolve a primeira resolução com URL de página (fallback externo).
        """
        tried: list[dict] = []
        page_fallback: ResolvedPlay | None = None

        for cand in candidates:
            name = cand.name or "?"
            link = cand.link
            try:
                ctx = get_context(link, cand.name or None)
            except Exception as e:
                logger.warning("get_play_context falhou (%s): %s", name, e)
                tried.append(
                    {"name": name, "link": link, "ok": False, "reason": str(e)[:120]}
                )
                continue

            if not ctx or not (ctx.url or "").strip():
                tried.append(
                    {
                        "name": name,
                        "link": link,
                        "ok": False,
                        "reason": "sem play_context",
                    }
                )
                continue

            try:
                ctx = self.finalize_play_context(ctx)
            except Exception as e:
                tried.append(
                    {
                        "name": name,
                        "link": link,
                        "ok": False,
                        "reason": f"finalize: {e}"[:120],
                    }
                )
                continue

            url = (ctx.url or "").strip()
            if not url:
                tried.append(
                    {"name": name, "link": link, "ok": False, "reason": "URL vazia"}
                )
                continue

            is_direct = bool(ctx.is_direct) and is_safe_url(
                url, allow_http=True, resolve_dns=False
            )

            if not is_direct:
                tried.append(
                    {
                        "name": name,
                        "link": link,
                        "ok": False,
                        "reason": "stream não é direto",
                        "playable": False,
                    }
                )
                if page_fallback is None:
                    page_fallback = ResolvedPlay(
                        ctx=ctx,
                        link=link,
                        source_name=name,
                        source_color=cand.color,
                        playable=False,
                        tried=list(tried),
                    )
                continue

            headers = self.build_upstream_headers(ctx)
            if require_probe:
                ok, reason = self.probe_stream(url, headers)
                if not ok:
                    logger.info("Probe falhou para %s: %s", name, reason)
                    tried.append(
                        {
                            "name": name,
                            "link": link,
                            "ok": False,
                            "reason": f"probe: {reason}",
                            "playable": False,
                        }
                    )
                    continue
                probe_reason = reason
            else:
                probe_reason = "probe skipped"

            tried.append(
                {
                    "name": name,
                    "link": link,
                    "ok": True,
                    "reason": probe_reason,
                    "playable": True,
                }
            )
            return ResolvedPlay(
                ctx=ctx,
                link=link,
                source_name=name,
                source_color=cand.color,
                playable=True,
                tried=list(tried),
            )

        if page_fallback is not None:
            page_fallback.tried = tried
            return page_fallback

        if tried:
            return ResolvedPlay(
                ctx=PlayContext.page(candidates[0].link if candidates else ""),
                link=candidates[0].link if candidates else "",
                source_name=candidates[0].name if candidates else "",
                source_color=candidates[0].color if candidates else "",
                playable=False,
                tried=list(tried),
            )
        return None
