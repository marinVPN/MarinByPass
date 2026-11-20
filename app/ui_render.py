"""Сглаженные поверхности и мягкие тени через Pillow.

Tk Canvas не умеет антиалиасинг, поэтому скругления и волосяные границы
рисуются в 3× и уменьшаются LANCZOS. Результат кэшируется по параметрам.
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFilter, ImageTk

_S = 3  # суперсэмплинг

_photo_cache: dict[tuple, ImageTk.PhotoImage] = {}


def _clamp_radius(w: int, h: int, radius: int) -> int:
    return max(0, min(int(radius), min(w, h) // 2))


def _rounded_rgba(w: int, h: int, radius: int, fill: str | None,
                  border: str | None, bw: int) -> Image.Image:
    w, h = max(1, int(w)), max(1, int(h))
    r = _clamp_radius(w, h, radius)
    img = Image.new("RGBA", (w * _S, h * _S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if border and bw > 0:
        inset = max(1, bw * _S // 2)
        d.rounded_rectangle(
            (inset, inset, w * _S - 1 - inset, h * _S - 1 - inset),
            radius=max(0, r * _S - inset),
            fill=fill,
            outline=border,
            width=max(1, bw * _S),
        )
    else:
        d.rounded_rectangle((0, 0, w * _S - 1, h * _S - 1), radius=r * _S, fill=fill)
    return img.resize((w, h), Image.LANCZOS)


def rounded_photo(w: int, h: int, radius: int, fill: str | None,
                  border: str | None = None, bw: int = 1) -> ImageTk.PhotoImage:
    """Сглаженный прямоугольник с опциональной границей (кэшируется)."""
    key = ("r", int(w), int(h), int(radius), fill, border, int(bw))
    photo = _photo_cache.get(key)
    if photo is None:
        img = _rounded_rgba(w, h, radius, fill, border, bw)
        photo = ImageTk.PhotoImage(img)
        _photo_cache[key] = photo
    return photo


def shadow_photo(w: int, h: int, radius: int, fill: str,
                 border: str | None = None, blur: int = 18,
                 alpha: float = 0.12, dy: int = 6,
                 bw: int = 1) -> tuple[ImageTk.PhotoImage, int]:
    """Карточка с мягкой тенью. Возвращает (photo, отступ тени)."""
    w, h = max(1, int(w)), max(1, int(h))
    pad = max(2, int(blur * 1.2))
    W, H = (w + 2 * pad) * _S, (h + 2 * pad) * _S
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    shade = Image.new("L", (W, H), 0)
    ImageDraw.Draw(shade).rounded_rectangle(
        (pad * _S, (pad + dy) * _S, (pad + w) * _S, (pad + dy + h) * _S),
        radius=_clamp_radius(w, h, radius) * _S,
        fill=int(255 * alpha),
    )
    shade = shade.filter(ImageFilter.GaussianBlur(blur * _S * 0.45))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.putalpha(shade)
    canvas.alpha_composite(layer)

    # карточка рисуется сразу в суперсэмплинге, иначе она вклеится в 1/3 размера
    card = Image.new("RGBA", (w * _S, h * _S), (0, 0, 0, 0))
    dc = ImageDraw.Draw(card)
    r = _clamp_radius(w, h, radius) * _S
    if border and bw > 0:
        inset = max(1, int(bw) * _S // 2)
        dc.rounded_rectangle(
            (inset, inset, w * _S - 1 - inset, h * _S - 1 - inset),
            radius=max(0, r - inset),
            fill=fill,
            outline=border,
            width=max(1, int(bw) * _S),
        )
    else:
        dc.rounded_rectangle((0, 0, w * _S - 1, h * _S - 1), radius=r, fill=fill)
    canvas.alpha_composite(card, (pad * _S, pad * _S))
    photo = ImageTk.PhotoImage(canvas.resize((w + 2 * pad, h + 2 * pad), Image.LANCZOS))
    return photo, pad


def clear_cache() -> None:
    _photo_cache.clear()