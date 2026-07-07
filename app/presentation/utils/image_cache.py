from __future__ import annotations

import threading

from app.presentation.utils.image_renderer import AnsiImage, render_image_from_url

_image_cache: dict[str, AnsiImage | None] = {}
_cache_lock = threading.Lock()


def get_image(url: str, max_width: int = 20) -> AnsiImage | None:
    if not url:
        return None

    key = f"{url}|{max_width}"

    with _cache_lock:
        if key in _image_cache:
            return _image_cache[key]

    result = render_image_from_url(url, max_width)

    with _cache_lock:
        _image_cache[key] = result

    return result
