"""Schemas Pydantic para a API web."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PlaySourceCandidate(BaseModel):
    name: str = ""
    link: str
    color: str = ""


class WebPlayRequest(BaseModel):
    episode_link: str = ""
    preferred_source: str | None = None
    anime_title: str = ""
    episode_title: str = ""
    episode_number: str = ""
    anime_image: str = ""
    season_number: int = 1
    source_color: str = ""
    candidates: list[PlaySourceCandidate] = Field(default_factory=list)


class ProgressRequest(BaseModel):
    episode_link: str
    progress_seconds: float = 0.0
    duration_seconds: float = 0.0


class HistoryAddRequest(BaseModel):
    anime_title: str
    episode_title: str
    episode_number: str
    episode_link: str
    source_name: str
    anime_image: str = ""
    season_number: int = 1
    source_color: str = ""
    progress_seconds: float = 0.0
    duration_seconds: float = 0.0


class SourceToggle(BaseModel):
    enabled: bool


class GenreResolveRequest(BaseModel):
    items: list[dict] = Field(default_factory=list)


class WatchLaterAddRequest(BaseModel):
    anime_title: str
    anime_image: str = ""
    source_name: str = ""
    source_link: str = ""
    source_color: str = ""


class OpeningMarkSaveRequest(BaseModel):
    anime_title: str
    season_number: int = 1
    end_seconds: float


class OpeningMarkGetRequest(BaseModel):
    anime_title: str
    season_number: int = 1
