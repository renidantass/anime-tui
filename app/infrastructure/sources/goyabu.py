from __future__ import annotations

import base64
import re

import requests
from bs4 import BeautifulSoup

from app.domain import Anime, Episode, Season
from app.infrastructure.sources._base import AnimeSource
from app.infrastructure.sources._utils import HEADERS, validate_response, get_episode_number


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
            return ''

    def get_video_src(self, episode_link: str) -> str:
        response = requests.get(episode_link, headers=HEADERS)
        if not validate_response(response):
            return episode_link
        soup = BeautifulSoup(response.text, self.default_analyzer)
        tab = soup.find('button', class_='player-tab')
        if tab:
            encrypted = tab.get('data-blogger-url-encrypted', '')
            if encrypted:
                return self.__decode_video_url(encrypted)
        return episode_link

    def get_last_episodes(self) -> list[Episode]:
        retrieved: list[Episode] = []

        response = requests.get(f"{self.base_url}/inicio", headers=HEADERS)
        if not validate_response(response):
            return []
        soup = BeautifulSoup(response.text, self.default_analyzer)

        for article in soup.find_all('article', class_='boxEP'):
            link_el = article.find('a', href=True)
            if not link_el:
                continue
            episode_link = link_el['href']

            figure = article.find('figure', class_='thumb')
            image = figure.get('data-thumb', '') if figure else ''

            ep_type = article.find(class_='ep-type')
            ep_text = ep_type.get_text().strip() if ep_type else ''
            episode_number = get_episode_number(ep_text)

            title_el = article.find(class_='title')
            raw_title = title_el.get_text().strip() if title_el else ''

            retrieved.append(Episode(
                number=episode_number,
                title=raw_title,
                link=episode_link,
                video_src='',
                image=image,
            ))

        return retrieved

    def search_by(self, name: str) -> list[Anime]:
        retrieved: list[Anime] = []

        response = requests.get(f"{self.base_url}/search/{name}", headers=HEADERS)
        if not validate_response(response):
            return []
        soup = BeautifulSoup(response.text, self.default_analyzer)

        for article in soup.find_all('article', class_='boxAN'):
            link_el = article.find('a', href=True)
            if not link_el:
                continue
            link = link_el['href']

            img = article.find('img', class_='cover')
            image = img.get('src', '') if img else ''

            title_el = article.find(class_='title')
            raw_title = title_el.get_text().strip() if title_el else ''

            rating_el = article.find(class_='rating-poster')
            rating = rating_el.get_text().strip() if rating_el else ''

            retrieved.append(Anime(title=raw_title, rating=rating, link=link, image=image))

        return retrieved

    def get_anime_details(self, link: str) -> Anime:
        response = requests.get(link, headers=HEADERS)
        if not validate_response(response):
            return Anime(title='', rating='', link=link)
        soup = BeautifulSoup(response.text, self.default_analyzer)

        title_elem = soup.find('h1')
        title = title_elem.get_text().strip() if title_elem else link.rstrip('/').split('/')[-1]

        img = soup.find('img', class_='cover')
        image = img.get('src', '') if img else ''

        episodes: list[Episode] = []
        for article in soup.find_all('article', class_='boxEP'):
            link_el = article.find('a', href=True)
            if not link_el:
                continue
            ep_text = link_el.get_text().strip()
            ep_match = re.search(r'\d+', ep_text)
            ep_num = ep_match.group() if ep_match else '?'
            episodes.append(Episode(
                number=ep_num,
                title=ep_text,
                link=link_el['href'],
                video_src='',
            ))

        seasons = [Season(number=1, episodes=episodes)] if episodes else None

        return Anime(title=title, rating='', link=link, image=image, seasons=seasons)
