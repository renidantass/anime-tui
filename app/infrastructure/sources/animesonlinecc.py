from __future__ import annotations

import re
from urllib.parse import quote

from app.domain import Anime, Episode, PlayContext, Season
from app.infrastructure.sources._base import AnimeSource
from app.infrastructure.sources._dooplay import resolve_dooplay_play_context
from app.infrastructure.sources._utils import extract_episode_number


class AnimesOnlineCC(AnimeSource):
    name = "AnimesOnlineCC"
    identifier = "animesonlinecc"
    base_url = "https://animesonlinecc.to"
    color = "#d35400"
    has_search = True
    has_details = True

    def get_play_context(self, episode_link: str) -> PlayContext:
        ctx = resolve_dooplay_play_context(episode_link, base_url=self.base_url)
        if ctx is not None and ctx.url:
            return ctx
        return PlayContext.page(episode_link, referer=self.base_url + "/")

    def get_last_episodes(self) -> list[Episode]:
        soup = self._fetch_soup(f"{self.base_url}/episodio/")
        if not soup:
            return []

        retrieved: list[Episode] = []
        for episode in soup.find_all("article", "episodes"):
            eptitle_div = episode.find("div", "eptitle")
            if eptitle_div is None:
                continue
            title_h3 = eptitle_div.h3
            if title_h3 is None:
                continue
            raw_title = title_h3.get_text().strip()
            title_a = title_h3.a
            if title_a is None:
                continue
            episode_link = title_a["href"]
            episode_number = extract_episode_number(raw_title, episode_link)

            image = ""
            poster = episode.find("div", "poster")
            if poster is not None:
                img_tag = poster.find("img")
                if img_tag is not None:
                    image = img_tag.get("src", "")

            retrieved.append(Episode(episode_number, raw_title, episode_link, "", image=image))

        return retrieved

    def search_by(self, name: str) -> list[Anime]:
        soup = self._fetch_soup(f"{self.base_url}/?s={quote(name, safe='')}&post_type=animes")
        if not soup:
            return []

        retrieved: list[Anime] = []
        for article in soup.find_all("article", "tvshows"):
            poster = article.find("div", "poster")
            if poster is None:
                continue
            rating_div = poster.find("div", "rating")
            rating = rating_div.get_text() if rating_div else ""
            img = poster.find("img")
            image = img.get("src", "") if img else ""

            data = article.find("div", "data")
            if data is None:
                continue
            title = data.h3
            if title is None:
                continue
            link = title.a["href"] if title.a else ""
            raw_title = title.get_text().strip()

            retrieved.append(Anime(title=raw_title, rating=rating, link=link, image=image))

        return retrieved

    def get_anime_details(self, link: str) -> Anime:
        soup = self._fetch_soup(link)
        if not soup:
            return Anime(title="", rating="", link=link)

        title = self._extract_title(soup, link)
        image = self._extract_image(soup)

        seasons: list[Season] = []
        season_containers = soup.find_all("div", class_=lambda c: c and "season" in c.lower())
        if not season_containers:
            season_containers = soup.find_all(
                "ul", class_=lambda c: c and ("episod" in c.lower() or "season" in c.lower())
            )

        for i, container in enumerate(season_containers):
            header = container.find(["h2", "h3", "h4"])
            season_num = i + 1
            if header:
                match = re.search(r"\d+", header.get_text())
                if match:
                    season_num = int(match.group())

            episodes: list[Episode] = []
            for a in container.find_all("a", href=True):
                href = a["href"]
                text = a.get_text().strip()
                if not href or not text:
                    continue
                ep_num = extract_episode_number(text, href)
                episodes.append(Episode(number=ep_num, title=text, link=href, video_src=""))

            if episodes:
                seasons.append(Season(number=season_num, episodes=episodes))

        if not seasons:
            ep_list: list[Episode] = []
            for article in soup.find_all("article", class_=lambda c: c and "episod" in c.lower()):
                a = article.find("a", href=True)
                if not a:
                    continue
                href = a["href"]
                text = a.get_text().strip()
                ep_num = extract_episode_number(text, href)
                ep_list.append(Episode(number=ep_num, title=text, link=href, video_src=""))
            if ep_list:
                seasons.append(Season(number=1, episodes=ep_list))

        return Anime(
            title=title, rating="", link=link, image=image, seasons=seasons if seasons else None
        )
