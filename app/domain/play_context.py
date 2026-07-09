"""Contexto de reprodução — definido pela fonte, consumido pelo player."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class PlayContext:
    """Tudo que o player precisa para tocar um stream, sem adivinhar a fonte.

    Attributes:
        url: URL a abrir (stream direto ou página).
        referer: Referer HTTP para anti-leech (opcional).
        origin: Origin HTTP no download/probe (opcional).
        is_direct: True se *url* é mídia tocável (mp4/m3u8/CDN), não página HTML.
        page_url: Página do episódio (fallback browser / cache key).
        cache_key: Chave estável de cache (ex.: token Blogger); default = url.
    """

    url: str
    referer: str | None = None
    origin: str | None = None
    is_direct: bool = False
    page_url: str | None = None
    cache_key: str | None = None

    def __post_init__(self) -> None:
        # frozen: usar object.__setattr__
        if not self.page_url:
            object.__setattr__(self, "page_url", self.url)
        if not self.cache_key:
            object.__setattr__(self, "cache_key", self.url)

    def http_headers(self) -> dict[str, str]:
        """Headers de request derivados do contexto (download / probe)."""
        headers: dict[str, str] = {}
        if self.referer:
            headers["Referer"] = self.referer
        if self.origin:
            headers["Origin"] = self.origin
        return headers

    @staticmethod
    def page(url: str, *, referer: str | None = None) -> PlayContext:
        """Página HTML (abre no browser se o player falhar)."""
        return PlayContext(
            url=url,
            referer=referer or url,
            is_direct=False,
            page_url=url,
            cache_key=url,
        )
