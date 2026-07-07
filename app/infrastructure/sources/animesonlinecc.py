from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from app.domain import Anime, Episode, Season
from app.infrastructure.sources._base import AnimeSource

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


class AnimesOnlineCC(AnimeSource):
    name = "AnimesOnlineCC"
    identifier = "animesonlinecc"
    base_url = "https://animesonlinecc.to"
    color = "#d35400"
    has_search = True
    has_details = True

    default_analyzer = 'lxml'

    urls = {
        "last_episodes": "https://animesonlinecc.to/episodio/",
    }

    def __get_episode_number(self, title: str) -> str:
        episode_separator = 'Episodio'
        separated_title = title.rpartition(episode_separator)
        return separated_title[-1].strip() or '0'

    def get_video_src(self, episode_link: str) -> str:
        response = requests.get(episode_link, headers=HEADERS)
        soup = BeautifulSoup(response.text, self.default_analyzer)
        playex = soup.find('div', 'playex')
        iframe = playex.iframe
        return iframe['src']

    def get_last_episodes(self) -> list[Episode]:
        retrieved: list[Episode] = []

        response = requests.get(self.urls["last_episodes"], headers=HEADERS)
        soup = BeautifulSoup(response.text, self.default_analyzer)
        episodes = soup.find_all("article", "episodes")

        for episode in episodes:
            title_element = episode.find('div', 'eptitle').h3
            raw_title = title_element.get_text().strip()
            episode_link = title_element.a['href']
            episode_number = self.__get_episode_number(raw_title)

            poster = episode.find('div', 'poster')
            image = poster.find('img')['src'] if poster and poster.find('img') else ''

            retrieved.append(Episode(episode_number, raw_title, episode_link, '', image=image))

        return retrieved

    def search_by(self, name: str) -> list[Anime]:
        retrieved: list[Anime] = []

        response = requests.get(f"{self.base_url}/?s={name}&post_type=animes", headers=HEADERS)
        soup = BeautifulSoup(response.text, self.default_analyzer)

        for article in soup.find_all("article", "tvshows"):
            poster = article.find("div", "poster")
            rating = poster.find("div", "rating").get_text()
            img = poster.find("img")
            image = img.get('src', '') if img else ''

            data = article.find("div", "data")
            title = data.h3
            link = title.a["href"]
            raw_title = title.get_text().strip()

            retrieved.append(Anime(title=raw_title, rating=rating, link=link, image=image))

        return retrieved

    def get_anime_details(self, link: str) -> Anime:
        response = requests.get(link, headers=HEADERS)
        soup = BeautifulSoup(response.text, self.default_analyzer)

        title_elem = soup.find('h1')
        title = title_elem.get_text().strip() if title_elem else link.rstrip('/').split('/')[-1]

        poster_div = soup.find('div', 'poster')
        image = poster_div.find('img')['src'] if poster_div and poster_div.find('img') else ''

        seasons: list[Season] = []

        season_containers = soup.find_all('div', class_=lambda c: c and 'season' in c.lower())
        if not season_containers:
            season_containers = soup.find_all('ul', class_=lambda c: c and ('episod' in c.lower() or 'season' in c.lower()))

        for i, container in enumerate(season_containers):
            header = container.find(['h2', 'h3', 'h4'])
            season_num = i + 1
            if header:
                match = re.search(r'\d+', header.get_text())
                if match:
                    season_num = int(match.group())

            episodes: list[Episode] = []
            for a in container.find_all('a', href=True):
                href = a['href']
                text = a.get_text().strip()
                if not href or not text:
                    continue
                ep_match = re.search(r'\d+', text)
                ep_num = ep_match.group() if ep_match else '?'
                episodes.append(Episode(number=ep_num, title=text, link=href, video_src=''))

            if episodes:
                seasons.append(Season(number=season_num, episodes=episodes))

        if not seasons:
            ep_list: list[Episode] = []
            for article in soup.find_all('article', class_=lambda c: c and 'episod' in c.lower()):
                a = article.find('a', href=True)
                if not a:
                    continue
                href = a['href']
                text = a.get_text().strip()
                ep_match = re.search(r'\d+', text)
                ep_num = ep_match.group() if ep_match else '?'
                ep_list.append(Episode(number=ep_num, title=text, link=href, video_src=''))
            if ep_list:
                seasons.append(Season(number=1, episodes=ep_list))

        return Anime(
            title=title,
            rating='',
            link=link,
            image=image,
            seasons=seasons if seasons else None,
        )
