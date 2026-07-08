from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from app.domain.watch_history import WatchHistoryEntry


class WatchHistoryService:
    def __init__(self, file_path: str | None = None):
        self._lock = threading.Lock()
        self._file_path = Path(file_path or os.path.join(
            os.path.expanduser("~"), ".anime-feed-reader", "watch_history.json"
        ))
        self._entries: list[WatchHistoryEntry] = []
        self._load()

    def _directory(self) -> Path:
        return self._file_path.parent

    def _load(self) -> None:
        if not self._file_path.exists():
            self._entries = []
            return
        try:
            raw = self._file_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            self._entries = [WatchHistoryEntry(**e) for e in data.get("entries", [])]
        except (json.JSONDecodeError, KeyError, TypeError):
            self._entries = []

    def _save(self) -> None:
        self._directory().mkdir(parents=True, exist_ok=True)
        data = {
            "entries": [
                {
                    "anime_title": e.anime_title,
                    "episode_title": e.episode_title,
                    "episode_number": e.episode_number,
                    "episode_link": e.episode_link,
                    "source_name": e.source_name,
                    "anime_image": e.anime_image,
                    "watched_at": e.watched_at,
                    "season_number": e.season_number,
                    "source_color": e.source_color,
                }
                for e in self._entries
            ]
        }
        tmp_path = self._file_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, self._file_path)

    def add_entry(
        self,
        anime_title: str,
        episode_title: str,
        episode_number: str,
        episode_link: str,
        source_name: str,
        anime_image: str = "",
        season_number: int = 1,
        source_color: str = "",
    ) -> WatchHistoryEntry:
        entry = WatchHistoryEntry(
            anime_title=anime_title,
            episode_title=episode_title,
            episode_number=episode_number,
            episode_link=episode_link,
            source_name=source_name,
            anime_image=anime_image,
            season_number=season_number,
            source_color=source_color,
        )
        with self._lock:
            self._entries.append(entry)
        self._save()
        return entry

    def get_all(self) -> list[WatchHistoryEntry]:
        with self._lock:
            return sorted(self._entries, key=lambda e: e.watched_at, reverse=True)

    def clear_all(self) -> None:
        with self._lock:
            self._entries.clear()
        self._save()
