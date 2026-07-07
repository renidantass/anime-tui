from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from app.domain import Anime, Episode, Season
from app.infrastructure.sources._base import AnimeSource


class Topanimes(AnimeSource):
    name = "Topanimes"
    identifier = "topanimes"
    base_url = "https://topanimes.net"
    color = "#1e8449"
    has_search = True
    has_details = True

    default_analyzer = 'lxml'

    def __get_episode_number(self, title: str) -> str:
        match = re.search(r'Episódio\s*(\d+)', title, re.IGNORECASE)
        return match.group(1) if match else '0'

    def get_video_src(self, episode_link: str) -> str:
        return episode_link

    def get_last_episodes(self) -> list[Episode]:
        retrieved: list[Episode] = []

        response = requests.get(self.base_url)
        soup = BeautifulSoup(response.text, self.default_analyzer)

        for article in soup.find_all('article', class_='episodes'):
            poster = article.find('div', 'poster')
            if not poster:
                continue

            link_el = poster.find('a', href=True)
            if not link_el:
                continue
            episode_link = link_el['href']

            picture = poster.find('picture')
            image = ''
            if picture:
                img = picture.find('img')
                if img:
                    image = img.get('src', '')

            data_div = article.find('div', 'data')
            title_text = ''
            episode_number = '0'
            if data_div:
                strong = data_div.find('strong')
                if strong:
                    title_text = strong.get_text().strip()
                h3 = data_div.find('h3')
                if h3:
                    ep_text = h3.get_text().strip()
                    episode_number = self.__get_episode_number(ep_text)
                    title_text = f"{title_text} - {ep_text}"

            retrieved.append(Episode(
                number=episode_number,
                title=title_text,
                link=episode_link,
                video_src='',
                image=image,
            ))

        return retrieved

    def search_by(self, name: str) -> list[Anime]:
        retrieved: list[Anime] = []

        response = requests.get(f"{self.base_url}/search/{name}")
        soup = BeautifulSoup(response.text, self.default_analyzer)

        for article in soup.find_all('article'):
            div_img = article.find('div', class_='image')
            if not div_img:
                continue

            link_el = div_img.find('a', href=True)
            if not link_el:
                continue
            link = link_el['href']

            img = div_img.find('img')
            image = img.get('src', '') if img else ''
            raw_title = img.get('alt', '') if img else ''

            retrieved.append(Anime(title=raw_title, rating='', link=link, image=image))

        return retrieved

    def get_anime_details(self, link: str) -> Anime:
        response = requests.get(link)
        soup = BeautifulSoup(response.text, self.default_analyzer)

        title_elem = soup.find('h1')
        title = title_elem.get_text().strip() if title_elem else link.rstrip('/').split('/')[-1]

        img = soup.find('img', class_=lambda c: c and 'poster' in c.lower() if c else False)
        image = ''
        if img:
            image = img.get('src', '')

        seasons: list[Season] = []
        for ul in soup.find_all('ul', class_='episodios'):
            season_num = len(seasons) + 1
            episodes: list[Episode] = []
            for li in ul.find_all('li'):
                ep_title_div = li.find(class_='episodiotitle')
                if not ep_title_div:
                    continue
                a = ep_title_div.find('a', href=True)
                if not a:
                    continue
                ep_text = a.get_text().strip()
                ep_match = re.search(r'\d+', ep_text)
                ep_num = ep_match.group() if ep_match else '?'
                episodes.append(Episode(
                    number=ep_num,
                    title=ep_text,
                    link=a['href'],
                    video_src='',
                ))
            if episodes:
                seasons.append(Season(number=season_num, episodes=episodes))

        return Anime(
            title=title,
            rating='',
            link=link,
            image=image,
            seasons=seasons if seasons else None,
        )
