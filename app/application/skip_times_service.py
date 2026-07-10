"""Lógica de skip-times — estratégia multi-length sem dependência de HTTP."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class SkipTimesService:
    """Busca timestamps de opening/ending/recap — recebe fetch callable injetado."""

    def __init__(self, fetch: Callable[..., dict[str, Any] | None] | None = None):
        self._fetch = fetch

    def get_skip_times(
        self,
        mal_id: int,
        episode: int,
        episode_length: float = 0,
        types: list[str] | None = None,
    ) -> dict[str, Any]:
        type_list = list(types) if types else ["op"]
        if not type_list:
            type_list = ["op"]

        lengths = self._build_lengths(episode_length)
        tried: set[int] = set()
        last_payload: dict[str, Any] | None = None

        for raw_len in lengths:
            L = max(0, int(raw_len or 0))
            if L in tried:
                continue
            tried.add(L)
            if not self._fetch:
                continue
            response = self._fetch(mal_id, episode, L, type_list)
            if response is None:
                continue
            if response.get("found") and response.get("results"):
                response["episode_length"] = L
                return response
            last_payload = response

        return {
            "found": False,
            "mal_id": mal_id,
            "episode": episode,
            "results": [],
            "message": (last_payload or {}).get("message") or "No skip times found",
        }

    @staticmethod
    def _build_lengths(episode_length: float) -> list[float]:
        lengths: list[float] = [0.0]
        if episode_length and episode_length > 60:
            d = float(episode_length)
            lengths.extend(
                [d, round(d), round(d) - 1, round(d) + 1, round(d / 10) * 10, round(d / 60) * 60]
            )
        return lengths
