"""Resolução de stream com fallback entre múltiplas fontes — lógica pura.

Recebe funções de IO (probe, finalize) via injeção.
"""

from __future__ import annotations

import logging
from typing import Callable

from app.application.constants import HEADERS
from app.application.dtos import PlayCandidate, ResolvedPlay
from app.application.security import is_safe_url
from app.domain import PlayContext

logger = logging.getLogger(__name__)


class StreamResolutionService:
    """Resolve streams com fallback automático entre fontes candidatas."""

    def __init__(
        self,
        probe: Callable[..., tuple[bool, str]] | None = None,
        finalize: Callable[..., PlayContext] | None = None,
    ):
        self._probe = probe
        self._finalize = finalize

    def finalize_play_context(self, ctx: PlayContext) -> PlayContext:
        if self._finalize:
            return self._finalize(ctx)
        return ctx

    def build_upstream_headers(self, ctx: PlayContext) -> dict[str, str]:
        headers = dict(HEADERS)
        headers.update(ctx.http_headers())
        if "User-Agent" not in headers:
            headers["User-Agent"] = HEADERS["User-Agent"]
        return headers

    def order_candidates(
        self, *, candidates: list[PlayCandidate],
        preferred_source: str | None, episode_link: str, source_color: str = "",
    ) -> list[PlayCandidate]:
        ordered: list[PlayCandidate] = []
        seen_links: set[str] = set()

        def add(c: PlayCandidate) -> None:
            link = (c.link or "").strip()
            if not link or link in seen_links:
                return
            if not is_safe_url(link, allow_http=True):
                return
            seen_links.add(link)
            ordered.append(PlayCandidate(name=c.name or "", link=link, color=c.color or ""))

        pref = (preferred_source or "").strip()
        if pref:
            for c in candidates:
                if c.name == pref:
                    add(c)
                    break
        for c in candidates:
            add(c)
        if not ordered and episode_link:
            add(PlayCandidate(name=pref, link=episode_link, color=source_color))
        return ordered

    def resolve_with_fallback(
        self, *, candidates: list[PlayCandidate],
        get_context: Callable[[str, str | None], PlayContext | None],
        require_probe: bool = True,
    ) -> ResolvedPlay | None:
        tried: list[dict] = []
        page_fallback: ResolvedPlay | None = None
        for cand in candidates:
            name = cand.name or "?"
            link = cand.link
            try:
                ctx = get_context(link, cand.name or None)
            except Exception as e:
                logger.warning("get_play_context falhou (%s): %s", name, e)
                tried.append({"name": name, "link": link, "ok": False, "reason": str(e)[:120]})
                continue
            if not ctx or not (ctx.url or "").strip():
                tried.append({"name": name, "link": link, "ok": False, "reason": "sem play_context"})
                continue
            try:
                ctx = self.finalize_play_context(ctx)
            except Exception as e:
                tried.append({"name": name, "link": link, "ok": False, "reason": f"finalize: {e}"[:120]})
                continue
            url = (ctx.url or "").strip()
            if not url:
                tried.append({"name": name, "link": link, "ok": False, "reason": "URL vazia"})
                continue
            if not (bool(ctx.is_direct) and is_safe_url(url, allow_http=True)):
                tried.append({"name": name, "link": link, "ok": False, "reason": "stream não é direto", "playable": False})
                if page_fallback is None:
                    page_fallback = ResolvedPlay(ctx=ctx, link=link, source_name=name,
                                                  source_color=cand.color, playable=False, tried=list(tried))
                continue
            headers = self.build_upstream_headers(ctx)
            if require_probe and self._probe:
                ok, reason = self._probe(url, headers)
                if not ok:
                    logger.info("Probe falhou para %s: %s", name, reason)
                    tried.append({"name": name, "link": link, "ok": False, "reason": f"probe: {reason}", "playable": False})
                    continue
            else:
                reason = "probe skipped"
            tried.append({"name": name, "link": link, "ok": True, "reason": reason, "playable": True})
            return ResolvedPlay(ctx=ctx, link=link, source_name=name, source_color=cand.color,
                                 playable=True, tried=list(tried))
        if page_fallback is not None:
            page_fallback.tried = tried
            return page_fallback
        if tried:
            return ResolvedPlay(ctx=PlayContext.page(candidates[0].link if candidates else ""),
                                 link=candidates[0].link if candidates else "",
                                 source_name=candidates[0].name if candidates else "",
                                 source_color=candidates[0].color if candidates else "",
                                 playable=False, tried=list(tried))
        return None
