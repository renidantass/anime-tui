"""Reescrita de playlists HLS — genérico, injetável via URL builder."""

from __future__ import annotations

import re
from typing import Callable
from urllib.parse import urljoin


def rewrite_m3u8(
    text: str,
    base_url: str,
    uri_builder: Callable[[str], str],
) -> str:
    """Reescreve URIs absolutas/relativas de um playlist M3U8.

    Args:
        text: Conteúdo do M3U8.
        base_url: URL base para resolver URIs relativas.
        uri_builder: Callable que recebe a URL absoluta e retorna a URL proxy.
    """
    lines_out: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            if "URI=" in stripped:

                def repl(m: re.Match[str]) -> str:
                    raw = m.group(1)
                    abs_u = urljoin(base_url, raw)
                    return f'URI="{uri_builder(abs_u)}"'

                lines_out.append(re.sub(r'URI="([^"]+)"', repl, line))
            else:
                lines_out.append(line)
            continue
        abs_u = urljoin(base_url, stripped)
        lines_out.append(uri_builder(abs_u))
    return "\n".join(lines_out) + "\n"
