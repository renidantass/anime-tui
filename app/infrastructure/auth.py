"""Autenticação stateless para a interface web."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import bcrypt
import jwt

from app.infrastructure.mongodb import get_database


def _secret() -> str:
    secret = os.environ.get("AUTH_SECRET") or os.environ.get("MONGODB_PASSWORD")
    if not secret:
        raise RuntimeError("AUTH_SECRET não configurado")
    return secret


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except (ValueError, TypeError):
        return False


def create_user(email: str, password: str) -> dict:
    _, db = get_database()
    email = email.strip().casefold()
    if len(password) < 8:
        raise ValueError("A senha deve ter pelo menos 8 caracteres")
    user = {"_id": str(uuid4()), "email": email, "password_hash": hash_password(password)}
    db.users.insert_one(user)
    return {"id": user["_id"], "email": email}


def authenticate(email: str, password: str) -> dict | None:
    _, db = get_database()
    user = db.users.find_one({"email": email.strip().casefold()})
    if not user or not verify_password(password, user["password_hash"]):
        return None
    return {"id": user["_id"], "email": user["email"]}


def issue_token(user: dict) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": user["id"], "email": user["email"], "iat": now, "exp": now + timedelta(days=30)},
        _secret(), algorithm="HS256"
    )


def decode_token(token: str) -> dict:
    return jwt.decode(token, _secret(), algorithms=["HS256"])
