from __future__ import annotations

from contextlib import contextmanager

import requests
from bs4 import BeautifulSoup

from app.application.interfaces import IAnimeFeedReader
from app.application.title_utils import get_episode_number
from app.domain import PlayContext

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def validate_response(response: requests.Response) -> bool:
    return 200 <= response.status_code < 300


@contextmanager
def http_session():
    session = requests.Session()
    try:
        yield session
    finally:
        session.close()


class AnimeSource(IAnimeFeedReader):
    name: str = ""
    identifier: str = ""
    base_url: str = ""
    color: str = ""
    has_search: bool = True
    has_details: bool = True
    # html.parser (stdlib) — evita dependência nativa do lxml no binário
    default_analyzer: str = "html.parser"

    def get_play_context(self, episode_link: str) -> PlayContext:
        return PlayContext.page(episode_link)

    # ── Helpers compartilhados ───────────────────────────────────────────

    def _fetch_soup(self, url: str, session: requests.Session | None = None) -> BeautifulSoup | None:
        fetcher = session.get if session else requests.get
        try:
            response = fetcher(url, headers=HEADERS, timeout=20)
        except requests.RequestException:
            return None
        if not validate_response(response):
            return None
        return BeautifulSoup(response.text, self.default_analyzer)

    @staticmethod
    def _extract_title(soup, fallback_link: str = "") -> str:
        title_elem = soup.find("h1")
        if title_elem:
            return title_elem.get_text().strip()
        return fallback_link.rstrip("/").split("/")[-1] if fallback_link else ""

    @staticmethod
    def _extract_image(soup) -> str:
        img = soup.find("img")
        if not img:
            return ""
        return img.get("data-src") or img.get("data-lazy-src") or img.get("data-original") or img.get("src", "")

    @staticmethod
    def _resolve_episode_number(ep_text: str, raw_title: str, episode_link: str) -> str:
        num = get_episode_number(ep_text, episode_link)
        if num in {"?", "0"}:
            num = get_episode_number(raw_title, episode_link)
        return num
