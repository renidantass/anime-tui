from __future__ import annotations

import requests

from app.application.title_utils import (  # noqa: F401 — re-export
    audio_variant_label,
    detect_audio_variant,
    extract_episode_number,
    get_episode_number,
    is_only_episode_label,
    is_unknown_episode_number,
    normalize_watch_titles,
    prefer_display_title,
    strip_episode_suffix,
    strip_title_variants,
    title_has_variant_noise,
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def validate_response(response: requests.Response) -> bool:
    return 200 <= response.status_code < 300
