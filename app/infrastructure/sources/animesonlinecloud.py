"""Fonte: AnimesOnline.cloud (tema DooPlay / WordPress)."""

from __future__ import annotations

import re
from urllib.parse import quote

from app.domain import Anime, Episode, PlayContext, Season
from app.infrastructure.security import is_safe_url
from app.infrastructure.sources._base import AnimeSource
from app.infrastructure.sources._dooplay import (
    img_src,
    resolve_dooplay_play_context,
)
from app.infrastructure.sources._utils import extract_episode_number, matches_search_tokens


class AnimesOnlineCloud(AnimeSource):
    name = "AnimesOnline.cloud"
    identifier = "animesonlinecloud"
    base_url = "https://animesonline.cloud"
    color = "#9b59b6"
    has_search = True
    has_details = True

    def get_play_context(self, episode_link: str) -> PlayContext:
        ctx = resolve_dooplay_play_context(episode_link, base_url=self.base_url)
        if ctx is not None:
            return ctx
        return PlayContext.page(episode_link, referer=self.base_url + "/")

    def get_last_episodes(self) -> list[Episode]:
        soup = self._fetch_soup(f"{self.base_url}/episodio/")
        if not soup:
            return []

        retrieved: list[Episode] = []
        for article in soup.select("article.episodes, article.item.episodes"):
            title_h3 = article.select_one(".eptitle h3, .data h3, h3")
            title_a = title_h3.find("a", href=True) if title_h3 else None
            if not title_a:
                title_a = article.find("a", href=True)
            if not title_a:
                continue
            episode_link = title_a["href"]
            if not episode_link or "/episodio" not in episode_link:
                poster_a = article.select_one(".poster a[href], .season_m a[href]")
                if poster_a:
                    episode_link = poster_a["href"]
            if not episode_link:
                continue

            ep_label = title_a.get_text(strip=True) or ""
            serie = article.select_one(".serie, .data .serie, span.serie")
            serie_name = serie.get_text(strip=True) if serie else ""
            poster = article.select_one(".poster img, img")
            alt = (poster.get("alt") if poster else "") or ""

            if serie_name and ep_label:
                raw_title = f"{serie_name} - {ep_label}"
            elif alt:
                raw_title = alt
            else:
                raw_title = ep_label or article.get_text(" ", strip=True) or episode_link

            episode_number = extract_episode_number(ep_label, raw_title, episode_link)
            image = img_src(poster)

            retrieved.append(
                Episode(
                    number=episode_number,
                    title=raw_title,
                    link=episode_link,
                    video_src="",
                    image=image,
                )
            )
        return retrieved

    def search_by(self, name: str) -> list[Anime]:
        q = (name or "").strip()
        if not q:
            return []

        soup = self._fetch_soup(f"{self.base_url}/?s={quote(q, safe='')}&post_type=animes")
        if not soup:
            soup = self._fetch_soup(f"{self.base_url}/?s={quote(q, safe='')}")
        if not soup:
            return []

        items = soup.select("article.result-item, .search-page .result-item, div.result-item")
        if not items:
            items = soup.select("article.item.tvshows, article.tvshows")
        if not items:
            items = soup.find_all("article")

        retrieved: list[Anime] = []
        seen: set[str] = set()
        for article in items:
            title_a = article.select_one(
                ".details .title a[href], .title a[href], "
                ".data h3 a[href], h3 a[href], .details a[href]"
            )
            if not title_a:
                continue
            link = title_a.get("href") or ""
            raw_title = title_a.get_text(strip=True) or ""
            if not link or not raw_title or link in seen:
                continue
            if raw_title.upper() in {"TV", "MOVIE", "OVA", "ONA", "SPECIAL"}:
                continue
            if not any(x in link for x in ("/anime/", "/filme/", "/tvshows/", "/movies/")):
                continue
            if not matches_search_tokens(q, raw_title, link):
                continue
            seen.add(link)
            img = article.find("img")
            image = img_src(img)
            rating_el = article.select_one(".rating, .meta .rating")
            rating = rating_el.get_text(strip=True) if rating_el else ""
            rating = re.sub(r"^IMDb\s*", "", rating, flags=re.I).strip()

            retrieved.append(Anime(title=raw_title, rating=rating, link=link, image=image))
        return retrieved

    def get_anime_details(self, link: str) -> Anime:
        if not is_safe_url(link, allow_http=True, resolve_dns=False):
            return Anime(title="", rating="", link=link)

        soup = self._fetch_soup(link)
        if not soup:
            return Anime(title="", rating="", link=link)

        title_elem = soup.select_one("h1, .data h1, .sheader .data h1")
        title = title_elem.get_text(strip=True) if title_elem else link.rstrip("/").split("/")[-1]
        title = re.sub(r"^(Home|Animes|Filmes)+", "", title, flags=re.I).strip() or title

        poster = soup.select_one(".poster img, .sheader .poster img, img.cover")
        image = img_src(poster)

        seasons: list[Season] = []
        season_blocks = soup.select("#seasons .se-c, .seasons .se-c, .se-c")
        for i, block in enumerate(season_blocks):
            header = block.select_one(".se-q span.title, .se-q, h2, h3")
            season_num = i + 1
            if header:
                m = re.search(r"\d+", header.get_text())
                if m:
                    season_num = int(m.group())
            episodes: list[Episode] = []
            for a in block.select("a[href*='/episodio']"):
                href = a.get("href") or ""
                text = a.get_text(strip=True)
                if not href:
                    continue
                if not text:
                    text = href.rstrip("/").split("/")[-1]
                ep_num = extract_episode_number(text, href)
                episodes.append(Episode(number=ep_num, title=text, link=href, video_src=""))
            if episodes:
                seasons.append(Season(number=season_num, episodes=episodes))

        if not seasons:
            ep_list: list[Episode] = []
            seen: set[str] = set()
            for a in soup.select("a[href*='/episodio']"):
                href = a.get("href") or ""
                if not href or href in seen:
                    continue
                seen.add(href)
                text = a.get_text(strip=True) or href
                ep_list.append(
                    Episode(
                        number=extract_episode_number(text, href),
                        title=text,
                        link=href,
                        video_src="",
                    )
                )
            if ep_list:
                seasons.append(Season(number=1, episodes=ep_list))

        return Anime(
            title=title, rating="", link=link, image=image, seasons=seasons if seasons else None
        )
