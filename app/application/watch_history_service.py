from __future__ import annotations

import json
import os
import threading
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from app.application.title_utils import (
    is_unknown_episode_number,
    normalize_watch_titles,
    strip_title_variants,
)
from app.domain.watch_history import WatchHistoryEntry


class WatchHistoryService:
    def __init__(self, file_path: str | None = None):
        self._lock = threading.Lock()
        self._file_path = Path(
            file_path
            or os.path.join(os.path.expanduser("~"), ".anime-feed-reader", "watch_history.json")
        )
        self._entries: list[WatchHistoryEntry] = []
        self._dirty = False
        self._load()

    def _directory(self) -> Path:
        return self._file_path.parent

    @staticmethod
    def _normalize_fields(
        anime_title: str,
        episode_title: str,
        episode_number: str,
    ) -> tuple[str, str, str, str, str]:
        """(anime, episode_title, number, anime_key, episode_key)."""
        anime, ep, num = normalize_watch_titles(
            anime_title or "", episode_title or "", episode_number or ""
        )
        # "X" e "X Dublado" contam como o mesmo anime no histórico
        anime_key = strip_title_variants(anime).strip().casefold()
        if is_unknown_episode_number(num):
            ep_key = ""
        else:
            ep_key = str(int(num)) if str(num).strip().isdigit() else str(num).strip().casefold()
        return anime, ep, num or (episode_number or ""), anime_key, ep_key

    @staticmethod
    def _entry_keys(e: WatchHistoryEntry) -> tuple[str, str, str]:
        """(anime_key, episode_key, link)."""
        _, _, _, anime_key, ep_key = WatchHistoryService._normalize_fields(
            e.anime_title, e.episode_title, e.episode_number
        )
        return anime_key, ep_key, (e.episode_link or "").strip()

    def _load(self) -> None:
        if not self._file_path.exists():
            self._entries = []
            return
        try:
            raw = self._file_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            self._entries = [WatchHistoryEntry.from_dict(e) for e in data.get("entries", [])]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            self._entries = []
        # limpa duplicatas legadas (mesmo anime/ep com links de fontes diferentes)
        self._compact_duplicates()

    def _compact_duplicates(self) -> None:
        """Mantém a entrada mais recente por (anime, episódio) ou link."""
        if not self._entries:
            return
        ordered = sorted(self._entries, key=lambda e: e.watched_at, reverse=True)
        seen_anime_ep: set[str] = set()
        seen_links: set[str] = set()
        kept: list[WatchHistoryEntry] = []
        changed = False
        for e in ordered:
            anime_key, ep_key, link = self._entry_keys(e)
            if link and link in seen_links:
                changed = True
                continue
            # chave de episódio: anime + número (quando conhecido)
            if anime_key and ep_key:
                k = f"{anime_key}|{ep_key}"
                if k in seen_anime_ep:
                    changed = True
                    continue
                seen_anime_ep.add(k)
            elif anime_key:
                # sem número: ainda dedupe por anime (fila “continuar”)
                # mas em compactação total preferimos não juntar eps diferentes sem número
                pass
            if link:
                seen_links.add(link)
            # normaliza campos gravados
            anime, ep, num, _, _ = self._normalize_fields(
                e.anime_title, e.episode_title, e.episode_number
            )
            if (e.anime_title, e.episode_title, e.episode_number) != (anime, ep, num):
                e.anime_title = anime
                e.episode_title = ep
                e.episode_number = num
                changed = True
            kept.append(e)
        if changed or len(kept) != len(self._entries):
            self._entries = kept
            self._dirty = True
            self._schedule_save()

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
        """Cria ou atualiza entrada.

        Upsert por:
        1) mesmo episode_link
        2) mesmo anime + mesmo nº de episódio (fonte diferente)
        """
        anime_title, episode_title, episode_number, anime_key, ep_key = self._normalize_fields(
            anime_title, episode_title, episode_number
        )
        link = (episode_link or "").strip()
        now = datetime.now(UTC).isoformat()
        with self._lock:
            entry: WatchHistoryEntry | None = None
            for e in self._entries:
                e_anime, e_ep, e_link = self._entry_keys(e)
                same_link = bool(link) and e_link == link
                same_ep = (
                    bool(anime_key) and bool(ep_key) and e_anime == anime_key and e_ep == ep_key
                )
                if same_link or same_ep:
                    e.anime_title = anime_title
                    e.episode_title = episode_title
                    e.episode_number = episode_number
                    e.episode_link = link or e.episode_link
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
            if entry is None:
                entry = WatchHistoryEntry(
                    anime_title=anime_title,
                    episode_title=episode_title,
                    episode_number=episode_number,
                    episode_link=link,
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
        now = datetime.now(UTC).isoformat()
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
        """Uma entrada por anime (a mais recente), com título normalizado."""
        seen: set[str] = set()
        result: list[WatchHistoryEntry] = []
        for e in self.get_all():
            anime_key, _, _ = self._entry_keys(e)
            if not anime_key or anime_key in seen:
                continue
            seen.add(anime_key)
            result.append(e)
        return result

    def get_all_unique_episodes(self) -> list[WatchHistoryEntry]:
        """Uma entrada por anime+episódio (mais recente), sem duplicar fontes."""
        seen: set[str] = set()
        result: list[WatchHistoryEntry] = []
        for e in self.get_all():
            anime_key, ep_key, link = self._entry_keys(e)
            if anime_key and ep_key:
                key = f"{anime_key}|{ep_key}"
            else:
                key = link or f"{anime_key}|{e.watched_at}"
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
        tmp_path = self._file_path.with_name(
            f".{self._file_path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        try:
            tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp_path, self._file_path)
        finally:
            with suppress(OSError):
                tmp_path.unlink(missing_ok=True)
