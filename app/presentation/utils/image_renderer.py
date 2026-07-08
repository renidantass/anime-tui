from __future__ import annotations

import io
from dataclasses import dataclass

import requests
from PIL import Image as PILImage, ImageEnhance

from rich.console import Console, ConsoleOptions, RenderResult
from rich.color import Color
from rich.measure import Measurement
from rich.style import Style
from rich.text import Text


@dataclass
class AnsiImage:
    text: Text
    width: int
    height: int

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        yield self.text

    def __rich_measure__(
        self, console: Console, options: ConsoleOptions
    ) -> Measurement:
        return Measurement(self.width, self.width)


def _download_image(url: str, timeout: int = 10) -> bytes | None:
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.content
    except requests.RequestException:
        return None


def _pixels_to_ansi(
    pixels: list[list[tuple[int, int, int]]],
    target_w: int,
    target_h: int,
) -> Text:
    result = Text()
    for y in range(0, target_h, 2):
        for x in range(target_w):
            top = pixels[y][x]
            bottom = pixels[y + 1][x] if y + 1 < target_h else (0, 0, 0)
            r1, g1, b1 = top
            r2, g2, b2 = bottom
            style = Style(color=Color.from_rgb(r1, g1, b1), bgcolor=Color.from_rgb(r2, g2, b2))
            result.append("\u2580", style=style)
        if y + 2 < target_h:
            result.append("\n")
    return result


def render_image_from_url(
    url: str,
    max_width: int = 20,
) -> AnsiImage | None:
    data = _download_image(url)
    if data is None:
        return None
    try:
        img = PILImage.open(io.BytesIO(data))
    except Exception:
        return None

    if img.width < 10 or img.height < 10:
        return None

    img = img.convert("RGBA")

    background = PILImage.new("RGBA", img.size, (24, 24, 28, 255))
    img = PILImage.alpha_composite(background, img)
    img = img.convert("RGB")

    aspect = img.height / img.width
    target_w = max_width
    target_h = max(2, round(target_w * aspect * 0.5))

    img = img.resize((target_w, target_h), PILImage.LANCZOS)

    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(1.4)

    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.15)

    pixels = list(img.getdata())
    pixel_grid = [
        [pixels[y * target_w + x] for x in range(target_w)]
        for y in range(target_h)
    ]

    text = _pixels_to_ansi(pixel_grid, target_w, target_h)
    return AnsiImage(text=text, width=target_w, height=target_h)
