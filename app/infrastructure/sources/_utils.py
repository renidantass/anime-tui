from __future__ import annotations

import re

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def validate_response(response: requests.Response) -> bool:
    return 200 <= response.status_code < 300


def get_episode_number(title: str) -> str:
    match = re.search(r'Episódio\s*(\d+)', title, re.IGNORECASE)
    return match.group(1) if match else '0'
