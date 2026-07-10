"""Dependências FastAPI compartilhadas entre os routers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request


def _get_state(request: Request):
    request.app.state.ensure_sources()
    return request.app.state


AppState = Annotated[object, Depends(_get_state)]
