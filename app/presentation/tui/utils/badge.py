import hashlib

_VIBRANT_COLORS = [
    "#e74c3c", "#d35400", "#c0392b", "#1e8449", "#117a65",
    "#3498db", "#9b59b6", "#e84393", "#1a5276", "#6c5ce7",
    "#8e44ad", "#1f618d", "#0984e3", "#d63031", "#636e72",
]


def _source_color(name: str) -> str:
    digest = hashlib.md5(name.encode()).hexdigest()
    idx = int(digest[:8], 16) % len(_VIBRANT_COLORS)
    return _VIBRANT_COLORS[idx]


def badge_tag(source_name: str, color: str = "") -> str:
    if not color:
        color = _source_color(source_name)
    abbr = source_name[:2].upper()
    return f"[bold white on {color}]{abbr}[/]"
