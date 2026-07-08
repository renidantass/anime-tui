"""Utilitários de segurança para URLs, hosts e downloads.

Mitiga SSRF (localhost/rede privada), schemes perigosos e abuso de tamanho.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from urllib.parse import quote, urlparse

logger = logging.getLogger(__name__)

_ALLOWED_SCHEMES = frozenset({"https", "http"})
# Preferir HTTPS; HTTP só se explicitamente permitido (alguns CDNs legados).
_DEFAULT_HTTPS_ONLY = False

# Hosts/padrões bloqueados mesmo se DNS “parecer” público
_BLOCKED_HOST_SUFFIXES = (
    ".local",
    ".localhost",
    ".internal",
    ".intranet",
    ".lan",
)

_MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024  # 8 MiB (imagens / probes leves)
_MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MiB


def is_private_or_reserved_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False  # não é IP literal
    return bool(
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
        or (
            addr.version == 6
            and addr.ipv4_mapped is not None
            and is_private_or_reserved_ip(str(addr.ipv4_mapped))
        )
    )


def _host_looks_blocked(host: str) -> bool:
    h = host.lower().rstrip(".")
    if not h or h == "localhost" or h.endswith(".localhost"):
        return True
    if h in {"0.0.0.0", "::", "::1"}:
        return True
    for suf in _BLOCKED_HOST_SUFFIXES:
        if h.endswith(suf):
            return True
    # IP literal na URL
    try:
        if is_private_or_reserved_ip(h):
            return True
    except Exception:
        pass
    return False


def resolve_host_ips(host: str, timeout: float = 3.0) -> list[str]:
    """Resolve A/AAAA; retorna lista de IPs (pode ser vazia se falhar)."""
    try:
        old = socket.getdefaulttimeout()
        socket.setdefaulttimeout(timeout)
        try:
            infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        finally:
            socket.setdefaulttimeout(old)
        ips: list[str] = []
        for info in infos:
            ip = info[4][0]
            if ip not in ips:
                ips.append(ip)
        return ips
    except OSError as e:
        logger.debug("DNS falhou para %s: %s", host, e)
        return []


def is_safe_url(
    url: str,
    *,
    allow_http: bool = True,
    resolve_dns: bool = True,
    allow_private: bool = False,
) -> bool:
    """Valida se *url* é segura para fetch/abrir no player.

    - scheme http/https apenas
    - bloqueia localhost / IPs privados (após DNS se resolve_dns=True)
    """
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if len(url) > 4096:
        return False
    # rejeita control chars / newlines (header injection)
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
    if _host_looks_blocked(host) and not allow_private:
        return False

    # userinfo em URL (https://user:pass@host) — evita
    if parsed.username or parsed.password:
        return False

    if resolve_dns and not allow_private:
        ips = resolve_host_ips(host)
        if not ips:
            # sem DNS: deixa passar só se host não parece privado (CDN flaky)
            # mas para SSRF preferimos falhar fechado em fetches sensíveis
            return True
        for ip in ips:
            if is_private_or_reserved_ip(ip):
                logger.warning("URL bloqueada (IP privado %s): %s", ip, host)
                return False
    return True


def require_safe_url(url: str, **kwargs) -> str | None:
    """Retorna a URL se segura, senão None."""
    if is_safe_url(url, **kwargs):
        return url.strip()
    logger.warning("URL rejeitada por política de segurança: %s…", (url or "")[:80])
    return None


def safe_player_url(url: str) -> str | None:
    """URL permitida para passar ao mpv/vlc (https/http público)."""
    u = require_safe_url(url, allow_http=True, resolve_dns=True)
    if not u:
        return None
    # mpv interpreta args que começam com '-' como opções
    if u.lstrip().startswith("-"):
        return None
    return u


def quote_path_segment(value: str) -> str:
    """Percent-encode para uso em path de URL (busca etc.)."""
    return quote(str(value or "").strip(), safe="")


def clamp_download(
    resp,
    *,
    max_bytes: int = _MAX_DOWNLOAD_BYTES,
) -> bytes | None:
    """Lê corpo de response com teto de bytes. None se exceder ou falhar."""
    try:
        cl = resp.headers.get("Content-Length")
        if cl is not None:
            try:
                if int(cl) > max_bytes:
                    logger.warning("Download bloqueado: Content-Length %s > %s", cl, max_bytes)
                    return None
            except ValueError:
                pass
        chunks: list[bytes] = []
        total = 0
        for chunk in resp.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                logger.warning("Download abortado: excedeu %s bytes", max_bytes)
                return None
            chunks.append(chunk)
        return b"".join(chunks)
    except Exception as e:
        logger.debug("clamp_download falhou: %s", e)
        return None


def safe_get_bytes(
    url: str,
    *,
    session=None,
    headers: dict | None = None,
    timeout: float = 15,
    max_bytes: int = _MAX_DOWNLOAD_BYTES,
    allow_http: bool = True,
) -> bytes | None:
    """GET seguro com validação de URL e limite de tamanho."""
    import requests

    if not is_safe_url(url, allow_http=allow_http, resolve_dns=True):
        return None
    own = session is None
    sess = session or requests.Session()
    try:
        resp = sess.get(
            url,
            headers=headers or {},
            timeout=timeout,
            stream=True,
            allow_redirects=True,
        )
        # revalida host final após redirects
        if not is_safe_url(resp.url, allow_http=allow_http, resolve_dns=True):
            logger.warning("Redirect para URL insegura: %s", resp.url[:80])
            resp.close()
            return None
        if not (200 <= resp.status_code < 300):
            resp.close()
            return None
        data = clamp_download(resp, max_bytes=max_bytes)
        resp.close()
        return data
    except Exception as e:
        logger.debug("safe_get_bytes falhou para %s: %s", url[:60], e)
        return None
    finally:
        if own:
            sess.close()
