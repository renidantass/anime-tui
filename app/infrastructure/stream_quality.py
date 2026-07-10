"""Escolha de stream pela maior qualidade disponível.

Usado por Blogger (itags YouTube), players JW (Alibaba/Ruplay/etc.) e
heurísticas genéricas de URL/label (1080p, 720p, HD…).
"""

from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import parse_qs, unquote, urlparse

# Progressive (áudio+vídeo) — preferidos no <video>/mpv simples
_ITAG_PROGRESSIVE: dict[int, int] = {
    17: 144,
    36: 240,
    18: 360,
    22: 720,
    37: 1080,
    38: 3072,
    43: 360,  # webm
    44: 480,
    45: 720,
    46: 1080,
    59: 480,
    78: 480,
    82: 360,
    83: 480,
    84: 720,
    85: 1080,
}

# DASH video-only (sem áudio embutido) — só se não houver progressive
_ITAG_DASH_VIDEO: dict[int, int] = {
    133: 240,
    134: 360,
    135: 480,
    136: 720,
    137: 1080,
    138: 2160,
    160: 144,
    242: 240,
    243: 360,
    244: 480,
    247: 720,
    248: 1080,
    264: 1440,
    266: 2160,
    271: 1440,
    278: 144,
    298: 720,   # 60fps
    299: 1080,
    302: 720,
    303: 1080,
    308: 1440,
    313: 2160,
    315: 2160,
    330: 144,
    331: 240,
    332: 360,
    333: 480,
    334: 720,
    335: 1080,
    336: 1440,
    337: 2160,
    394: 144,   # AV1
    395: 240,
    396: 360,
    397: 480,
    398: 720,
    399: 1080,
    400: 1440,
    401: 2160,
}

_HEIGHT_IN_TEXT = re.compile(
    r"(?<!\d)(2160|1440|1080|720|576|480|360|240|144)p?\b",
    re.I,
)

_QUALITY_TOKEN = re.compile(
    r"\b(4k|uhd|fhd|full\s*hd|hd|sd|high|medium|med|low|auto|original|source|max)\b",
    re.I,
)

_TOKEN_HEIGHT = {
    "4k": 2160,
    "uhd": 2160,
    "fhd": 1080,
    "fullhd": 1080,
    "full hd": 1080,
    "hd": 720,
    "sd": 480,
    "high": 900,
    "medium": 480,
    "med": 480,
    "low": 240,
    "auto": 0,
    "original": 2000,
    "source": 2000,
    "max": 2000,
}


def height_from_itag(itag: int) -> int:
    """Altura estimada (px) do itag YouTube/Blogger; 0 se desconhecido."""
    if itag in _ITAG_PROGRESSIVE:
        return _ITAG_PROGRESSIVE[itag]
    if itag in _ITAG_DASH_VIDEO:
        return _ITAG_DASH_VIDEO[itag]
    return 0


def is_progressive_itag(itag: int) -> bool:
    return itag in _ITAG_PROGRESSIVE


def height_from_text(*parts: str) -> int:
    """Maior altura citada em labels/URLs (1080p, 720, HD…)."""
    best = 0
    for part in parts:
        if not part:
            continue
        text = unquote(str(part)).replace("_", " ").replace("-", " ")
        for m in _HEIGHT_IN_TEXT.finditer(text):
            best = max(best, int(m.group(1)))
        for m in _QUALITY_TOKEN.finditer(text):
            tok = re.sub(r"\s+", " ", m.group(1).lower())
            best = max(best, _TOKEN_HEIGHT.get(tok, 0))
    return best


def height_from_url(url: str) -> int:
    if not url:
        return 0
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    blobs = [url, parsed.path]
    for key in ("q", "quality", "res", "resolution", "h", "height", "size", "label"):
        for v in qs.get(key) or []:
            blobs.append(v)
    # itag na query googlevideo
    itags = qs.get("itag") or []
    for raw in itags:
        try:
            h = height_from_itag(int(raw))
            if h:
                return h
        except (TypeError, ValueError):
            pass
    return height_from_text(*blobs)


def blogger_stream_rank(
    *,
    itag: int,
    url: str = "",
    mime: str = "",
) -> tuple[int, int, int, int]:
    """Ranking de stream Blogger/YouTube — maior é melhor.

    Ordem:
      1) progressive (A+V) > DASH video-only
      2) altura (px)
      3) prefere mp4 a webm
      4) itag como desempate fraco
    """
    height = height_from_itag(itag) or height_from_url(url)
    progressive = 1 if is_progressive_itag(itag) else 0
    # se itag desconhecido mas mime tem áudio embutido tipicamente
    low_mime = (mime or "").lower()
    if progressive == 0 and "mp4" in low_mime and itag in (0,):
        progressive = 1
    is_mp4 = 1 if ("mp4" in low_mime or ".mp4" in (url or "").lower()) else 0
    # video-only DASH sem altura conhecida: ainda tenta, mas por último
    return (progressive, height, is_mp4, itag if height else 0)


def media_url_rank(url: str, label: str = "") -> tuple[int, int, int, int]:
    """Ranking genérico de URL de mídia (JW Player, Alibaba CDN, etc.).

    Ordem:
      1) altura (label + URL)
      2) mp4 > m3u8 > outros
      3) evita nomes “low/mobile”
      4) comprimento da URL (desempate estável)
    """
    height = max(height_from_text(label), height_from_url(url))
    low = f"{url} {label}".lower()
    if ".mp4" in low:
        container = 3
    elif ".m3u8" in low or "mpegurl" in low:
        container = 2
    elif ".webm" in low:
        container = 1
    else:
        container = 0
    penalty = 0
    if re.search(r"\b(low|mobile|tiny|min|lq|small)\b", low):
        penalty = 1
    return (height, container, -penalty, len(url or ""))


def pick_best_url(
    urls: Iterable[str],
    *,
    labels: dict[str, str] | None = None,
) -> str | None:
    """Escolhe a URL de maior qualidade; None se lista vazia."""
    labels = labels or {}
    best_url: str | None = None
    best_rank: tuple | None = None
    for u in urls:
        if not u:
            continue
        rank = media_url_rank(u, labels.get(u, ""))
        if best_rank is None or rank > best_rank:
            best_rank = rank
            best_url = u
    return best_url


def pick_best_labeled(items: Iterable[tuple[str, str]]) -> str | None:
    """items = (url, label)."""
    best_url: str | None = None
    best_rank: tuple | None = None
    for url, label in items:
        if not url:
            continue
        rank = media_url_rank(url, label or "")
        if best_rank is None or rank > best_rank:
            best_rank = rank
            best_url = url
    return best_url
