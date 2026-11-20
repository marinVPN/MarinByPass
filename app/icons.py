"""Векторные иконки, отрисованные Pillow с суперсэмплингом.

Набор близок к SF Symbols: тонкая линия, скруглённые окончания,
одинаковая оптическая плотность на всех размерах.
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageTk

_S = 4
_photos: dict[tuple, ImageTk.PhotoImage] = {}


def _line(d, pts, color, w, closed=False, caps=True):
    pts = [(float(x), float(y)) for x, y in pts]
    if closed:
        pts = pts + [pts[0]]
    d.line(pts, fill=color, width=w, joint="curve")
    if caps:
        r = w / 2
        for x, y in (pts[0], pts[-1]):
            d.ellipse((x - r, y - r, x + r, y + r), fill=color)


def _arc_pts(cx, cy, r, a0, a1, steps=48):
    pts = []
    for i in range(steps + 1):
        a = math.radians(a0 + (a1 - a0) * i / steps)
        pts.append((cx + math.cos(a) * r, cy - math.sin(a) * r))
    return pts


def _render(name: str, size: int, color: str, weight: float) -> Image.Image:
    px = max(8, int(size)) * _S
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = px / 2
    s = px / 2
    w = max(1, int(round(weight * _S)))
    cap = w / 2

    def dot(x, y, r=None):
        rr = r if r is not None else cap
        d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=color)

    if name == "home":
        _line(d, [(c - .92 * s, c - .08 * s), (c, c - .92 * s),
                  (c + .92 * s, c - .08 * s)], color, w)
        _line(d, [(c - .68 * s, c - .12 * s), (c - .68 * s, c + .86 * s),
                  (c + .68 * s, c + .86 * s), (c + .68 * s, c - .12 * s)],
              color, w, caps=False)
    elif name == "activity":
        _line(d, [(c - s, c + .1 * s), (c - .55 * s, c + .1 * s),
                  (c - .25 * s, c - .75 * s), (c + .1 * s, c + .75 * s),
                  (c + .4 * s, c - .15 * s), (c + s, c - .15 * s)], color, w)
    elif name == "shield":
        _line(d, [(c, c - s), (c + .85 * s, c - .55 * s),
                  (c + .85 * s, c + .15 * s), (c + .55 * s, c + .62 * s),
                  (c, c + s), (c - .55 * s, c + .62 * s),
                  (c - .85 * s, c + .15 * s), (c - .85 * s, c - .55 * s)],
              color, w, closed=True)
        _line(d, [(c - .3 * s, c + .02 * s), (c - .02 * s, c + .3 * s),
                  (c + .38 * s, c - .34 * s)], color, w)
    elif name == "sliders":
        for yy, kx in ((c - .58 * s, .34), (c, -.3), (c + .58 * s, .46)):
            knob = c + kx * s
            d.line([(c - s, yy), (knob - .2 * s, yy)], fill=color, width=w)
            d.line([(knob + .2 * s, yy), (c + s, yy)], fill=color, width=w)
            dot(knob, yy, .24 * s)
    elif name == "info":
        d.ellipse((c - .94 * s, c - .94 * s, c + .94 * s, c + .94 * s),
                  outline=color, width=w)
        dot(c, c - .5 * s, .08 * s)
        _line(d, [(c, c - .12 * s), (c, c + .5 * s)], color, w)
    elif name == "power":
        pts = _arc_pts(c, c, .82 * s, -60, 240, 72)
        _line(d, pts, color, max(2, w), caps=False)
        dot(pts[0][0], pts[0][1])
        dot(pts[-1][0], pts[-1][1])
        _line(d, [(c, c - .95 * s), (c, c - .02 * s)], color, max(2, w))
    elif name == "bolt":
        d.polygon([(c + .16 * s, c - s), (c - .56 * s, c + .1 * s),
                   (c - .04 * s, c + .1 * s), (c - .22 * s, c + s),
                   (c + .56 * s, c - .08 * s), (c + .05 * s, c - .08 * s)],
                  fill=color)
    elif name == "check":
        _line(d, [(c - .8 * s, c + .02 * s), (c - .16 * s, c + .64 * s),
                  (c + .82 * s, c - .56 * s)], color, max(2, w))
    elif name == "close":
        _line(d, [(c - .66 * s, c - .66 * s), (c + .66 * s, c + .66 * s)],
              color, max(2, w))
        _line(d, [(c + .66 * s, c - .66 * s), (c - .66 * s, c + .66 * s)],
              color, max(2, w))
    elif name == "play":
        _line(d, [(c - .55 * s, c - .82 * s), (c + .82 * s, c),
                  (c - .55 * s, c + .82 * s)], color, w, closed=True)
    elif name == "chat":
        _line(d, [(c - .95 * s, c - .8 * s), (c + .95 * s, c - .8 * s),
                  (c + .95 * s, c + .28 * s), (c + .18 * s, c + .28 * s),
                  (c - .18 * s, c + .72 * s), (c - .18 * s, c + .28 * s),
                  (c - .95 * s, c + .28 * s)], color, w, closed=True)
        _line(d, [(c - .45 * s, c - .18 * s), (c + .45 * s, c - .18 * s)],
              color, w, caps=False)
    elif name == "globe":
        d.ellipse((c - .92 * s, c - .92 * s, c + .92 * s, c + .92 * s),
                  outline=color, width=w)
        d.ellipse((c - .4 * s, c - .92 * s, c + .4 * s, c + .92 * s),
                  outline=color, width=w)
        _line(d, [(c - .92 * s, c), (c + .92 * s, c)], color, w, caps=False)
        _line(d, [(c - .78 * s, c - .46 * s), (c + .78 * s, c - .46 * s)], color, w,
              caps=False)
        _line(d, [(c - .78 * s, c + .46 * s), (c + .78 * s, c + .46 * s)], color, w,
              caps=False)
    elif name == "search":
        d.ellipse((c - .85 * s, c - .85 * s, c + .25 * s, c + .25 * s),
                  outline=color, width=w)
        _line(d, [(c + .15 * s, c + .15 * s), (c + .82 * s, c + .82 * s)], color, w)
    elif name == "refresh":
        pts = _arc_pts(c, c, .8 * s, 55, 325, 56)
        _line(d, pts, color, w, caps=False)
        ex, ey = pts[-1]
        a = math.radians(325)
        tx, ty = -math.sin(a), -math.cos(a)
        _line(d, [(ex - tx * .34 * s - ty * .3 * s, ey - ty * .34 * s + tx * .3 * s),
                  (ex, ey),
                  (ex - tx * .34 * s + ty * .3 * s, ey - ty * .34 * s - tx * .3 * s)],
              color, w)
    elif name == "folder":
        _line(d, [(c - .9 * s, c - .62 * s), (c - .2 * s, c - .62 * s),
                  (c + .02 * s, c - .36 * s), (c + .9 * s, c - .36 * s),
                  (c + .9 * s, c + .66 * s), (c - .9 * s, c + .66 * s)],
              color, w, closed=True)
    elif name == "copy":
        d.rectangle((c - .72 * s, c - .72 * s, c + .42 * s, c + .42 * s),
                    outline=color, width=w)
        _line(d, [(c - .38 * s, c + .72 * s), (c + .72 * s, c + .72 * s),
                  (c + .72 * s, c - .38 * s)], color, w)
        dot(c - .38 * s, c + .72 * s)
        dot(c + .72 * s, c - .38 * s)
    elif name == "trash":
        _line(d, [(c - .8 * s, c - .66 * s), (c + .8 * s, c - .66 * s)], color, w,
              caps=False)
        _line(d, [(c - .28 * s, c - .66 * s), (c - .28 * s, c - .86 * s),
                  (c + .28 * s, c - .86 * s), (c + .28 * s, c - .66 * s)], color, w,
              caps=False)
        _line(d, [(c - .62 * s, c - .5 * s), (c - .52 * s, c + .8 * s),
                  (c + .52 * s, c + .8 * s), (c + .62 * s, c - .5 * s)], color, w)
    elif name == "arrow-right":
        _line(d, [(c - .8 * s, c), (c + .72 * s, c)], color, w)
        _line(d, [(c + .2 * s, c - .5 * s), (c + .75 * s, c),
                  (c + .2 * s, c + .5 * s)], color, w)
    elif name == "chevron-right":
        _line(d, [(c - .3 * s, c - .6 * s), (c + .3 * s, c),
                  (c - .3 * s, c + .6 * s)], color, w)
    elif name == "spark":
        d.polygon([(c, c - s), (c + .22 * s, c - .22 * s), (c + s, c),
                   (c + .22 * s, c + .22 * s), (c, c + s),
                   (c - .22 * s, c + .22 * s), (c - s, c),
                   (c - .22 * s, c - .22 * s)], fill=color)
    elif name == "wifi":
        for r in (.95, .62, .3):
            pts = _arc_pts(c, c + .45 * s, r * s, 35, 145, 32)
            _line(d, pts, color, w, caps=False)
        dot(c, c + .62 * s, .1 * s)
    elif name == "lock":
        pts = _arc_pts(c, c - .24 * s, .48 * s, 0, 180, 32)
        _line(d, pts, color, w, caps=False)
        d.rounded_rectangle((c - .72 * s, c - .1 * s, c + .72 * s, c + .82 * s),
                            radius=max(1, int(.14 * s)), outline=color, width=w)
        _line(d, [(c, c + .24 * s), (c, c + .48 * s)], color, w)
    elif name == "terminal":
        d.rounded_rectangle((c - .92 * s, c - .78 * s, c + .92 * s, c + .78 * s),
                            radius=max(1, int(.16 * s)), outline=color, width=w)
        _line(d, [(c - .5 * s, c - .2 * s), (c - .12 * s, c + .14 * s),
                  (c - .5 * s, c + .48 * s)], color, w)
        _line(d, [(c + .08 * s, c + .48 * s), (c + .56 * s, c + .48 * s)], color, w,
              caps=False)
    elif name == "external":
        _line(d, [(c - .45 * s, c - .62 * s), (c + .62 * s, c - .62 * s),
                  (c + .62 * s, c + .45 * s)], color, w)
        _line(d, [(c + .62 * s, c - .62 * s), (c - .15 * s, c + .15 * s)], color, w)
        _line(d, [(c - .72 * s, c - .28 * s), (c - .72 * s, c + .72 * s),
                  (c + .28 * s, c + .72 * s)], color, w)
    elif name == "plus":
        _line(d, [(c, c - .7 * s), (c, c + .7 * s)], color, w)
        _line(d, [(c - .7 * s, c), (c + .7 * s, c)], color, w)
    elif name == "minus":
        _line(d, [(c - .7 * s, c), (c + .7 * s, c)], color, w)
    elif name == "dot":
        dot(c, c, .42 * s)
    else:
        d.ellipse((c - .7 * s, c - .7 * s, c + .7 * s, c + .7 * s),
                  outline=color, width=w)

    return img.resize((int(size), int(size)), Image.LANCZOS)


def photo(name: str, size: int, color: str, weight: float = 1.5) -> ImageTk.PhotoImage:
    key = (name, int(size), color, round(float(weight), 2))
    pic = _photos.get(key)
    if pic is None:
        pic = ImageTk.PhotoImage(_render(name, size, color, weight))
        _photos[key] = pic
    return pic


def clear_cache() -> None:
    _photos.clear()