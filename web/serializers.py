"""Serialização de DTOs / entidades para JSON da API web."""

from __future__ import annotations

from app.application.dtos import (
    AnimeDetail,
    AnimeEntry,
    EpisodeEntry,
    EpisodeItem,
    SeasonDetail,
    SourceEntry,
    SourceInfo,
)
from app.domain.watch_history import WatchHistoryEntry


def source_info(s: SourceInfo) -> dict:
    return {
        "name": s.name,
        "video_src": s.video_src or "",
        "link": s.link or "",
        "color": s.color or "",
    }


def episode_entry(e: EpisodeEntry) -> dict:
    return {
        "title": e.title,
        "image": e.image or "",
        "date": e.date or "",
        "number": e.number or "",
        "sources": [source_info(s) for s in e.sources],
    }


def anime_entry(a: AnimeEntry) -> dict:
    return {
        "title": a.title,
        "rating": a.rating or "",
        "image": a.image or "",
        "sources": [source_info(s) for s in a.sources],
    }


def episode_item(ep: EpisodeItem) -> dict:
    return {
        "number": ep.number,
        "title": ep.title,
        "link": ep.link,
        "video_src": ep.video_src or "",
        "image": ep.image or "",
        "date": ep.date or "",
    }


def season_detail(s: SeasonDetail) -> dict:
    return {
        "number": s.number,
        "episodes": [episode_item(ep) for ep in s.episodes],
    }


def anime_detail(a: AnimeDetail) -> dict:
    return {
        "title": a.title,
        "rating": a.rating or "",
        "link": a.link,
        "image": a.image or "",
        "description": a.description or "",
        "seasons": [season_detail(s) for s in (a.seasons or [])],
    }


def source_entry(e: SourceEntry, enabled: bool) -> dict:
    status = getattr(e, "status", None) or (
        "online" if e.available else ("offline" if e.error else "unknown")
    )
    uptime = getattr(e, "uptime_percent", None)
    latency = getattr(e, "latency_ms", None)
    checks_total = int(getattr(e, "checks_total", 0) or 0)
    checks_ok = int(getattr(e, "checks_ok", 0) or 0)
    return {
        "name": e.name,
        "identifier": e.identifier,
        "color": e.color or "",
        "has_search": e.has_search,
        "has_details": e.has_details,
        "available": bool(e.available),
        "error": e.error or "",
        "enabled": enabled,
        "status": status,
        "latency_ms": latency,
        "last_check_at": getattr(e, "last_check_at", "") or "",
        "uptime_percent": uptime,
        "checks_total": checks_total,
        "checks_ok": checks_ok,
        "base_url": getattr(e, "base_url", "") or "",
    }


def history_entry(e: WatchHistoryEntry) -> dict:
    from app.infrastructure.sources._utils import normalize_watch_titles

    anime_t, ep_t, ep_n = normalize_watch_titles(
        e.anime_title or "",
        e.episode_title or "",
        e.episode_number or "",
    )
    return {
        "anime_title": anime_t,
        "episode_title": ep_t,
        "episode_number": ep_n,
        "episode_link": e.episode_link,
        "source_name": e.source_name,
        "anime_image": e.anime_image or "",
        "watched_at": e.watched_at,
        "season_number": e.season_number,
        "source_color": e.source_color or "",
        "progress_seconds": e.progress_seconds,
        "duration_seconds": e.duration_seconds,
        "progress_ratio": e.progress_ratio(),
        "is_finished": e.is_finished(),
    }
