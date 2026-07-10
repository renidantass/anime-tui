"""Serviço de marcação de fim de abertura (opening) por temporada de anime."""

from __future__ import annotations

import contextlib
import json
import os
import threading
from pathlib import Path


class OpeningMarkService:
    """Persiste e recupera marcações de fim de abertura por anime/season.

    A chave de busca é baseada no título normalizado do anime + número da temporada,
    permitindo que cada temporada tenha sua própria marcação.
    """

    def __init__(self, file_path: str | None = None):
        self._lock = threading.Lock()
        self._file_path = Path(
            file_path
            or os.path.join(os.path.expanduser("~"), ".anime-feed-reader", "opening_marks.json")
        )
        self._marks: dict[str, float] = {}
        self._dirty = False
        self._load()

    @staticmethod
    def _normalize_title(title: str) -> str:
        import re
        t = str(title or "").strip().lower().normalize("NFKD")
        t = "".join(c for c in t if ord(c) < 0x0300 or ord(c) > 0x036F)
        return re.sub(r"\s+", " ", t)

    @staticmethod
    def _key(anime_title: str, season_number: int) -> str:
        normalized = OpeningMarkService._normalize_title(anime_title)
        season = max(1, int(season_number or 1))
        return f"{normalized}|s{season}"

    def _load(self) -> None:
        if not self._file_path.exists():
            self._marks = {}
            return
        try:
            raw = self._file_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            loaded = data.get("marks", {})
            self._marks = {
                k: float(v)
                for k, v in loaded.items()
                if isinstance(k, str) and isinstance(v, (int, float))
            }
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            self._marks = {}

    def get_mark(self, anime_title: str, season_number: int = 1) -> float | None:
        """Retorna o tempo em segundos onde a abertura termina, ou None."""
        key = self._key(anime_title, season_number)
        with self._lock:
            val = self._marks.get(key)
        if val is None:
            return None
        val = float(val)
        if 20 <= val <= 240:
            return val
        return None

    def save_mark(self, anime_title: str, season_number: int, end_seconds: float) -> None:
        """Salva o fim da abertura para um anime/temporada."""
        end = float(end_seconds)
        if not 20 <= end <= 240:
            return
        key = self._key(anime_title, season_number)
        with self._lock:
            self._marks[key] = round(end * 10) / 10
            self._dirty = True
        self._schedule_save()

    def list_marks(self) -> dict[str, float]:
        """Retorna cópia de todas as marcações (chave -> segundos)."""
        with self._lock:
            return dict(self._marks)

    def _schedule_save(self) -> None:
        with self._lock:
            if not self._dirty:
                return
            if getattr(self, "_save_pending", False):
                return
            self._save_pending = True
        threading.Thread(target=self._do_save, daemon=True).start()

    def _do_save(self) -> None:
        try:
            while True:
                with self._lock:
                    if not self._dirty:
                        return
                    marks = dict(self._marks)
                    self._dirty = False
                self._save_marks(marks)
        finally:
            with self._lock:
                self._save_pending = False
                requeue = self._dirty
            if requeue:
                self._schedule_save()

    def _save_marks(self, marks: dict[str, float]) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"marks": marks}
        tmp_path = self._file_path.with_name(
            f".{self._file_path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        try:
            tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp_path, self._file_path)
        finally:
            with contextlib.suppress(OSError):
                tmp_path.unlink(missing_ok=True)
