"""Helpers de playback compartilhados entre fontes (sem conhecimento no player de *sites*)."""

from __future__ import annotations

import logging

import requests

from app.domain.play_context import PlayContext
from app.infrastructure.blogger_extractor import extract_best_url, is_blogger_url

logger = logging.getLogger(__name__)

BLOGGER_REFERER = "https://www.blogger.com/"
BLOGGER_ORIGIN = "https://www.blogger.com"


def looks_like_media_url(url: str) -> bool:
    """Heurística genérica de mídia (extensão/mime), não de site."""
    low = (url or "").lower()
    return ".mp4" in low or ".m3u8" in low or "mime=video" in low or "googlevideo.com" in low


def resolve_blogger_context(
    embed_or_token_url: str,
    *,
    page_url: str,
    session: requests.Session | None = None,
) -> PlayContext | None:
    """Se for URL Blogger, resolve o stream e devolve PlayContext completo.

    Pode ser chamado pela source (pré-resolve) ou pelo open_video (no momento
    de tocar — mais resiliente e com feedback de status na UI).
    """
    if not is_blogger_url(embed_or_token_url):
        return None
    try:
        stream = extract_best_url(embed_or_token_url, session=session)
    except Exception as e:
        logger.warning("Falha ao resolver Blogger: %s", e)
        return None
    return PlayContext(
        url=stream,
        referer=BLOGGER_REFERER,
        origin=BLOGGER_ORIGIN,
        is_direct=True,
        page_url=page_url,
        cache_key=embed_or_token_url,
    )


def context_from_embed(
    embed_url: str,
    *,
    page_url: str,
    default_referer: str,
    default_origin: str | None = None,
    session: requests.Session | None = None,
    resolve_now: bool = False,
) -> PlayContext:
    """Monta PlayContext a partir de um embed da fonte.

    Por padrão **não** resolve Blogger aqui (fica para o open_video, com
    status na UI e menos chance de falha silenciosa). Passe
    ``resolve_now=True`` se a source quiser o stream já resolvido.
    """
    if is_blogger_url(embed_url):
        if resolve_now:
            blogger = resolve_blogger_context(embed_url, page_url=page_url, session=session)
            if blogger is not None:
                return blogger
        # Embed Blogger: headers corretos; open_video resolve o stream
        return PlayContext(
            url=embed_url,
            referer=BLOGGER_REFERER,
            origin=BLOGGER_ORIGIN,
            is_direct=True,
            page_url=page_url,
            cache_key=embed_url,
        )

    direct = looks_like_media_url(embed_url)
    return PlayContext(
        url=embed_url,
        referer=default_referer,
        origin=default_origin,
        is_direct=direct,
        page_url=page_url,
        cache_key=embed_url,
    )
