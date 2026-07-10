"""Proxy de imagem — busca, valida e detecta tipo via magic bytes."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import requests

from app.infrastructure.security import is_safe_url
from app.infrastructure.sources._utils import HEADERS

logger = logging.getLogger(__name__)

MAX_SIZE_BYTES = 5 * 1024 * 1024
MIN_SIZE_BYTES = 32


def derive_referer(image_url: str) -> str:
    """Deriva Referer do domínio da imagem para evitar bloqueio de hotlink."""
    try:
        p = urlparse(image_url)
        if p.scheme and p.netloc:
            return f"{p.scheme}://{p.netloc}/"
    except Exception:
        pass
    return ""


def detect_media_type(data: bytes, content_type: str) -> str:
    """Detecta o media type a partir do Content-Type e magic bytes."""
    if content_type.startswith("image/"):
        return content_type
    if data[:4] == b"RIFF" and b"WEBP" in data[:16]:
        return "image/webp"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    return "image/jpeg"


def is_image_data(data: bytes, content_type: str) -> bool:
    """Valida se os bytes são realmente uma imagem (magic bytes + tipo)."""
    return bool(
        data[:3] == b"\xff\xd8\xff"
        or data[:8] == b"\x89PNG\r\n\x1a\n"
        or data[:3] == b"GIF"
        or (data[:4] == b"RIFF" and b"WEBP" in data[:16])
        or data[4:8] == b"ftyp"
    )


def validate_image(data: bytes, content_type: str) -> tuple[bool, str, str]:
    """Valida e detecta tipo da imagem.

    Returns:
        (ok, media_type, error_message)
    """
    if len(data) > MAX_SIZE_BYTES:
        return False, "", "Imagem grande demais"
    if len(data) < MIN_SIZE_BYTES:
        return False, "", "Imagem vazia"

    if content_type.startswith("text/html") or (
        not content_type.startswith("image/")
        and "octet-stream" not in content_type
        and not is_image_data(data, content_type)
    ):
        return False, "", "Upstream não retornou imagem"

    media = detect_media_type(data, content_type)
    return True, media, ""


def fetch_proxied_image(
    url: str,
    *,
    timeout: float = 15,
    session: requests.Session | None = None,
) -> tuple[bytes, str]:
    """Busca e valida uma imagem via proxy.

    Args:
        url: URL da imagem.
        timeout: Timeout da requisição.
        session: Session HTTP opcional (reusa conexão).

    Returns:
        (data, media_type)

    Raises:
        ValueError: URL inválida ou insegura.
        RuntimeError: Imagem inválida ou erro de upstream.
    """
    if not is_safe_url(url, allow_http=True, resolve_dns=True):
        raise ValueError("URL de imagem inválida")

    referer = derive_referer(url)
    headers = {**HEADERS, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"}
    if referer:
        headers["Referer"] = referer

    sess = session or requests.Session()
    try:
        r = sess.get(url, headers=headers, timeout=timeout, stream=True)
    except requests.RequestException as e:
        raise RuntimeError(str(e)) from e

    if r.status_code >= 400:
        r.close()
        raise RuntimeError(f"Imagem upstream {r.status_code}")

    content_type = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    data = r.content
    r.close()

    ok, media, err = validate_image(data, content_type)
    if not ok:
        raise RuntimeError(err)
    return data, media
