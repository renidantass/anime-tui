"""Conexão e pequenos utilitários do MongoDB.

O módulo importa pymongo apenas quando a aplicação é iniciada, permitindo que
os testes unitários dos serviços legados continuem independentes do servidor.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


@lru_cache(maxsize=1)
def get_database():
    from pymongo import MongoClient

    uri = os.environ.get("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI não configurada")
    client = MongoClient(uri, serverSelectionTimeoutMS=10_000)
    database_name = os.environ.get("MONGODB_DATABASE", "animes_tui")
    db = client[database_name]
    db.command("ping")
    db.users.create_index("email", unique=True)
    db.watch_history.create_index(
        [("user_id", 1), ("episode_link", 1)],
        unique=False,
    )
    db.watch_later.create_index([("user_id", 1), ("anime_key", 1)], unique=True)
    db.opening_marks.create_index(
        [("anime_key", 1), ("season_number", 1), ("end_seconds", 1)], unique=True
    )
    db.opening_mark_votes.create_index([("user_id", 1), ("mark_id", 1)], unique=True)
    db.user_configs.create_index("user_id", unique=True)
    return client, db
