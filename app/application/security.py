"""Validação pura de URLs — sem DNS, sem HTTP — seguro para a camada de application."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

_ALLOWED_SCHEMES = frozenset({"https", "http"})
_BLOCKED_HOST_SUFFIXES = (".local", ".localhost", ".internal", ".intranet", ".lan")


def _is_private_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return bool(addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_multicast or addr.is_reserved or addr.is_unspecified)


def _host_blocked(host: str) -> bool:
    h = host.lower().rstrip(".")
    if not h or h == "localhost" or h.endswith(".localhost"):
        return True
    if h in {"0.0.0.0", "::", "::1"}:
        return True
    for suf in _BLOCKED_HOST_SUFFIXES:
        if h.endswith(suf):
            return True
    try:
        if _is_private_ip(h):
            return True
    except Exception:
        pass
    return False


def is_safe_url(url: str, *, allow_http: bool = True) -> bool:
    """Valida URL sem resolver DNS (puro, seguro para application layer).

    - scheme http/https apenas
    - bloqueia localhost / IPs privados por pattern
    - NÃO faz DNS lookup (delegado ao caller)
    """
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if len(url) > 4096:
        return False
    if re.search(r"[\x00-\x1f\x7f]", url):
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        return False
    if scheme == "http" and not allow_http:
        return False
    host = parsed.hostname
    if not host:
        return False
    if _host_blocked(host):
        return False
    if parsed.username or parsed.password:
        return False
    return True


# ── Blogger detection (regex pura) ──────────────────────────────────────────

_BLOGGER_RE = re.compile(
    r"https?://(?:www\.)?blogger\.com/video\.g\?token=(?P<token>[^&\s#]+)",
    re.IGNORECASE,
)


def is_blogger_url(url: str) -> bool:
    return bool(url and _BLOGGER_RE.search(url))
