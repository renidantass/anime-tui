from __future__ import annotations

from contextlib import contextmanager

import requests
from bs4 import BeautifulSoup

from app.application.interfaces import IAnimeFeedReader
from app.application.title_utils import get_episode_number
from app.domain import PlayContext
from app.infrastructure.http_cache import get_cached, set_cached
from app.infrastructure.http_retry import retry_request

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
    request_timeout: float = 20
    max_retries: int = 2
    default_analyzer: str = "html.parser"

    def __init__(self, base_url: str | None = None):
        if base_url:
            self.base_url = base_url.rstrip("/")

    def get_play_context(self, episode_link: str) -> PlayContext:
        return PlayContext.page(episode_link)

    def _fetch_soup(
        self, url: str, session: requests.Session | None = None
    ) -> BeautifulSoup | None:
        resp = retry_request(
            "GET",
            url,
            session=session,
            timeout=self.request_timeout,
            max_retries=self.max_retries,
            headers=HEADERS,
        )
        if resp is None or not validate_response(resp):
            return None
        return BeautifulSoup(resp.text, self.default_analyzer)

    def _fetch_text(
        self, url: str, session: requests.Session | None = None, use_cache: bool = True
    ) -> str | None:
        if use_cache:
            cached = get_cached("GET", url)
            if cached is not None:
                return cached

        resp = retry_request(
            "GET",
            url,
            session=session,
            timeout=self.request_timeout,
            max_retries=self.max_retries,
            headers=HEADERS,
        )
        if resp is None or not validate_response(resp):
            return None

        text = resp.text
        if use_cache:
            set_cached("GET", url, text)
        return text

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
        return (
            img.get("data-src")
            or img.get("data-lazy-src")
            or img.get("data-original")
            or img.get("src", "")
        )

    @staticmethod
    def _resolve_episode_number(ep_text: str, raw_title: str, episode_link: str) -> str:
        num = get_episode_number(ep_text, episode_link)
        if num in {"?", "0"}:
            num = get_episode_number(raw_title, episode_link)
        return num
