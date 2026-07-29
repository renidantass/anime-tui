from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from app.infrastructure.auth import authenticate, create_user, issue_token
from app.presentation.web.schemas import AuthRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register")
def register(body: AuthRequest, response: Response):
    try:
        user = create_user(body.email, body.password)
    except Exception as exc:
        if exc.__class__.__name__ == "DuplicateKeyError":
            raise HTTPException(409, "E-mail já cadastrado") from exc
        raise
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    response.set_cookie("anishelf_token", issue_token(user), httponly=True, samesite="lax", max_age=2592000)
    return user


@router.post("/login")
def login(body: AuthRequest, response: Response):
    user = authenticate(body.email, body.password)
    if not user:
        raise HTTPException(401, "E-mail ou senha inválidos")
    response.set_cookie("anishelf_token", issue_token(user), httponly=True, samesite="lax", max_age=2592000)
    return user


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("anishelf_token")
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(401, "Autenticação necessária")
    return user
