import requests

from app.application.interfaces import IAnimeFeedReader
from app.domain import Anime, Episode
from bs4 import BeautifulSoup


class AnimesOnlineFeedReader(IAnimeFeedReader):
    default_analyzer = 'lxml'

    urls = {
        "last_episodes": "https://animesonlinecc.to/episodio/",
        "search": "https://animesonlinecc.to/search"
    }

    def __get_episode_number(self, title) -> str:
        episode_number = '0'
        episode_separator = 'Episodio'

        if episode_separator:
            separated_title = title.rpartition(episode_separator)
            episode_number = separated_title[-1]
            return episode_number.strip()

        return episode_number

    def get_video_src(self, episode_link: str) -> str:
        response = requests.get(episode_link)
        soup = BeautifulSoup(response.text, self.default_analyzer)

        playex = soup.find('div', 'playex')
        iframe = playex.iframe

        return iframe['src']

    def get_last_episodes(self) -> list[Episode]:
        retrieved_episodes: list[Episode] = []

        response = requests.get(self.urls["last_episodes"])
        soup = BeautifulSoup(response.text, self.default_analyzer)

        episodes = soup.find_all("article", "episodes")

        for episode in episodes:
            title_element = episode.find('div', 'eptitle').h3
            raw_title = title_element.get_text().strip()
            episode_link = title_element.a['href']
            episode_number = self.__get_episode_number(raw_title)
            video_src = self.get_video_src(episode_link)

            retrieved_episode = Episode(episode_number, raw_title, episode_link, video_src)
            retrieved_episodes.append(retrieved_episode)

        return retrieved_episodes

    def search_by(self, name: str) -> list[Anime]:
        retrieved_animes: list[Anime] = []
        url = f"{self.urls["search"]}/{name}"

        response = requests.get(url)
        soup = BeautifulSoup(response.text, self.default_analyzer)

        articles = soup.find_all("article", "tvshows")

        for article in articles:
            poster = article.find("div", "poster")
            rating = poster.find("div", "rating").get_text()

            data = article.find("div", "data")
            title = data.h3
            link = title.a["href"]
            raw_title = title.get_text().strip()

            retrieved_anime = Anime(title=raw_title, rating=rating, link=link)
            retrieved_animes.append(retrieved_anime)

        return retrieved_animes
