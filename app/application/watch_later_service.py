from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

from app.domain.watch_later import WatchLaterEntry


class WatchLaterService:
    def __init__(self, file_path: str | None = None):
        self._lock = threading.Lock()
        self._file_path = Path(
            file_path
            or os.path.join(os.path.expanduser("~"), ".anime-feed-reader", "watch_later.json")
        )
        self._entries: list[WatchLaterEntry] = []
        self._dirty = False
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
            self._entries = [WatchLaterEntry.from_dict(e) for e in data.get("entries", [])]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            self._entries = []

    def add_entry(
        self,
        anime_title: str,
        anime_image: str = "",
        source_name: str = "",
        source_link: str = "",
        source_color: str = "",
    ) -> WatchLaterEntry:
        key = anime_title.strip().casefold()
        now = datetime.now(UTC).isoformat()
        with self._lock:
            for e in self._entries:
                if e.anime_title.strip().casefold() == key:
                    e.anime_image = anime_image or e.anime_image
                    e.source_name = source_name or e.source_name
                    e.source_link = source_link or e.source_link
                    e.source_color = source_color or e.source_color
                    e.added_at = now
                    self._dirty = True
                    self._schedule_save()
                    return e
            entry = WatchLaterEntry(
                anime_title=anime_title,
                anime_image=anime_image,
                source_name=source_name,
                source_link=source_link,
                source_color=source_color,
                added_at=now,
            )
            self._entries.append(entry)
            self._dirty = True
        self._schedule_save()
        return entry

    def remove_entry(self, anime_title: str) -> bool:
        key = anime_title.strip().casefold()
        with self._lock:
            for i, e in enumerate(self._entries):
                if e.anime_title.strip().casefold() == key:
                    self._entries.pop(i)
                    self._dirty = True
                    self._schedule_save()
                    return True
        return False

    def get_all(self) -> list[WatchLaterEntry]:
        with self._lock:
            return sorted(self._entries, key=lambda e: e.added_at, reverse=True)

    def contains(self, anime_title: str) -> bool:
        key = anime_title.strip().casefold()
        with self._lock:
            return any(e.anime_title.strip().casefold() == key for e in self._entries)

    def clear_all(self) -> None:
        with self._lock:
            self._entries.clear()
            self._dirty = True
        self._schedule_save()

    def _schedule_save(self):
        with self._lock:
            if not self._dirty:
                return
            if getattr(self, "_save_pending", False):
                return
            self._save_pending = True
        threading.Thread(target=self._do_save, daemon=True).start()

    def _do_save(self):
        try:
            while True:
                with self._lock:
                    if not self._dirty:
                        return
                    entries = list(self._entries)
                    self._dirty = False
                self._save_entries(entries)
        finally:
            with self._lock:
                self._save_pending = False
                requeue = self._dirty
            if requeue:
                self._schedule_save()

    def _save_entries(self, entries: list[WatchLaterEntry]) -> None:
        self._directory().mkdir(parents=True, exist_ok=True)
        data = {
            "entries": [
                {
                    "anime_title": e.anime_title,
                    "anime_image": e.anime_image,
                    "source_name": e.source_name,
                    "source_link": e.source_link,
                    "source_color": e.source_color,
                    "added_at": e.added_at,
                }
                for e in entries
            ]
        }
        tmp_path = self._file_path.with_name(
            f".{self._file_path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        try:
            tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp_path, self._file_path)
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
