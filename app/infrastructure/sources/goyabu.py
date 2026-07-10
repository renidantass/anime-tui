from __future__ import annotations

import base64

from app.domain import Anime, Episode, PlayContext, Season
from app.infrastructure.security import is_safe_url, quote_path_segment
from app.infrastructure.sources._base import AnimeSource
from app.infrastructure.sources._playback import context_from_embed


class Goyabu(AnimeSource):
    name = "Goyabu"
    identifier = "goyabu"
    base_url = "https://goyabu.io"
    color = "#3498db"
    has_search = True
    has_details = True

    def __decode_video_url(self, encrypted: str) -> str:
        try:
            decoded = base64.b64decode(encrypted).decode()
            return decoded[::-1]
        except Exception:
            return ""

    def get_play_context(self, episode_link: str) -> PlayContext:
        if not is_safe_url(episode_link, allow_http=True, resolve_dns=False):
            return PlayContext.page(episode_link)

        soup = self._fetch_soup(episode_link)
        if not soup:
            return PlayContext.page(episode_link)

        tab = soup.find("button", class_="player-tab")
        embed = ""
        if tab:
            encrypted = tab.get("data-blogger-url-encrypted", "")
            if encrypted:
                embed = self.__decode_video_url(encrypted)

        if embed and is_safe_url(embed, allow_http=True, resolve_dns=False):
            return context_from_embed(
                embed,
                page_url=episode_link,
                default_referer=f"{self.base_url}/",
                default_origin=self.base_url,
            )

        return PlayContext.page(episode_link, referer=f"{self.base_url}/")

    def get_last_episodes(self) -> list[Episode]:
        soup = self._fetch_soup(f"{self.base_url}/inicio")
        if not soup:
            return []

        retrieved: list[Episode] = []
        for article in soup.find_all("article", class_="boxEP"):
            link_el = article.find("a", href=True)
            if not link_el:
                continue
            episode_link = link_el["href"]

            figure = article.find("figure", class_="thumb")
            image = figure.get("data-thumb", "") if figure else ""

            ep_type = article.find(class_="ep-type")
            ep_text = ep_type.get_text().strip() if ep_type else ""
            title_el = article.find(class_="title")
            raw_title = title_el.get_text().strip() if title_el else ""
            episode_number = self._resolve_episode_number(ep_text, raw_title, episode_link)

            retrieved.append(
                Episode(
                    number=episode_number,
                    title=raw_title or ep_text,
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
        for article in soup.find_all("article", class_="boxAN"):
            link_el = article.find("a", href=True)
            if not link_el:
                continue
            link = link_el["href"]

            img = article.find("img", class_="cover")
            image = img.get("src", "") if img else ""

            title_el = article.find(class_="title")
            raw_title = title_el.get_text().strip() if title_el else ""

            rating_el = article.find(class_="rating-poster")
            rating = rating_el.get_text().strip() if rating_el else ""

            retrieved.append(Anime(title=raw_title, rating=rating, link=link, image=image))

        return retrieved

    def get_anime_details(self, link: str) -> Anime:
        soup = self._fetch_soup(link)
        if not soup:
            return Anime(title="", rating="", link=link)

        title = self._extract_title(soup, link)
        image = self._extract_image(soup)

        episodes: list[Episode] = []
        for article in soup.find_all("article", class_="boxEP"):
            link_el = article.find("a", href=True)
            if not link_el:
                continue
            ep_text = link_el.get_text().strip()
            href = link_el["href"]
            ep_num = self._resolve_episode_number(ep_text, "", href)
            episodes.append(Episode(number=ep_num, title=ep_text, link=href, video_src=""))

        if not episodes:
            for a in soup.select('a[href*="/episodio/"]'):
                text = a.get_text().strip()
                if not text:
                    continue
                href = a.get("href", "")
                ep_num = self._resolve_episode_number(text, "", href)
                if href:
                    episodes.append(Episode(number=ep_num, title=text, link=href, video_src=""))

        seasons = [Season(number=1, episodes=episodes)] if episodes else None
        return Anime(title=title, rating="", link=link, image=image, seasons=seasons)
