from __future__ import annotations

import threading
from collections import OrderedDict

from app.presentation.utils.image_renderer import AnsiImage, render_image_from_url

_MAX_CACHE_SIZE = 256
_image_cache: OrderedDict[str, AnsiImage | None] = OrderedDict()
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
        if key not in _image_cache:
            if len(_image_cache) >= _MAX_CACHE_SIZE:
                _image_cache.popitem(last=False)
            _image_cache[key] = result

    return result
