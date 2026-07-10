"""Fonte: Anime Yabu (animeyabu.net).

Stream: URLs R2 precisam de assinatura via ads.animeyabu.net
(POST com outbrain.js → token → query AWS/S3).
"""

from __future__ import annotations

import logging
import re
import threading
import time
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from app.domain import Anime, Episode, PlayContext, Season
from app.infrastructure.security import is_safe_url
from app.infrastructure.sources._base import AnimeSource
from app.infrastructure.sources._utils import (
    HEADERS,
    extract_episode_number,
    is_unknown_episode_number,
    matches_search_tokens,
    normalize_watch_titles,
    strip_title_variants,
    validate_response,
)

logger = logging.getLogger(__name__)

_VID_RE = re.compile(
    r"""var\s+vid\s*=\s*['"](https?://[^'"]+\.mp4[^'"]*)['"]""",
    re.I,
)
_YABU_EP_IN_TITLE = re.compile(
    r"\s+ep\s*[#.:]?\s*\d{1,4}(?:\s+final)?\s*$",
    re.I,
)
_VIDEO_ID_RE = re.compile(r"/videos/(\d+)", re.I)

_ADS_URL = "https://ads.animeyabu.net"
_OUTBRAIN_URL = "https://widgets.outbrain.com/outbrain.js"

# cache de outbrain.js (corpo grande; reutiliza por alguns minutos)
_ob_lock = threading.Lock()
_ob_body: str = ""
_ob_expires: float = 0.0
_OB_TTL = 600.0  # 10 min


class AnimeYabu(AnimeSource):
    name = "Anime Yabu"
    identifier = "animeyabu"
    base_url = "https://www.animeyabu.net"
    color = "#e74c3c"
    has_search = True
    has_details = True

    def _abs(self, href: str) -> str:
        return urljoin(self.base_url + "/", href or "")

    @staticmethod
    def _video_id(link: str) -> str:
        m = _VIDEO_ID_RE.search(link or "")
        return m.group(1) if m else ""

    def _thumb_from_img_tag(self, img_tag) -> str:
        """URL exata que o site usa no HTML (não reescrever para default.webp)."""
        if img_tag is None:
            return ""
        for attr in ("src", "data-src", "data-lazy-src", "data-original"):
            raw = (img_tag.get(attr) or "").strip()
            if raw and not raw.startswith("data:"):
                return self._abs(raw)
        # srcset: "url 1x, url2 2x"
        srcset = (img_tag.get("srcset") or "").strip()
        if srcset:
            first = srcset.split(",")[0].strip().split()[0]
            if first.startswith("http") or first.startswith("/"):
                return self._abs(first)
        return ""

    def _thumb_candidates(self, video_id: str) -> list[str]:
        if not video_id:
            return []
        base = f"{self.base_url}/media/videos/tmb/{video_id}"
        # Ordem do site + og:image (default.jpg). Evita default.webp minúsculo/quebrado.
        return [
            f"{base}/1.jpg",
            f"{base}/default.jpg",
            f"{base}/default.webp",
            f"{base}/2.jpg",
            f"{base}/3.jpg",
        ]

    def _url_looks_like_image(self, url: str, session: requests.Session | None = None) -> bool:
        """Valida que a URL responde como imagem de verdade (não HTML 404)."""
        if not url or not is_safe_url(url, allow_http=True, resolve_dns=False):
            return False
        sess = session or requests
        headers = {
            **HEADERS,
            "Referer": self.base_url + "/",
            "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
            "Range": "bytes=0-2047",
        }
        try:
            r = sess.get(url, headers=headers, timeout=6, stream=True, allow_redirects=True)
            try:
                if r.status_code not in (200, 206):
                    return False
                ct = (r.headers.get("Content-Type") or "").lower()
                if "text/html" in ct:
                    return False
                chunk = next(r.iter_content(32), b"")
                if len(chunk) < 16:
                    return False
                if chunk[:3] == b"\xff\xd8\xff":
                    return True
                if chunk[:8] == b"\x89PNG\r\n\x1a\n":
                    return True
                if chunk[:4] == b"RIFF" and b"WEBP" in chunk[:16]:
                    # webp minúsculo (~1KB) costuma ser placeholder ruim
                    cl = r.headers.get("Content-Length")
                    if cl and cl.isdigit() and int(cl) < 1500:
                        return False
                    return True
                if ct.startswith("image/"):
                    return True
                return False
            finally:
                r.close()
        except requests.RequestException:
            return False

    def _thumb_url(
        self,
        video_id: str,
        img_tag=None,
        *,
        session: requests.Session | None = None,
        prefer_site_src: bool = True,
    ) -> str:
        """Escolhe a melhor capa disponível para o episódio.

        1) src real do HTML da home (o que o Yabu mostra)
        2) candidatos 1.jpg → default.jpg → default.webp (validados)
        """
        # 1) src real do HTML — é o frame que o Yabu mostra no card
        if prefer_site_src:
            from_tag = self._thumb_from_img_tag(img_tag)
            if from_tag:
                return from_tag
        # 2) fallbacks validados (quando não há img no HTML ou src vazio)
        for cand in self._thumb_candidates(video_id):
            if self._url_looks_like_image(cand, session=session):
                return cand
        cands = self._thumb_candidates(video_id)
        return cands[0] if cands else ""

    @staticmethod
    def _series_title(raw_title: str, ep_text: str = "", number: str = "") -> str:
        t = (raw_title or "").strip()
        t = _YABU_EP_IN_TITLE.sub("", t).strip()
        anime, _, _ = normalize_watch_titles(t, ep_text or t, number or "")
        anime = strip_title_variants(anime or t)
        anime = re.sub(r"\s*[\-–—:|]\s*$", "", anime).strip()
        return anime or t

    @staticmethod
    def _series_key(series_title: str) -> str:
        t = strip_title_variants(series_title or "")
        t = re.sub(r"\s+", " ", t.lower().strip())
        return t

    @staticmethod
    def _quality_rank(url: str) -> int:
        low = (url or "").lower()
        if "/fful/" in low or "/full/" in low:
            return 300
        if "/f333/" in low or "/720/" in low:
            return 200
        if "iphone" in low or "/fiphone" in low or "/mobile" in low:
            return 50
        return 100

    def _outbrain_body(self, session: requests.Session) -> str:
        global _ob_body, _ob_expires
        now = time.monotonic()
        with _ob_lock:
            if _ob_body and now < _ob_expires:
                return _ob_body
        try:
            r = session.get(_OUTBRAIN_URL, timeout=25)
            r.raise_for_status()
            body = r.text or ""
        except requests.RequestException as e:
            logger.warning("AnimeYabu: falha outbrain.js: %s", e)
            body = "x"  # tenta mesmo assim (pode vir BLOQUEADO)
        with _ob_lock:
            _ob_body = body
            _ob_expires = time.monotonic() + _OB_TTL
        return body

    def _sign_video_url(
        self,
        raw_mp4: str,
        *,
        page_url: str,
        session: requests.Session,
    ) -> str | None:
        """Obtém query assinado (R2/S3) para o MP4 do Yabu."""
        if not raw_mp4:
            return None
        try:
            ad_body = self._outbrain_body(session)
            post_headers = {
                **HEADERS,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": self.base_url,
                "Referer": page_url or self.base_url + "/",
            }
            r1 = None
            for attempt in range(3):
                r1 = session.post(
                    _ADS_URL,
                    data={
                        "category": "client",
                        "type": "premium",
                        "ad": ad_body,
                    },
                    headers=post_headers,
                    timeout=25,
                )
                # 5xx/520 do Cloudflare: tenta de novo
                if r1.status_code in (200, 201) or r1.status_code < 500:
                    break
                time.sleep(0.4 * (attempt + 1))
            if r1 is None or not validate_response(r1):
                logger.warning(
                    "AnimeYabu ads step1 HTTP %s",
                    getattr(r1, "status_code", "?"),
                )
                return None
            try:
                payload = r1.json()
            except Exception:
                payload = None
            if isinstance(payload, dict):
                payload = [payload]
            if not isinstance(payload, list) or not payload:
                logger.warning("AnimeYabu ads step1 payload inválido: %s", r1.text[:120])
                return None
            token = (payload[0] or {}).get("publicidade") or ""
            if not token or (payload[0] or {}).get("ads") == "BLOQUEADO":
                logger.warning("AnimeYabu ads step1 bloqueado/sem token: %s", r1.text[:160])
                return None

            # JS do site concatena token cru (pode começar com ?)
            r2 = None
            for attempt in range(3):
                r2 = session.get(
                    _ADS_URL,
                    params={"token": token, "url": raw_mp4},
                    headers={
                        **HEADERS,
                        "X-Requested-With": "XMLHttpRequest",
                        "Origin": self.base_url,
                        "Referer": page_url or self.base_url + "/",
                    },
                    timeout=25,
                )
                if r2.status_code in (200, 201) or r2.status_code < 500:
                    break
                time.sleep(0.4 * (attempt + 1))
            if r2 is None or not validate_response(r2):
                logger.warning(
                    "AnimeYabu ads step2 HTTP %s",
                    getattr(r2, "status_code", "?"),
                )
                return None
            try:
                payload2 = r2.json()
            except Exception:
                payload2 = None
            if isinstance(payload2, dict):
                payload2 = [payload2]
            if not isinstance(payload2, list) or not payload2:
                return None
            sig = (payload2[0] or {}).get("publicidade") or ""
            if not sig:
                return None
            if sig.startswith("?"):
                signed = raw_mp4 + sig
            elif sig.startswith("&"):
                signed = raw_mp4 + ("?" + sig[1:] if "?" not in raw_mp4 else sig)
            elif "=" in sig:
                signed = raw_mp4 + ("&" if "?" in raw_mp4 else "?") + sig
            else:
                signed = raw_mp4 + sig
            return signed
        except requests.RequestException as e:
            logger.warning("AnimeYabu sign fail: %s", e)
            return None

    def _probe_mp4(self, url: str, *, referer: str, session: requests.Session) -> bool:
        try:
            r = session.get(
                url,
                headers={
                    **HEADERS,
                    "Referer": referer,
                    "Range": "bytes=0-1023",
                    "Origin": self.base_url,
                },
                timeout=15,
                stream=True,
            )
            try:
                if r.status_code not in (200, 206):
                    return False
                chunk = next(r.iter_content(64), b"")
                return bool(chunk) and (
                    b"ftyp" in chunk[:64] or chunk[:4] == b"\x00\x00\x00"
                )
            finally:
                r.close()
        except requests.RequestException:
            return False

    def get_play_context(self, episode_link: str) -> PlayContext:
        if not is_safe_url(episode_link, allow_http=True, resolve_dns=False):
            return PlayContext.page(episode_link)

        session = requests.Session()
        session.headers.update(HEADERS)
        try:
            response = session.get(
                episode_link,
                headers={**HEADERS, "Referer": self.base_url + "/"},
                timeout=20,
            )
            if not validate_response(response):
                return PlayContext.page(episode_link, referer=self.base_url + "/")

            raw_urls = list(dict.fromkeys(_VID_RE.findall(response.text)))
            # maior qualidade primeiro
            raw_urls.sort(key=self._quality_rank, reverse=True)
            if not raw_urls:
                logger.warning("AnimeYabu: nenhum vid= no HTML de %s", episode_link)
                return PlayContext.page(episode_link, referer=self.base_url + "/")

            for raw in raw_urls:
                if not is_safe_url(raw, allow_http=True, resolve_dns=False):
                    continue
                signed = self._sign_video_url(
                    raw, page_url=episode_link, session=session
                )
                if not signed:
                    continue
                if not is_safe_url(signed, allow_http=True, resolve_dns=False):
                    continue
                if not self._probe_mp4(
                    signed, referer=episode_link, session=session
                ):
                    logger.debug("AnimeYabu: signed URL não playable %s…", signed[:80])
                    continue
                logger.info(
                    "AnimeYabu: stream assinado ok (%s) %s…",
                    "fful"
                    if "/fful/" in raw
                    else "f333"
                    if "/f333/" in raw
                    else "other",
                    signed[:90],
                )
                return PlayContext(
                    url=signed,
                    referer=episode_link,
                    origin=self.base_url,
                    is_direct=True,
                    page_url=episode_link,
                    cache_key=raw,  # cache por URL base (assinatura expira)
                )

            # última tentativa: página no browser
            return PlayContext.page(episode_link, referer=self.base_url + "/")
        finally:
            session.close()

    def get_last_episodes(self) -> list[Episode]:
        """Últimos eps da home — **1 por anime** (Yabu relista vários eps da mesma obra)."""
        retrieved: list[Episode] = []
        session = requests.Session()
        session.headers.update(HEADERS)
        try:
            soup = self._fetch_soup(self.base_url + "/", session=session)
            if not soup:
                return []

            seen_series: set[str] = set()
            seen_links: set[str] = set()

            for item in soup.select(".ultimosEpisodiosHomeItem"):
                a = item.find("a", href=True)
                if not a:
                    continue
                link = self._abs(a["href"])
                if "/videos/" not in link or link in seen_links:
                    continue
                seen_links.add(link)

                name_el = item.select_one(
                    ".ultimosEpisodiosHomeItemInfosNome h1, "
                    ".ultimosEpisodiosHomeItemInfosNome"
                )
                num_el = item.select_one(".ultimosEpisodiosHomeItemInfosNum")
                raw_title = (
                    (name_el.get_text(strip=True) if name_el else "")
                    or a.get("title")
                    or ""
                )
                ep_text = num_el.get_text(strip=True) if num_el else ""
                number = extract_episode_number(ep_text, raw_title, link)
                if is_unknown_episode_number(number):
                    number = extract_episode_number(raw_title, link)

                series = self._series_title(raw_title, ep_text, number)
                skey = self._series_key(series)
                if not skey or skey in seen_series:
                    continue
                seen_series.add(skey)

                if number and not is_unknown_episode_number(number):
                    title = f"{series} - Episódio {number}"
                else:
                    title = series or raw_title or ep_text or link

                vid = self._video_id(link)
                # usa a mesma thumb do card do site (1.jpg), com fallback validado
                image = self._thumb_url(
                    vid, item.find("img"), session=session, prefer_site_src=True
                )
                date_el = item.select_one(".lancaster_episodio_info_data")
                date = date_el.get_text(strip=True) if date_el else ""

                retrieved.append(
                    Episode(
                        number=number if not is_unknown_episode_number(number) else "",
                        title=title,
                        link=link,
                        video_src="",
                        image=image,
                        date=date,
                    )
                )
            return retrieved
        finally:
            session.close()

    def search_by(self, name: str) -> list[Anime]:
        q = (name or "").strip()
        if not q:
            return []

        soup = self._fetch_soup(f"{self.base_url}/?s={quote(q, safe='')}")
        if not soup:
            return []

        seen: set[str] = set()
        retrieved: list[Anime] = []

        anchors = soup.select(
            ".FsssItem a[href*='/animes/'], .search a[href*='/animes/']"
        )
        if not anchors:
            anchors = soup.select("a[href*='/animes/']")

        for a in anchors:
            href = self._abs(a.get("href") or "")
            if not href or href in seen:
                continue
            if "/animes/letra" in href or href.rstrip("/").endswith("/animes"):
                continue
            title = a.get_text(" ", strip=True)
            title = re.split(
                r"\banime\b|\bEpis[oó]dio\b|\bep\s*\d",
                title,
                maxsplit=1,
                flags=re.I,
            )[0].strip()
            if not title or len(title) < 2:
                continue
            if not matches_search_tokens(q, title, href):
                continue
            seen.add(href)
            parent = a.find_parent(["div", "article", "li"])
            img = a.find("img") or (parent.find("img") if parent else None)
            image = ""
            if img:
                for attr in ("data-src", "data-lazy-src", "src"):
                    raw = (img.get(attr) or "").strip()
                    if raw and not raw.startswith("data:"):
                        image = self._abs(raw)
                        break
            retrieved.append(Anime(title=title, rating="", link=href, image=image))

        return retrieved

    def get_anime_details(self, link: str) -> Anime:
        if not is_safe_url(link, allow_http=True, resolve_dns=False):
            return Anime(title="", rating="", link=link)

        soup = self._fetch_soup(link)
        if not soup:
            return Anime(title="", rating="", link=link)

        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else link.rstrip("/").split("/")[-1]

        image = ""
        for img in soup.find_all("img"):
            src = ""
            for attr in ("data-src", "data-lazy-src", "src"):
                raw = (img.get(attr) or "").strip()
                if raw and not raw.startswith("data:"):
                    src = raw
                    break
            if not src or "logo" in src.lower():
                continue
            if "/media/" in src or "categories" in src or "tmb" in src:
                image = self._abs(src)
                break
        if not image:
            og = soup.find("meta", property="og:image")
            if og and og.get("content"):
                image = og["content"]

        episodes: list[Episode] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = self._abs(a["href"])
            if "/videos/" not in href or href in seen:
                continue
            seen.add(href)
            text = a.get_text(" ", strip=True)
            text = re.sub(r"\d{2}/\d{2}/\d{4}.*$", "", text).strip()
            if not text:
                text = f"Ep {extract_episode_number(href)}"
            vid = self._video_id(href)
            # na ficha, prefira 1.jpg (frame do ep); não reescrever p/ webp
            image = ""
            if vid:
                image = f"{self.base_url}/media/videos/tmb/{vid}/1.jpg"
            episodes.append(
                Episode(
                    number=extract_episode_number(text, href),
                    title=text,
                    link=href,
                    video_src="",
                    image=image,
                )
            )

        seasons = [Season(number=1, episodes=episodes)] if episodes else None
        return Anime(
            title=title,
            rating="",
            link=link,
            image=image,
            seasons=seasons,
        )
