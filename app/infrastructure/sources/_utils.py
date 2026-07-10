from __future__ import annotations

import re

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
from app.infrastructure.sources._base import HEADERS, validate_response  # noqa: F401 — re-export


def matches_search_tokens(query: str, raw_title: str, link: str) -> bool:
    tokens = [t for t in re.split(r"\s+", query.lower()) if len(t) > 1]
    if not tokens:
        return True
    blob = f"{raw_title} {link}".lower()
    return all(t in blob for t in tokens)
