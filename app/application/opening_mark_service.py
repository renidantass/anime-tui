"""Serviço de marcação de fim de abertura (opening) por temporada de anime."""

from __future__ import annotations

import contextlib
import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


class OpeningMarkService:
    """Persiste marcações comunitárias de fim de abertura por anime/temporada."""

    def __init__(self, file_path: str | None = None, *, mongo_db=None, user_id: str | None = None):
        self._lock = threading.Lock()
        self._file_path = Path(file_path) if file_path else None
        self._marks: dict[str, float] = {}
        self._mongo_db = mongo_db
        self._user_id = user_id
        self._dirty = False
        self._load()

    @staticmethod
    def _normalize_title(title: str) -> str:
        import re
        import unicodedata

        t = unicodedata.normalize("NFKD", str(title or "").strip().lower())
        t = "".join(c for c in t if ord(c) < 0x0300 or ord(c) > 0x036F)
        return re.sub(r"\s+", " ", t)

    @staticmethod
    def _key(anime_title: str, season_number: int) -> str:
        normalized = OpeningMarkService._normalize_title(anime_title)
        season = max(1, int(season_number or 1))
        return f"{normalized}|s{season}"

    def _load(self) -> None:
        if self._mongo_db is not None and self._user_id:
            self._marks = {}
            return
        if self._file_path is None:
            self._marks = {}
            return
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
        if self._mongo_db is not None and self._user_id:
            info = self.get_mark_info(anime_title, season_number)
            return info["end_seconds"] if info else None
        key = self._key(anime_title, season_number)
        with self._lock:
            val = self._marks.get(key)
        if val is None:
            return None
        val = float(val)
        if 20 <= val <= 240:
            return val
        return None

    def get_mark_info(self, anime_title: str, season_number: int = 1) -> dict | None:
        """Retorna a marcação comunitária mais bem avaliada."""
        if self._mongo_db is None or not self._user_id:
            value = self.get_mark(anime_title, season_number)
            return {"end_seconds": value, "score": 0, "upvotes": 0, "downvotes": 0} if value else None
        key = self._normalize_title(anime_title)
        doc = self._mongo_db.opening_marks.find_one(
            {"anime_key": key, "season_number": max(1, int(season_number or 1))},
            sort=[("score", -1), ("upvotes", -1), ("created_at", 1)],
        )
        if not doc:
            return None
        return {
            "mark_id": str(doc["_id"]),
            "end_seconds": float(doc["end_seconds"]),
            "score": int(doc.get("score", 0)),
            "upvotes": int(doc.get("upvotes", 0)),
            "downvotes": int(doc.get("downvotes", 0)),
        }

    def save_mark(self, anime_title: str, season_number: int, end_seconds: float) -> dict | None:
        """Salva o fim da abertura para um anime/temporada."""
        end = float(end_seconds)
        if not 20 <= end <= 240:
            return None
        if self._mongo_db is not None and self._user_id:
            from pymongo import ReturnDocument

            key = self._normalize_title(anime_title)
            season = max(1, int(season_number or 1))
            result = self._mongo_db.opening_marks.find_one_and_update(
                {"anime_key": key, "season_number": season, "end_seconds": round(end * 10) / 10},
                {"$setOnInsert": {"_id": str(uuid4()), "anime_key": key, "season_number": season,
                                  "end_seconds": round(end * 10) / 10, "score": 0,
                                  "upvotes": 0, "downvotes": 0,
                                  "created_at": datetime.now(UTC)}},
                upsert=True, return_document=ReturnDocument.AFTER,
            )
            mark_id = str(result["_id"])
            self.vote(mark_id, 1)
            return self.get_mark_info(anime_title, season)
        key = self._key(anime_title, season_number)
        with self._lock:
            self._marks[key] = round(end * 10) / 10
            self._dirty = True
        self._schedule_save()
        return {"end_seconds": round(end * 10) / 10, "score": 0, "upvotes": 0, "downvotes": 0}

    def vote(self, mark_id: str, value: int) -> dict:
        """Registra ou altera o voto do usuário atual (-1 ou +1)."""
        if self._mongo_db is None or not self._user_id:
            raise ValueError("Votação comunitária requer MongoDB e usuário autenticado")
        if value not in (-1, 1):
            raise ValueError("Voto deve ser 1 ou -1")
        marks = self._mongo_db.opening_marks
        votes = self._mongo_db.opening_mark_votes
        mark = marks.find_one({"_id": mark_id})
        if not mark:
            raise KeyError("Marcação não encontrada")
        previous = votes.find_one({"user_id": self._user_id, "mark_id": mark_id})
        if previous and previous["value"] == value:
            return self.get_mark_info(mark["anime_key"], mark["season_number"]) or {}
        if previous:
            old = int(previous["value"])
            votes.update_one({"_id": previous["_id"]}, {"$set": {"value": value}})
            marks.update_one({"_id": mark_id}, {"$inc": {
                "score": value - old, "upvotes": (1 if value == 1 else -1),
                "downvotes": (1 if value == -1 else -1),
            }})
        else:
            votes.insert_one({"user_id": self._user_id, "mark_id": mark_id, "value": value})
            marks.update_one({"_id": mark_id}, {"$inc": {
                "score": value, "upvotes": (1 if value == 1 else 0),
                "downvotes": (1 if value == -1 else 0),
            }})
        return self.get_mark_info(mark["anime_key"], mark["season_number"]) or {}

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
        if self._mongo_db is not None and self._user_id:
            collection = self._mongo_db.opening_marks
            collection.delete_many({"user_id": self._user_id})
            if marks:
                collection.insert_many([
                    {"user_id": self._user_id, "anime_key": key.rsplit("|s", 1)[0],
                     "season_number": int(key.rsplit("|s", 1)[1]), "end_seconds": value}
                    for key, value in marks.items()
                ])
            return
        if self._file_path is None:
            return
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
