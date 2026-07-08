"""Extrai URLs diretas de streams a partir de links Blogger com token.

O player antigo do Blogger embutia ``var VIDEO_CONFIG = {...}`` no HTML.
Desde 2025/2026 a página virou SPA e o stream vem da API interna
``/_/BloggerVideoPlayerUi/data/batchexecute`` (rpcid ``WcwnYd``).
"""

from __future__ import annotations

import json
import logging
import random
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, quote, urlparse

import requests

from app.infrastructure.security import is_safe_url, require_safe_url
from app.infrastructure.sources._utils import HEADERS

logger = logging.getLogger(__name__)

BLOGGER_VIDEO_RE = re.compile(
    r"https?://(?:www\.)?blogger\.com/video\.g\?token=(?P<token>[^&\s#]+)",
    re.IGNORECASE,
)

_BATCH_URL = "https://www.blogger.com/_/BloggerVideoPlayerUi/data/batchexecute"
_RPC_ID = "WcwnYd"
_WRB_RE = re.compile(r'\["wrb\.fr","WcwnYd","((?:\\.|[^"\\])*)"')


@dataclass(slots=True, frozen=True)
class BloggerStream:
    """Um formato de vídeo retornado pelo Blogger."""

    itag: int
    url: str
    mime: str = "video/mp4"


def is_blogger_url(url: str) -> bool:
    return bool(url and BLOGGER_VIDEO_RE.search(url))


def extract_token(url: str) -> str | None:
    m = BLOGGER_VIDEO_RE.search(url or "")
    if m:
        tok = m.group("token")
        # token só alfanumérico + _- típico do Blogger
        if tok and re.fullmatch(r"[A-Za-z0-9_\-]{16,512}", tok):
            return tok
        return None
    if url and "blogger.com" in url and "token=" in url:
        if not is_safe_url(url, allow_http=True, resolve_dns=False):
            return None
        qs = parse_qs(urlparse(url).query)
        tokens = qs.get("token")
        tok = tokens[0] if tokens else None
        if tok and re.fullmatch(r"[A-Za-z0-9_\-]{16,512}", tok):
            return tok
    return None


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def _fetch_bl(session: requests.Session, token: str) -> str:
    """Carrega a página do player para cookies + build label (``bl``)."""
    page_url = f"https://www.blogger.com/video.g?token={quote(token, safe='')}"
    page = session.get(page_url, timeout=20)
    page.raise_for_status()
    m = re.search(r"boq_bloggeruiserver_[^'\"\s]+", page.text)
    return m.group(0) if m else "boq_bloggeruiserver_20260706.01_p0"


def _call_batchexecute(session: requests.Session, token: str, bl: str) -> str:
    f_req = json.dumps(
        [[[_RPC_ID, json.dumps([token, None, 0]), None, "generic"]]],
        separators=(",", ":"),
    )
    params = {
        "rpcids": _RPC_ID,
        "source-path": "/video.g",
        "f.sid": str(random.randint(1, 10**15)),
        "bl": bl,
        "hl": "en",
        "rt": "c",
        "_reqid": str(random.randint(10_000, 99_999)),
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "Origin": "https://www.blogger.com",
        "Referer": "https://www.blogger.com/",
        "X-Same-Domain": "1",
    }
    resp = session.post(
        _BATCH_URL,
        params=params,
        data={"f.req": f_req},
        headers=headers,
        timeout=25,
    )
    resp.raise_for_status()
    return resp.text


def _parse_streams(raw: str) -> list[BloggerStream]:
    """Extrai lista de streams do payload batchexecute."""
    m = _WRB_RE.search(raw)
    if not m:
        raise ValueError("Resposta batchexecute sem wrb.fr/WcwnYd")

    # o grupo 1 é o conteúdo de uma string JSON (com escapes)
    inner = json.loads(f'"{m.group(1)}"')
    data = json.loads(inner) if isinstance(inner, str) else inner

    # data ≈ [status, null, [[url, [itag]], ...], thumbnail, iframe_id, content_id, bool]
    try:
        formats = data[2]
    except (IndexError, TypeError) as e:
        raise ValueError(f"Formato inesperado de payload Blogger: {data!r:.200}") from e

    streams: list[BloggerStream] = []
    for item in formats or []:
        if not item:
            continue
        url = item[0]
        if not isinstance(url, str):
            continue
        # só aceita googlevideo / hosts Google de mídia
        host = (urlparse(url).hostname or "").lower()
        if not any(
            host == h or host.endswith("." + h)
            for h in ("googlevideo.com", "googleusercontent.com", "gvt1.com")
        ):
            logger.warning("Blogger: host de stream recusado: %s", host)
            continue
        if not is_safe_url(url, allow_http=False, resolve_dns=True):
            continue
        itag = 0
        if len(item) > 1 and item[1]:
            itag = int(item[1][0]) if isinstance(item[1], list) else int(item[1])
        mime = "video/mp4"
        qs = parse_qs(urlparse(url).query)
        if qs.get("mime"):
            mime = qs["mime"][0]
        streams.append(BloggerStream(itag=itag, url=url, mime=mime))

    if not streams:
        raise ValueError("Nenhum stream encontrado no payload Blogger")
    return streams


def extract_streams(url_or_token: str, *, session: requests.Session | None = None) -> list[BloggerStream]:
    """Resolve um link ``video.g?token=…`` (ou o token puro) em streams diretos."""
    token = extract_token(url_or_token)
    if not token and url_or_token and re.fullmatch(r"[A-Za-z0-9_\-]{16,512}", url_or_token.strip()):
        token = url_or_token.strip()
    if not token:
        raise ValueError("Token Blogger vazio ou inválido")

    own = session is None
    sess = session or _session()
    try:
        bl = _fetch_bl(sess, token)
        raw = _call_batchexecute(sess, token, bl)
        streams = _parse_streams(raw)
        logger.info(
            "Blogger: %d stream(s) para token…%s → itags %s",
            len(streams),
            token[-8:],
            sorted(s.itag for s in streams),
        )
        return streams
    finally:
        if own:
            sess.close()


def extract_best_url(url_or_token: str, *, session: requests.Session | None = None) -> str:
    """Retorna a melhor URL de stream (itag mais alto, ex.: 22 > 18)."""
    streams = extract_streams(url_or_token, session=session)
    best = max(streams, key=lambda s: s.itag)
    safe = require_safe_url(best.url, allow_http=False, resolve_dns=True)
    if not safe:
        raise ValueError("Stream Blogger rejeitado por segurança")
    return safe
