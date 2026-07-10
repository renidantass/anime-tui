"""Helpers para temas WordPress DooPlay (animesonline*, topanimes-like)."""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from app.domain import PlayContext
from app.infrastructure.security import is_safe_url
from app.infrastructure.sources._playback import context_from_embed, looks_like_media_url
from app.infrastructure.sources._utils import HEADERS, validate_response
from app.infrastructure.stream_quality import media_url_rank

logger = logging.getLogger(__name__)

_PLAYER_OPTION_SEL = (
    "li.dooplay_player_option, .dooplay_player_option, ul.playeroptionsul li, #playeroptionsul li"
)


def img_src(tag) -> str:
    """src / data-src / data-lazy-src de um <img>."""
    if not tag:
        return ""
    for attr in ("data-src", "data-lazy-src", "data-original", "src"):
        val = (tag.get(attr) or "").strip()
        if val and not val.startswith("data:"):
            return val
    return ""


def fetch_player_options(soup: BeautifulSoup) -> list[dict[str, str]]:
    """Lista opções do player DooPlay (data-post / data-nume / label)."""
    out: list[dict[str, str]] = []
    for el in soup.select(_PLAYER_OPTION_SEL):
        post = (el.get("data-post") or "").strip()
        nume = (el.get("data-nume") or "").strip()
        if not post or not nume:
            continue
        label = el.get_text(" ", strip=True) or nume
        out.append(
            {
                "post": post,
                "nume": nume,
                "type": (el.get("data-type") or "tv").strip() or "tv",
                "label": label,
            }
        )
    return out


def ajax_embed_url(
    base_url: str,
    *,
    post: str,
    nume: str,
    ptype: str = "tv",
    referer: str = "",
    session: requests.Session | None = None,
) -> str | None:
    """Resolve embed via admin-ajax.php (action=doo_player_ajax)."""
    ajax = urljoin(base_url.rstrip("/") + "/", "wp-admin/admin-ajax.php")
    data = {
        "action": "doo_player_ajax",
        "post": post,
        "nume": nume,
        "type": ptype or "tv",
    }
    headers = {
        **HEADERS,
        "Referer": referer or base_url,
        "X-Requested-With": "XMLHttpRequest",
        "Origin": base_url.rstrip("/"),
    }
    own = session is None
    sess = session or requests.Session()
    try:
        if own:
            sess.headers.update(HEADERS)
        resp = sess.post(ajax, data=data, headers=headers, timeout=20)
        if not validate_response(resp):
            return None
        text = (resp.text or "").strip()
        if not text:
            return None
        try:
            payload = resp.json()
        except Exception:
            try:
                payload = json.loads(text)
            except Exception:
                # às vezes devolve HTML do iframe
                m = re.search(r'src=["\'](https?://[^"\']+)["\']', text, re.I)
                return m.group(1) if m else None
        if isinstance(payload, dict):
            for key in ("embed_url", "embed", "url", "source"):
                val = payload.get(key)
                if isinstance(val, str) and val.startswith("http"):
                    return val
        return None
    except requests.RequestException as e:
        logger.debug("dooplay ajax fail: %s", e)
        return None
    finally:
        if own:
            sess.close()


def unwrap_jwplayer_source(url: str) -> str | None:
    """Extrai ?source= de páginas /jwplayer?source=…"""
    if not url:
        return None
    low = url.lower()
    if "jwplayer" not in low and "source=" not in low:
        return None
    qs = parse_qs(urlparse(url).query)
    raw = (qs.get("source") or [None])[0]
    if not raw:
        return None
    src = unquote(raw)
    # pode vir double-encoded
    if "%3A" in src or "%2F" in src:
        src = unquote(src)
    return src if src.startswith("http") else None


def option_quality_rank(label: str, stream_url: str) -> tuple:
    """Maior = melhor. Penaliza Mobile; favorece FullHD/HLS/FHD."""
    lab = (label or "").lower()
    penalty = 0
    if any(k in lab for k in ("mobile", "celular", "phone", "360", "sd only")):
        penalty = 2
    elif "sd" in lab and "hd" not in lab:
        penalty = 1
    bonus = 0
    if any(k in lab for k in ("fullhd", "full hd", "fhd", "1080", "4k")):
        bonus = 3
    elif "hls" in lab or "720" in lab or re.search(r"\bhd\b", lab):
        bonus = 2
    q = media_url_rank(stream_url, label)
    return (bonus - penalty, q[0], q[1], q[2])


def resolve_dooplay_play_context(
    episode_link: str,
    *,
    base_url: str,
    session: requests.Session | None = None,
) -> PlayContext | None:
    """Página de episódio DooPlay → melhor stream (HLS/mp4/blogger)."""
    if not is_safe_url(episode_link, allow_http=True, resolve_dns=False):
        return None

    own = session is None
    sess = session or requests.Session()
    try:
        if own:
            sess.headers.update(HEADERS)
        resp = sess.get(episode_link, headers={**HEADERS, "Referer": base_url}, timeout=20)
        if not validate_response(resp):
            return None
        soup = BeautifulSoup(resp.text, "html.parser")

        candidates: list[tuple[tuple, PlayContext]] = []

        # 1) iframe já embutido (alguns sites)
        playex = soup.find("div", class_="playex") or soup.find(id="playex")
        if playex:
            iframe = playex.find("iframe")
            if iframe:
                src = (iframe.get("src") or iframe.get("data-src") or "").strip()
                if src and is_safe_url(src, allow_http=True, resolve_dns=False):
                    ctx = _embed_to_context(src, episode_link, base_url)
                    if ctx and ctx.url:
                        candidates.append((option_quality_rank("embed", ctx.url), ctx))

        # 2) opções ajax
        for opt in fetch_player_options(soup):
            embed = ajax_embed_url(
                base_url,
                post=opt["post"],
                nume=opt["nume"],
                ptype=opt["type"],
                referer=episode_link,
                session=sess,
            )
            if not embed:
                continue
            ctx = _embed_to_context(embed, episode_link, base_url)
            if not ctx or not ctx.url:
                continue
            rank = option_quality_rank(opt["label"], ctx.url)
            candidates.append((rank, ctx))
            logger.debug(
                "dooplay opt %s → %s… rank=%s",
                opt["label"][:24],
                ctx.url[:70],
                rank,
            )

        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0], reverse=True)
        best = candidates[0][1]
        logger.info(
            "dooplay: escolhido %s… (%d opções)",
            (best.url or "")[:80],
            len(candidates),
        )
        return best
    except requests.RequestException as e:
        logger.warning("dooplay resolve fail: %s", e)
        return None
    finally:
        if own:
            sess.close()


def _embed_to_context(embed: str, page_url: str, base_url: str) -> PlayContext | None:
    if not embed:
        return None
    # jwplayer wrapper com source=m3u8/mp4
    direct = unwrap_jwplayer_source(embed)
    if direct and is_safe_url(direct, allow_http=True, resolve_dns=False):
        return PlayContext(
            url=direct,
            referer=base_url.rstrip("/") + "/",
            origin=base_url.rstrip("/"),
            is_direct=True,
            page_url=page_url,
            cache_key=direct,
        )
    if looks_like_media_url(embed) or re.search(r"\.(m3u8|mp4)(\?|$)", embed, re.I):
        return PlayContext(
            url=embed,
            referer=base_url.rstrip("/") + "/",
            origin=base_url.rstrip("/"),
            is_direct=True,
            page_url=page_url,
            cache_key=embed,
        )
    # blogger / iframe genérico
    return context_from_embed(
        embed,
        page_url=page_url,
        default_referer=base_url.rstrip("/") + "/",
        default_origin=base_url.rstrip("/"),
    )
