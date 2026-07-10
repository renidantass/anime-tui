"""Cliente HTTP AniSkip — implementação concreta de fetch de skip-times."""

from __future__ import annotations

import logging
from typing import Any

import requests

from app.application.constants import HEADERS

logger = logging.getLogger(__name__)
ANISKIP_BASE = "https://api.aniskip.com/v2/skip-times"


def fetch_skip_times(
    mal_id: int,
    episode: int,
    episode_length: int,
    types: list[str],
) -> dict[str, Any] | None:
    """Faz uma requisição à AniSkip com duração específica."""
    params: list[tuple[str, str | int]] = [("episodeLength", episode_length)]
    for t in types:
        params.append(("types[]", t))
    try:
        r = requests.get(
            f"{ANISKIP_BASE}/{mal_id}/{episode}",
            params=params,
            headers={**HEADERS, "Accept": "application/json"},
            timeout=12,
        )
    except requests.RequestException as e:
        logger.warning("AniSkip request fail: %s", e)
        return None
    if r.status_code == 404:
        return None
    if r.status_code >= 400:
        logger.debug("AniSkip HTTP %s: %s", r.status_code, r.text[:120])
        return None
    try:
        payload = r.json()
    except Exception:
        return None
    if isinstance(payload, dict):
        return payload
    return None
