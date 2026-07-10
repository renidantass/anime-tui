from __future__ import annotations

import logging
import re
import socket
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup

from app.domain import Anime, Episode, PlayContext, Season
from app.infrastructure.security import is_safe_url, quote_path_segment
from app.infrastructure.sources._base import AnimeSource
from app.infrastructure.sources._utils import HEADERS, get_episode_number, validate_response
from app.infrastructure.stream_quality import (
    height_from_url,
    media_url_rank,
    pick_best_labeled,
    pick_best_url,
)

logger = logging.getLogger(__name__)

# JW Player: sources: [{"file":"URL", "label":"720p", ...}]
_JW_FILE_RE = re.compile(
    r'["\']file["\']\s*:\s*["\'](https?://[^"\']+)["\']',
    re.IGNORECASE,
)
# objeto source JW com file:"url" (aspas opcionais na chave; label no mesmo objeto)
_JW_SOURCE_OBJ_RE = re.compile(
    r'\{[^{}]*?["\']?file["\']?\s*:\s*["\'](https?://[^"\']+)["\'][^{}]*?\}',
    re.IGNORECASE | re.DOTALL,
)
_JW_LABEL_IN_OBJ = re.compile(
    r'["\']?label["\']?\s*:\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_MEDIA_URL_RE = re.compile(
    r'https?://[^\s"\'<>]+?\.(?:m3u8|mp4)/?(?:\?[^\s"\'<>]*)?',
    re.IGNORECASE,
)


class Topanimes(AnimeSource):
    name = "Topanimes"
    identifier = "topanimes"
    base_url = "https://topanimes.net"
    color = "#1e8449"
    has_search = True
    has_details = True

    def get_play_context(self, episode_link: str) -> PlayContext:
        """Extrai stream direto (mp4/m3u8) + headers anti-leech do CDN escolhido.

        Preferência: MP4 do incvideo (Ruplay/csst). Evita 1a-1791.com e HLS
        OdaCDN (segmentos fake). O *referer* fica no PlayContext — o player
        não precisa conhecer hosts desta fonte.
        """
        if not is_safe_url(episode_link, allow_http=True, resolve_dns=False):
            return PlayContext.page(episode_link)

        response = requests.get(episode_link, headers=HEADERS, timeout=20)
        if not validate_response(response):
            return PlayContext.page(episode_link)

        soup = BeautifulSoup(response.text, self.default_analyzer)
        candidates = self._collect_iframe_srcs(soup)
        if not candidates:
            logger.warning("Topanimes: nenhum iframe em %s", episode_link)
            return PlayContext.page(episode_link, referer=episode_link)

        candidates = sorted(candidates, key=self._iframe_priority)

        session = requests.Session()
        session.headers.update(HEADERS)
        session.headers["Referer"] = episode_link

        # rank maior = melhor (qualidade + tipo). Avalia todos os players
        # playable para não ficar no 360p se o 1080p está em outro iframe.
        best: tuple[tuple, str, str] | None = None

        for src in candidates:
            try:
                resolved = self._resolve_player_src(src, session=session, referer=episode_link)
            except Exception as e:
                logger.debug("Topanimes: falha em %s: %s", src[:80], e)
                continue
            if not resolved:
                continue

            resolved = resolved.rstrip("/")
            if not is_safe_url(resolved, allow_http=True, resolve_dns=False):
                continue
            if not self._host_resolves(resolved):
                logger.debug("Topanimes: host sem DNS %s", urlparse(resolved).hostname)
                continue

            probe_ref = self._probe_referer_for(src, resolved, episode_link)
            playable = self._stream_looks_playable(resolved, session=session, referer=probe_ref)
            if not playable:
                logger.debug("Topanimes: stream duvidoso %s…", resolved[:60])
                continue

            # iframe priority (menor = CDN mais confiável) + qualidade do arquivo
            iframe_bonus = max(0, 10 - self._iframe_priority(src))
            q = media_url_rank(resolved)
            rank = (q[0], iframe_bonus, q[1], q[2], q[3])

            if best is None or rank > best[0]:
                best = (rank, resolved, probe_ref)
                logger.debug(
                    "Topanimes: candidato ~%sp rank=%s %s…",
                    height_from_url(resolved) or "?",
                    rank,
                    resolved[:70],
                )

        if best:
            rank, stream_url, best_ref = best
            logger.info(
                "Topanimes: melhor stream ~%sp %s…",
                height_from_url(stream_url) or "?",
                stream_url[:80],
            )
            return PlayContext(
                url=stream_url,
                referer=best_ref,
                origin=self.base_url,
                is_direct=True,
                page_url=episode_link,
                cache_key=stream_url,
            )
        return PlayContext.page(episode_link, referer=episode_link)

    @staticmethod
    def _host_resolves(url: str) -> bool:
        host = urlparse(url).hostname
        if not host:
            return False
        try:
            socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            return True
        except OSError:
            return False

    @staticmethod
    def _iframe_priority(src: str) -> int:
        s = src.lower()
        # Ruplay / csst → incvideo (estável)
        if "csst.online" in s or "incvideo" in s:
            return 0
        if "/aviso/" in s:
            return 1
        if "alibabacdn" in s or "sk-ru." in s:
            return 2  # 1a-1791 costuma falhar DNS
        if "antivirus" in s:
            return 4  # HLS fake
        return 3

    @staticmethod
    def _probe_referer_for(iframe_src: str, stream_url: str, episode_link: str) -> str:
        low_i = iframe_src.lower()
        low_s = stream_url.lower()
        if "incvideo" in low_s or "csst.online" in low_i:
            return "https://www.incvideo1.online/"
        if "alibabacdn" in low_i or "sk-ru." in low_i or "1a-1791" in low_s:
            return "https://sk-ru.alibabacdn.net/"
        if "antivirus" in low_i or "b-cdn.net" in low_s:
            return "https://topanimes.net/"
        return episode_link

    def _stream_looks_playable(
        self,
        url: str,
        *,
        session: requests.Session,
        referer: str,
    ) -> bool:
        """Filtra 403/HTML e HLS falso (segmentos image/png)."""
        try:
            resp = session.get(
                url,
                headers={
                    "Referer": referer,
                    "Range": "bytes=0-2047",
                    "Origin": "https://topanimes.net",
                },
                timeout=15,
                stream=True,
                allow_redirects=True,
            )
            try:
                if resp.status_code not in (200, 206):
                    return False
                ctype = (resp.headers.get("content-type") or "").lower()
                if "text/html" in ctype:
                    return False

                if ".m3u8" in url.lower() or "mpegurl" in ctype or "x-mpegurl" in ctype:
                    body = b"".join(resp.iter_content(8192))
                    if not body.lstrip().startswith(b"#EXT"):
                        return False
                    return self._hls_segments_are_video(
                        body.decode("utf-8", errors="replace"),
                        session=session,
                        referer=referer,
                    )

                # mp4 / octet-stream
                chunk = next(resp.iter_content(64), b"")
                if b"ftyp" in chunk:
                    return True
                # alguns CDNs devolvem 200 sem range; ainda pode ser mp4
                return (
                    resp.status_code in (200, 206) and len(chunk) > 0 and not chunk.startswith(b"<")
                )
            finally:
                resp.close()
        except requests.RequestException:
            return False

    @staticmethod
    def _hls_segments_are_video(
        playlist: str,
        *,
        session: requests.Session,
        referer: str,
    ) -> bool:
        """Descarta playlists cujos 'segmentos' são PNG/HTML (anti-hotlink)."""
        first_uri = None
        for line in playlist.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                first_uri = line
                break
        if not first_uri:
            return False
        # hosts conhecidos de isca
        if "qooglecdn.com" in first_uri:
            return False
        try:
            r = session.get(
                first_uri,
                headers={"Referer": referer, "Range": "bytes=0-512"},
                timeout=12,
                stream=True,
            )
            try:
                if r.status_code not in (200, 206):
                    return False
                ct = (r.headers.get("content-type") or "").lower()
                if ct.startswith("image/") or "text/html" in ct:
                    return False
                chunk = next(r.iter_content(32), b"")
                # PNG magic / HTML
                if chunk.startswith(b"\x89PNG") or chunk.startswith(b"<"):
                    return False
                return True
            finally:
                r.close()
        except requests.RequestException:
            return False

    @staticmethod
    def _collect_iframe_srcs(soup: BeautifulSoup) -> list[str]:
        srcs: list[str] = []
        seen: set[str] = set()

        # players dooplay (ordem das abas OdaCDN, Ruplay, …)
        roots = soup.select(
            ".dooplay_player iframe, #dooplay_player_content iframe, iframe.metaframe"
        )
        if not roots:
            roots = soup.find_all("iframe")

        for iframe in roots:
            src = (iframe.get("src") or iframe.get("data-src") or "").strip()
            if not src or src in seen or src.startswith("about:"):
                continue
            seen.add(src)
            srcs.append(src)
        return srcs

    def _resolve_player_src(
        self,
        src: str,
        *,
        session: requests.Session,
        referer: str,
    ) -> str | None:
        """Converte URL de iframe em stream direto, se possível."""
        if not src:
            return None

        # já é mídia
        if re.search(r"\.(m3u8|mp4)(\?|$)", src, re.I):
            # antivirus2/?id=path/to/file.m3u8 — precisa da página que assina o token
            if "antivirus" in src or "alibabacdn" in src or "playervideo" in src:
                return self._extract_from_player_page(src, session=session, referer=referer)
            return src

        # wrapper aviso/?url=ENCODED
        if "/aviso/" in src or "url=" in src:
            nested = self._unwrap_aviso(src)
            if nested and nested != src:
                return self._resolve_player_src(nested, session=session, referer=referer)

        # players JW embutidos (antivirus2, sk-ru.alibabacdn, …)
        if any(
            k in src
            for k in (
                "antivirus",
                "alibabacdn",
                "playervideo",
                "sk-ru.",
                "cdn.net",
            )
        ) or src.startswith(self.base_url):
            return self._extract_from_player_page(src, session=session, referer=referer)

        # embed externo — devolve como está (mpv/VLC às vezes resolvem)
        if src.startswith("http"):
            media = self._extract_from_player_page(src, session=session, referer=referer)
            return media or src
        return None

    @staticmethod
    def _unwrap_aviso(src: str) -> str | None:
        qs = parse_qs(urlparse(src).query)
        raw = (qs.get("url") or [None])[0]
        if not raw:
            return None
        # pode vir duplamente encoded e com & como %26
        url = unquote(unquote(raw))
        return url if url.startswith("http") else None

    def _extract_from_player_page(
        self,
        page_url: str,
        *,
        session: requests.Session,
        referer: str,
    ) -> str | None:
        if not is_safe_url(page_url, allow_http=True, resolve_dns=True):
            return None
        try:
            resp = session.get(
                page_url,
                headers={"Referer": referer},
                timeout=20,
            )
        except requests.RequestException as e:
            logger.debug("Topanimes player page fail: %s", e)
            return None
        if not validate_response(resp):
            return None

        text = resp.text

        def _clean(u: str) -> str:
            return u.replace("\\/", "/").rstrip("/")

        # 1) objetos JW com label de qualidade (Alibaba, Ruplay, etc.)
        labeled: list[tuple[str, str]] = []
        for m in _JW_SOURCE_OBJ_RE.finditer(text):
            url = _clean(m.group(1))
            if not url.startswith("http"):
                continue
            obj = m.group(0)
            lm = _JW_LABEL_IN_OBJ.search(obj)
            label = (lm.group(1) if lm else "") or ""
            labeled.append((url, label))

        if labeled:
            best = pick_best_labeled(labeled)
            if best:
                logger.info(
                    "Topanimes JW: %d source(s) → ~%sp %s…",
                    len(labeled),
                    height_from_url(best) or height_from_url(labeled[0][0]) or "?",
                    best[:80],
                )
                return best

        # 2) só "file":"url" sem label
        files = [_clean(u) for u in _JW_FILE_RE.findall(text)]
        if files:
            best = pick_best_url(files)
            if best:
                return best

        # 3) qualquer mp4/m3u8 no HTML
        media = [_clean(u) for u in _MEDIA_URL_RE.findall(text)]
        if media:
            return pick_best_url(media)

        return None

    def get_last_episodes(self) -> list[Episode]:
        soup = self._fetch_soup(self.base_url)
        if not soup:
            return []

        retrieved: list[Episode] = []
        for article in soup.find_all("article", class_="episodes"):
            poster = article.find("div", "poster")
            if not poster:
                continue

            link_el = poster.find("a", href=True)
            if not link_el:
                continue
            episode_link = link_el["href"]

            picture = poster.find("picture")
            image = ""
            if picture:
                img = picture.find("img")
                if img:
                    image = img.get("src", "")

            data_div = article.find("div", "data")
            title_text = ""
            episode_number = "?"
            if data_div:
                strong = data_div.find("strong")
                if strong:
                    title_text = strong.get_text().strip()
                h3 = data_div.find("h3")
                ep_text = h3.get_text().strip() if h3 else ""
                if ep_text:
                    title_text = f"{title_text} - {ep_text}".strip(" -")
                episode_number = get_episode_number(ep_text, title_text, episode_link)
            if episode_number in {"?", "0"}:
                episode_number = get_episode_number(title_text, episode_link)

            retrieved.append(
                Episode(
                    number=episode_number,
                    title=title_text,
                    link=episode_link,
                    video_src="",
                    image=image,
                )
            )

        return retrieved

    def search_by(self, name: str) -> list[Anime]:
        soup = self._fetch_soup(f"{self.base_url}/search/{quote_path_segment(name)}")
        if not soup:
            return []

        retrieved: list[Anime] = []
        for article in soup.find_all("article"):
            div_img = article.find("div", class_="image")
            if not div_img:
                continue

            link_el = div_img.find("a", href=True)
            if not link_el:
                continue
            link = link_el["href"]

            img = div_img.find("img")
            image = img.get("src", "") if img else ""
            raw_title = img.get("alt", "") if img else ""

            retrieved.append(Anime(title=raw_title, rating="", link=link, image=image))

        return retrieved

    def get_anime_details(self, link: str) -> Anime:
        soup = self._fetch_soup(link)
        if not soup:
            return Anime(title="", rating="", link=link)

        title = self._extract_title(soup, link)

        img = soup.find("img", class_=lambda c: c and "poster" in c.lower() if c else False)
        if not img:
            img = soup.find("img", src=True)
        image = ""
        if img:
            image = img.get("src", "")

        seasons: list[Season] = []
        for ul in soup.find_all("ul", class_="episodios"):
            season_num = len(seasons) + 1
            episodes: list[Episode] = []
            for li in ul.find_all("li"):
                ep_title_div = li.find(class_="episodiotitle")
                if not ep_title_div:
                    continue
                a = ep_title_div.find("a", href=True)
                if not a:
                    continue
                ep_text = a.get_text().strip()
                href = a["href"]
                ep_num = get_episode_number(ep_text, href)
                episodes.append(
                    Episode(
                        number=ep_num,
                        title=ep_text,
                        link=href,
                        video_src="",
                    )
                )
            if episodes:
                seasons.append(Season(number=season_num, episodes=episodes))

        return Anime(
            title=title,
            rating="",
            link=link,
            image=image,
            seasons=seasons if seasons else None,
        )
