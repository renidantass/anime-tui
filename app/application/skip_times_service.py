"""Serviço de skip-times via API AniSkip — compartilhado entre TUI e Web.

Estratégia: testa múltiplas durações de episódio contra a API AniSkip,
que é sensível ao parâmetro ``episodeLength``.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from app.infrastructure.sources._utils import HEADERS

logger = logging.getLogger(__name__)

ANISKIP_BASE = "https://api.aniskip.com/v2/skip-times"


class SkipTimesService:
    """Busca timestamps de opening/ending/recap via AniSkip."""

    def get_skip_times(
        self,
        mal_id: int,
        episode: int,
        episode_length: float = 0,
        types: list[str] | None = None,
    ) -> dict[str, Any]:
        """Busca skip-times com estratégia multi-length.

        Args:
            mal_id: ID MyAnimeList do anime.
            episode: Número do episódio.
            episode_length: Duração em segundos (0 = curinga).
            types: Tipos a buscar (ex.: ["op", "ed"]). Default: ["op"].

        Returns:
            Dict com ``found``, ``mal_id``, ``episode``, ``episode_length``,
            ``results`` (lista de timestamps), e opcionalmente ``message``.
        """
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

    def _build_lengths(self, episode_length: float) -> list[float]:
        """Constrói lista de durações para tentar na API.

        Ordem: 0 (curinga), duração real, arredondamentos.
        """
        lengths: list[float] = [0.0]
        if episode_length and episode_length > 60:
            d = float(episode_length)
            lengths.extend(
                [
                    d,
                    round(d),
                    round(d) - 1,
                    round(d) + 1,
                    round(d / 10) * 10,
                    round(d / 60) * 60,
                ]
            )
        return lengths

    def _fetch(
        self,
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
