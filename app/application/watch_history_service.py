from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.domain.watch_history import WatchHistoryEntry


class WatchHistoryService:
    def __init__(self, file_path: str | None = None):
        self._lock = threading.Lock()
        self._file_path = Path(
            file_path
            or os.path.join(
                os.path.expanduser("~"), ".anime-feed-reader", "watch_history.json"
            )
        )
        self._entries: list[WatchHistoryEntry] = []
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
            self._entries = [
                WatchHistoryEntry.from_dict(e) for e in data.get("entries", [])
            ]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            self._entries = []

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
        progress_seconds: float = 0.0,
        duration_seconds: float = 0.0,
    ) -> WatchHistoryEntry:
        """Cria ou atualiza entrada (mesmo episode_link = upsert)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            for e in self._entries:
                if e.episode_link == episode_link:
                    e.anime_title = anime_title
                    e.episode_title = episode_title
                    e.episode_number = episode_number
                    e.source_name = source_name
                    e.anime_image = anime_image or e.anime_image
                    e.season_number = season_number
                    e.source_color = source_color or e.source_color
                    e.watched_at = now
                    if progress_seconds > 0:
                        e.progress_seconds = progress_seconds
                    if duration_seconds > 0:
                        e.duration_seconds = duration_seconds
                    self._dirty = True
                    entry = e
                    break
            else:
                entry = WatchHistoryEntry(
                    anime_title=anime_title,
                    episode_title=episode_title,
                    episode_number=episode_number,
                    episode_link=episode_link,
                    source_name=source_name,
                    anime_image=anime_image,
                    season_number=season_number,
                    source_color=source_color,
                    progress_seconds=progress_seconds,
                    duration_seconds=duration_seconds,
                    watched_at=now,
                )
                self._entries.append(entry)
                self._dirty = True
        self._schedule_save()
        return entry

    def update_progress(
        self,
        episode_link: str,
        progress_seconds: float,
        duration_seconds: float = 0.0,
    ) -> None:
        """Atualiza progresso de um episódio já no histórico."""
        if not episode_link:
            return
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            for e in self._entries:
                if e.episode_link == episode_link:
                    e.progress_seconds = max(0.0, float(progress_seconds))
                    if duration_seconds and duration_seconds > 0:
                        e.duration_seconds = float(duration_seconds)
                    e.watched_at = now
                    self._dirty = True
                    break
            else:
                return
        self._schedule_save()

    def get_progress(self, episode_link: str) -> float:
        with self._lock:
            for e in self._entries:
                if e.episode_link == episode_link:
                    # se já terminou, recomeça do zero
                    if e.is_finished():
                        return 0.0
                    return float(e.progress_seconds or 0.0)
        return 0.0

    def get_all(self) -> list[WatchHistoryEntry]:
        with self._lock:
            return sorted(self._entries, key=lambda e: e.watched_at, reverse=True)

    def get_all_deduped(self) -> list[WatchHistoryEntry]:
        """Uma entrada por anime (a mais recente), evita repetir o mesmo título."""
        seen: set[str] = set()
        result: list[WatchHistoryEntry] = []
        for e in self.get_all():
            key = (e.anime_title or e.episode_title or "").strip().casefold()
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(e)
        return result

    def clear_all(self) -> None:
        with self._lock:
            self._entries.clear()
            self._dirty = True
        self._schedule_save()

    def _schedule_save(self):
        with self._lock:
            if not self._dirty:
                return
            # um save assíncrono por vez; dirty permanece até gravar
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
                # se ficou dirty de novo durante o write, reagenda (fora do lock)
                requeue = self._dirty
            if requeue:
                self._schedule_save()

    def _save_entries(self, entries: list[WatchHistoryEntry]) -> None:
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
                    "progress_seconds": e.progress_seconds,
                    "duration_seconds": e.duration_seconds,
                }
                for e in entries
            ]
        }
        # tmp único evita colisão entre saves
        tmp_path = self._file_path.with_name(
            f".{self._file_path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        try:
            tmp_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(tmp_path, self._file_path)
        finally:
            tmp_path.unlink(missing_ok=True)
