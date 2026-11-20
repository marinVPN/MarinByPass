"""Дизайн-система MarinByPass на Canvas + Pillow.

Поверхности и иконки рендерятся с суперсэмплингом, текст — нативным Tk:
это даёт одинаково чёткую картинку при 100–200 % масштабе Windows.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

import icons
import theme as T
from theme import ft
from ui_render import rounded_photo

from constants import sp


# ------------------------------------------------------------------ helpers


def _pointer(parent) -> str:
    try:
        return parent.cget("bg")
    except Exception:
        return T.BG


def _keep(cv: tk.Canvas, *pics) -> None:
    refs = getattr(cv, "_photo_refs", None)
    if refs is None:
        refs = []
        cv._photo_refs = refs
    refs.extend(pics)


def apply_fonts(root: tk.Tk) -> None:
    T.resolve_fonts(root)


def draw_icon(cv: tk.Canvas, name: str, cx: int, cy: int, size: int,
              color: str, width=1.5) -> None:
    pic = icons.photo(name, int(size), color, width)
    cv.create_image(cx, cy, image=pic, anchor="center")
    _keep(cv, pic)


def draw_dot(cv: tk.Canvas, cx: int, cy: int, diameter: int, color: str) -> None:
    pic = icons.photo("dot", max(4, int(round(diameter / 0.84))), color)
    cv.create_image(cx, cy, image=pic, anchor="center")
    _keep(cv, pic)


def draw_logo(cv: tk.Canvas, cx: int, cy: int, size: int) -> None:
    s = max(8, int(size))
    tile = rounded_photo(s, s, int(round(s * 0.235)), T.ACCENT_FILL)
    cv.create_image(cx - s / 2, cy - s / 2, image=tile, anchor="nw")
    inner = max(8, int(round(s * 0.56)))
    pic = icons.photo("bolt", inner, T.WHITE, 1.4)
    cv.create_image(cx, cy, image=pic, anchor="center")
    _keep(cv, tile, pic)


class _Focusable:
    """Общий каркас клавиатурного фокуса для Canvas-контролов."""

    def _init_focus(self):
        self._focused = False
        self.configure(takefocus=1)
        self.bind("<FocusIn>", self._focus_in, add="+")
        self.bind("<FocusOut>", self._focus_out, add="+")

    def _focus_in(self, _=None):
        self._focused = True
        self.redraw()

    def _focus_out(self, _=None):
        self._focused = False
        self.redraw()


# --------------------------------------------------------------------- panel
class Panel(tk.Canvas):
    """Карточка со скруглёнными углами и произвольным содержимым."""

    def __init__(self, parent, fill=T.CARD, border=T.BORDER, radius=12, pad=0,
                 bg=None, fill_height=False):
        self.parent_bg = bg or _pointer(parent)
        super().__init__(parent, bg=self.parent_bg, height=1,
                         highlightthickness=0, bd=0)
        self.fill = fill
        self.border = border
        self.radius = sp(radius)
        self.pad = sp(pad)
        self.fill_height = fill_height
        self.inner = tk.Frame(self, bg=fill)
        self._win = self.create_window(self.pad, self.pad, anchor="nw",
                                       window=self.inner)
        self.inner.bind("<Configure>", self._on_inner)
        self.bind("<Configure>", self._on_resize)
        self._job = None
        self._size = (0, 0)
        self._img = None
        self.after(0, self._sync)

    def set_border(self, color):
        if color == self.border:
            return
        self.border = color
        self._draw()

    def _sync(self):
        try:
            self._on_inner()
        except Exception:
            pass

    def _on_inner(self, _=None):
        if self.fill_height:
            return
        want = self.inner.winfo_reqheight() + 2 * self.pad
        if want > 2 and want != self.winfo_height():
            self.configure(height=want)

    def _on_resize(self, e=None):
        w, h = self.winfo_width(), self.winfo_height()
        if w - 2 * self.pad > 1:
            self.itemconfigure(self._win, width=w - 2 * self.pad)
        if self.fill_height and h - 2 * self.pad > 1:
            self.itemconfigure(self._win, height=h - 2 * self.pad)
        if self._job:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
        self._job = self.after(10, self._draw)

    def _draw(self):
        self._job = None
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 2 or h <= 2:
            return
        self.delete("surface")
        pic = rounded_photo(w, h, self.radius, self.fill, self.border, 1)
        self.create_image(0, 0, image=pic, anchor="nw", tags="surface")
        self._img = pic
        self.tag_lower("surface")


# ------------------------------------------------------------------- buttons
class RoundButton(tk.Canvas, _Focusable):
    KINDS = {
        "primary": dict(fill=T.ACCENT_FILL, fg=T.WHITE, border=None,
                        hover=T.ACCENT_HOVER, press=T.ACCENT_PRESS),
        "secondary": dict(fill=T.CARD, fg=T.TEXT, border=T.BORDER_STRONG,
                          hover=T.CARD_ALT, press="#ECECF0"),
        "ghost": dict(fill=None, fg=T.TEXT_DIM, border=None,
                      hover="#EFEFF3", press="#E7E7EC"),
        "soft": dict(fill=T.ACCENT_SOFT, fg=T.ACCENT, border=None,
                     hover="#DFEEFE", press="#D3E7FD"),
        "danger": dict(fill=None, fg=T.RED, border=None,
                       hover=T.RED_SOFT, press="#FBE3E6"),
    }

    def __init__(self, parent, text, command=None, width=150, height=34,
                 kind="primary", radius=8, font=None, bg=None, icon=None):
        self.bg = bg or _pointer(parent)
        super().__init__(parent, width=sp(width), height=sp(height), bg=self.bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.font = font or ft("semi", 12.5)
        need = tkfont.Font(font=self.font).measure(text) + sp(30)
        if icon:
            need += sp(18) + sp(7)
        self.w, self.h = max(sp(width), need), sp(height)
        self.configure(width=self.w)
        self.radius = sp(radius)
        self.kind = kind
        self.text = text
        self.icon = icon
        self.command = command
        self.enabled = True
        self._hover = False
        self._press = False
        self._init_focus()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Return>", self._activate)
        self.bind("<space>", self._activate)
        self.redraw()

    def set_text(self, text):
        self.text = text
        self.redraw()

    def set_enabled(self, value: bool):
        self.enabled = bool(value)
        self.configure(cursor="hand2" if self.enabled else "arrow")
        if not self.enabled:
            self._hover = self._press = False
        self.redraw()

    def _on_enter(self, _=None):
        if not self.enabled:
            return
        self._hover = True
        self.redraw()

    def _on_leave(self, _=None):
        self._hover = False
        self._press = False
        self.redraw()

    def _on_press(self, _=None):
        if not self.enabled:
            return
        self._press = True
        self.redraw()

    def _on_release(self, _=None):
        if not self.enabled:
            return
        was = self._press
        self._press = False
        self.redraw()
        if was and self.command:
            self.command()

    def _activate(self, _=None):
        if self.enabled and self.command:
            self.command()

    def redraw(self):
        self.delete("all")
        st = self.KINDS.get(self.kind, self.KINDS["primary"])
        if not self.enabled:
            fill, fg, border = "#E9E9EF", T.FAINT, None
        else:
            fill = st["press"] if self._press else (st["hover"] if self._hover else st["fill"])
            fg = st["fg"]
            border = st["border"]
            if self.kind in ("ghost", "danger") and fill is None:
                fill = self.bg
        pic = rounded_photo(self.w, self.h, self.radius, fill, border, 1)
        self.create_image(0, 0, image=pic, anchor="nw")
        _keep(self, pic)

        dy = 1 if (self._press and self.enabled) else 0
        tx = self.w / 2
        if self.icon:
            ic = sp(15)
            tw = tkfont.Font(font=self.font).measure(self.text)
            total = ic + sp(7) + tw
            draw_icon(self, self.icon, int((self.w - total) / 2 + ic / 2),
                      int(self.h / 2 + dy), int(ic), fg, 1.6)
            tx = (self.w + total) / 2 - tw / 2
        self.create_text(tx, self.h / 2 + dy, text=self.text, fill=fg,
                         font=self.font, anchor="center")
        if self._focused and self.enabled:
            ring = rounded_photo(self.w, self.h, self.radius, None, T.ACCENT, 2)
            self.create_image(0, 0, image=ring, anchor="nw")
            _keep(self, ring)


class NavItem(tk.Canvas, _Focusable):
    def __init__(self, parent, text, icon, command, width=204, height=38, bg=None):
        self.bg = bg or _pointer(parent)
        super().__init__(parent, width=sp(width), height=sp(height), bg=self.bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.w, self.h = sp(width), sp(height)
        self.text = text
        self.icon = icon
        self.command = command
        self.active = False
        self._hover = False
        self._init_focus()
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Button-1>", lambda e: self.command())
        self.bind("<Return>", lambda e: self.command())
        self.bind("<space>", lambda e: self.command())
        self.redraw()

    def _enter(self, _=None):
        self._hover = True
        self.redraw()

    def _leave(self, _=None):
        self._hover = False
        self.redraw()

    def set_active(self, value: bool):
        self.active = bool(value)
        self.redraw()

    def redraw(self):
        self.delete("all")
        if self.active:
            fill = "#E7E7EC"
        elif self._hover:
            fill = "#ECECF1"
        else:
            fill = self.bg
        pic = rounded_photo(self.w, self.h, sp(9), fill)
        self.create_image(0, 0, image=pic, anchor="nw")
        _keep(self, pic)
        col = T.TEXT if self.active else T.TEXT_DIM
        draw_icon(self, self.icon, sp(21), self.h // 2, sp(18),
                  T.ACCENT if self.active else T.MUTED, 1.6)
        self.create_text(sp(43), self.h / 2 + 1, text=self.text, anchor="w",
                         fill=col, font=ft("semi" if self.active else "text", 12.5))
        if self._focused:
            ring = rounded_photo(self.w, self.h, sp(9), None, T.ACCENT, 2)
            self.create_image(0, 0, image=ring, anchor="nw")
            _keep(self, ring)


# --------------------------------------------------------------------- chips
class Chip(tk.Canvas):
    def __init__(self, parent, text, fg=T.TEXT_DIM, bg=None, border=None, height=24,
                 font=None, bg_parent=None, pad=10):
        self.parent_bg = bg_parent or _pointer(parent)
        f = font or ft("text", 11)
        tmp = tkfont.Font(font=f)
        w = tmp.measure(text) + sp(pad * 2)
        super().__init__(parent, width=w, height=sp(height), bg=self.parent_bg,
                         highlightthickness=0, bd=0)
        self.w, self.h = w, sp(height)
        self.text, self.fg, self.font = text, fg, f
        self.bg = bg or T.CARD_ALT
        self.border = border
        self.pad = sp(pad)
        self.redraw()

    def set(self, text=None, fg=None, bg=None):
        if text is not None:
            self.text = text
        if fg is not None:
            self.fg = fg
        if bg is not None:
            self.bg = bg
        self.w = tkfont.Font(font=self.font).measure(self.text) + 2 * self.pad
        self.configure(width=self.w)
        self.redraw()

    def redraw(self):
        self.delete("all")
        pic = rounded_photo(self.w, self.h, self.h // 2, self.bg, self.border, 1)
        self.create_image(0, 0, image=pic, anchor="nw")
        _keep(self, pic)
        self.create_text(self.w / 2, self.h / 2 + 1, text=self.text, fill=self.fg,
                         font=self.font, anchor="center")


# ------------------------------------------------------------------ switches
class Switch(tk.Canvas, _Focusable):
    """Переключатель в духе macOS: синяя дорожка, белый бегунок."""

    def __init__(self, parent, value=False, command=None, width=42, height=25, bg=None):
        self.bg = bg or _pointer(parent)
        super().__init__(parent, width=sp(width), height=sp(height), bg=self.bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.w, self.h = sp(width), sp(height)
        self.value = bool(value)
        self.command = command
        self._pos = 1.0 if self.value else 0.0
        self._job = None
        self._hover = False
        self._init_focus()
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Return>", self._click)
        self.bind("<space>", self._click)
        self.redraw()

    def _enter(self, _=None):
        self._hover = True
        self.redraw()

    def _leave(self, _=None):
        self._hover = False
        self.redraw()

    def _click(self, _=None):
        self.value = not self.value
        self._animate()
        if self.command:
            self.command(self.value)

    def set(self, value, animate=True):
        self.value = bool(value)
        if not animate:
            self._pos = 1.0 if self.value else 0.0
            self.redraw()
            return
        self._animate()

    def _animate(self):
        target = 1.0 if self.value else 0.0
        if self._job:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
        step = 0.2 if target > self._pos else -0.2
        self._pos += step
        if abs(target - self._pos) < 0.02:
            self._pos = target
            self._job = None
        else:
            self._job = self.after(14, self._animate)
        self.redraw()

    def redraw(self):
        self.delete("all")
        w, h = self.w, self.h
        track = T.ACCENT_FILL if self._pos > 0.5 else "#E9E9EA"
        if self._hover:
            track = T.ACCENT_HOVER if self._pos > 0.5 else "#E2E2E7"
        border = None if self._pos > 0.5 else T.BORDER_STRONG
        pic = rounded_photo(w, h, h // 2, track, border, 1)
        self.create_image(0, 0, image=pic, anchor="nw")
        _keep(self, pic)

        r = h // 2 - sp(2)
        x = sp(2) + r + (w - sp(4) - 2 * r) * self._pos
        knob = rounded_photo(2 * r, 2 * r, r, T.WHITE, "#DFDFE4", 1)
        self.create_image(x - r, h / 2 - r, image=knob, anchor="nw")
        _keep(self, knob)
        if self._focused:
            ring = rounded_photo(w, h, h // 2, None, T.ACCENT, 2)
            self.create_image(0, 0, image=ring, anchor="nw")
            _keep(self, ring)


# --------------------------------------------------------------- power button
class PowerControl(tk.Canvas, _Focusable):
    """Главный переключатель защиты: спокойный круг без свечения."""

    def __init__(self, parent, command=None, size=112, bg=None):
        self.bg = bg or _pointer(parent)
        self.size = sp(size)
        super().__init__(parent, width=self.size, height=self.size, bg=self.bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.command = command
        self.on = False
        self.enabled = True
        self.busy = False
        self._hover = False
        self._press = False
        self._angle = 0
        self._spin_job = None
        self._init_focus()
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Button-1>", self._down)
        self.bind("<ButtonRelease-1>", self._up)
        self.bind("<Return>", self._activate)
        self.bind("<space>", self._activate)
        self.redraw()

    def _enter(self, _=None):
        self._hover = True
        self.redraw()

    def _leave(self, _=None):
        self._hover = self._press = False
        self.redraw()

    def _down(self, _=None):
        if not self.enabled or self.busy:
            return
        self._press = True
        self.redraw()

    def _up(self, _=None):
        if not self.enabled or self.busy:
            self._press = False
            self.redraw()
            return
        was = self._press
        self._press = False
        self.redraw()
        if was and self.command:
            self.command()

    def _activate(self, _=None):
        if self.enabled and not self.busy and self.command:
            self.command()

    def set_on(self, value: bool):
        if self.on != bool(value):
            self.on = bool(value)
            self.redraw()

    def set_enabled(self, value: bool):
        self.enabled = bool(value)
        self.configure(cursor="hand2" if self.enabled else "arrow")
        self.redraw()

    def set_busy(self, value: bool):
        self.busy = bool(value)
        if self.busy and not self._spin_job:
            self._spin()
        elif not self.busy and self._spin_job:
            try:
                self.after_cancel(self._spin_job)
            except Exception:
                pass
            self._spin_job = None
        self.redraw()

    def _spin(self):
        self._angle = (self._angle + 24) % 360
        if self.busy:
            self.redraw()
            self._spin_job = self.after(60, self._spin)
        else:
            self._spin_job = None

    def redraw(self):
        self.delete("all")
        d = self.size
        c = d / 2
        if not self.enabled:
            fill, border, glyph = T.CARD_ALT, T.HAIR, T.FAINT
        elif self.busy:
            fill, border, glyph = T.ACCENT_SOFT, T.ACCENT_LINE, T.ACCENT
        elif self.on:
            fill = T.ACCENT_PRESS if self._press else (
                T.ACCENT_HOVER if self._hover else T.ACCENT_FILL)
            border, glyph = None, T.WHITE
        else:
            fill = "#E4E4EA" if self._press else (
                "#ECECF1" if self._hover else T.CARD_ALT)
            border, glyph = T.BORDER_STRONG, T.TEXT
        disc = int(d * 0.80)
        pic = rounded_photo(disc, disc, disc // 2, fill, border, 1)
        self.create_image(c - disc / 2, c - disc / 2, image=pic, anchor="nw")
        _keep(self, pic)
        draw_icon(self, "power", int(c), int(c), int(d * 0.28), glyph, 2.0)
        if self.busy:
            r = disc / 2 + sp(7)
            self.create_arc(c - r, c - r, c + r, c + r, start=self._angle,
                            extent=80, style="arc", outline=T.ACCENT,
                            width=max(1, sp(2)))
        if self._focused:
            ring = rounded_photo(disc + sp(8), disc + sp(8), (disc + sp(8)) // 2,
                                 None, T.ACCENT, 2)
            self.create_image(c - (disc + sp(8)) / 2, c - (disc + sp(8)) / 2,
                              image=ring, anchor="nw")
            _keep(self, ring)


# -------------------------------------------------------------------- cards
class ServiceCard(tk.Canvas):
    """Компактная карточка сервиса: иконка, домен, статус и задержка."""

    ICONS = {"YouTube": "play", "Discord": "chat", "Google": "globe"}
    DOMAINS = {"YouTube": "youtube.com", "Discord": "discord.com",
               "Google": "google.com"}

    def __init__(self, parent, title, width=220, height=104, icon=None):
        self.parent_bg = _pointer(parent)
        super().__init__(parent, width=sp(width), height=sp(height), bg=self.parent_bg,
                         highlightthickness=0, bd=0)
        self.w, self.h = sp(width), sp(height)
        self.title = title
        self.icon = icon or self.ICONS.get(title, "globe")
        self.state = "idle"
        self.detail = "не проверено"
        self.ms = None
        self._hover = False
        self._spin = 0
        self._spin_job = None
        self.bind("<Enter>", lambda e: self.redraw(True))
        self.bind("<Leave>", lambda e: self.redraw(False))
        self.bind("<Configure>", self._on_resize)
        self.redraw()

    def _on_resize(self, e):
        if e.width > sp(80) and abs(e.width - self.w) > 1:
            self.w = e.width
            self.redraw(self._hover)

    def set_state(self, state, detail=None, ms=None):
        self.state = state
        self.detail = detail if detail is not None else self.detail
        self.ms = ms
        if state == "checking":
            if not self._spin_job:
                self._spin_tick()
        elif self._spin_job:
            try:
                self.after_cancel(self._spin_job)
            except Exception:
                pass
            self._spin_job = None
        self.redraw(self._hover)

    def _spin_tick(self):
        self._spin = (self._spin + 24) % 360
        self.redraw(self._hover)
        self._spin_job = self.after(55, self._spin_tick)

    def redraw(self, hover=False):
        self._hover = hover
        self.delete("all")
        border = T.BORDER_STRONG if hover else T.BORDER
        if self.state == "ok":
            border = T.BORDER_STRONG
        elif self.state == "fail":
            border = "#E7C3C7"
        elif self.state == "checking":
            border = T.ACCENT_LINE
        pic = rounded_photo(self.w, self.h, sp(12), T.CARD, border, 1)
        self.create_image(0, 0, image=pic, anchor="nw")
        _keep(self, pic)

        tile = sp(38)
        tx, ty = sp(16), sp(16)
        tile_pic = rounded_photo(tile, tile, sp(10), "#F0F4FA")
        self.create_image(tx, ty, image=tile_pic, anchor="nw")
        _keep(self, tile_pic)
        draw_icon(self, self.icon, tx + tile / 2, ty + tile / 2, sp(19),
                  "#3E6A9E", 1.6)

        self.create_text(tx + tile + sp(12), ty + sp(2), text=self.title,
                         anchor="nw", fill=T.TEXT, font=ft("semi", 13.5))
        self.create_text(tx + tile + sp(12), ty + sp(23),
                         text=self.DOMAINS.get(self.title, ""), anchor="nw",
                         fill=T.MUTED, font=ft("text", 11))
        if self.ms is not None and self.state == "ok":
            self.create_text(self.w - sp(16), ty + sp(3), text=f"{self.ms} мс",
                             anchor="ne", fill=T.MUTED, font=ft("mono", 11))

        y = self.h - sp(18)
        if self.state == "checking":
            r = sp(6)
            self.create_arc(sp(16) - r, y - r, sp(16) + r, y + r, start=self._spin,
                            extent=90, style="arc", outline=T.AMBER,
                            width=max(1, sp(2)))
            txt, col = "проверка…", T.AMBER
        else:
            colors = {"idle": T.FAINT, "ok": T.GREEN_DOT, "fail": T.RED_DOT}
            col = {"idle": T.MUTED, "ok": T.GREEN, "fail": T.RED}.get(self.state, T.MUTED)
            draw_dot(self, sp(20), y, sp(8), colors.get(self.state, T.FAINT))
            if self.state == "ok":
                txt = "доступен"
            elif self.state == "fail":
                txt = self.detail or "нет доступа"
            else:
                txt = "не проверено"
        if self.state != "checking":
            self.create_text(sp(32), y + 1, text=txt, anchor="w", fill=col,
                             font=ft("text", 11.5))
        else:
            self.create_text(sp(32), y + 1, text=txt, anchor="w", fill=col,
                             font=ft("text", 11.5))


class PresetCard(tk.Canvas, _Focusable):
    """Строка списка стратегий: радио, название, бейджи, описание."""

    BADGES = {
        "engine": ("#F0F4FA", "#3E6A9E"),
        "recommended": (T.GREEN_SOFT, T.GREEN),
        "tag": (T.AMBER_SOFT, T.AMBER),
    }

    def __init__(self, parent, preset, command, width=760, height=94,
                 first=False, last=False, bg=None):
        self.parent_bg = bg or _pointer(parent)
        super().__init__(parent, width=sp(width), height=sp(height),
                         bg=self.parent_bg, highlightthickness=0, bd=0, cursor="hand2")
        self.w, self.h = sp(width), sp(height)
        self.preset = preset
        self.command = command
        self.first = first
        self.last = last
        self.selected = False
        self._hover = False
        self._init_focus()
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Button-1>", lambda e: self.command(self.preset))
        self.bind("<Return>", lambda e: self.command(self.preset))
        self.bind("<space>", lambda e: self.command(self.preset))
        self.bind("<Configure>", self._on_resize)
        self.redraw()

    def _on_resize(self, e):
        if e.width > sp(200) and abs(e.width - self.w) > 1:
            self.w = e.width
            self.redraw()

    def _enter(self, _=None):
        self._hover = True
        self.redraw()

    def _leave(self, _=None):
        self._hover = False
        self.redraw()

    def set_selected(self, v):
        self.selected = bool(v)
        self.redraw()

    def redraw(self):
        self.delete("all")
        if self.selected:
            fill = "#F4F9FF"
        elif self._hover:
            fill = "#FAFAFC"
        else:
            fill = T.CARD
        pic = rounded_photo(self.w, self.h, sp(12), fill)
        self.create_image(0, 0, image=pic, anchor="nw")
        _keep(self, pic)
        # у первой/последней строки скругляем только внешние углы
        edge = sp(14)
        if not self.first:
            self.create_rectangle(0, 0, self.w, edge, fill=fill, outline="")
        if not self.last:
            self.create_rectangle(0, self.h - edge, self.w, self.h,
                                  fill=fill, outline="")
        if not self.last:
            self.create_line(sp(52), self.h - 1, self.w - sp(20), self.h - 1,
                             fill=T.HAIR)

        rx, ry = sp(24), sp(26)
        ring_col = T.ACCENT if self.selected else T.BORDER_STRONG
        ring = rounded_photo(sp(18), sp(18), sp(9), None, ring_col, 1)
        self.create_image(rx - sp(9), ry - sp(9), image=ring, anchor="nw")
        _keep(self, ring)
        if self.selected:
            dot = rounded_photo(sp(8), sp(8), sp(4), T.ACCENT)
            self.create_image(rx - sp(4), ry - sp(4), image=dot, anchor="nw")
            _keep(self, dot)

        tx = sp(50)
        title_f = ft("semi", 13.5)
        self.create_text(tx, sp(17), text=self.preset.title, anchor="nw",
                         fill=T.TEXT, font=title_f)
        bw = tx + tkfont.Font(font=title_f).measure(self.preset.title) + sp(10)
        for label, kind in self.preset.badges():
            fg, bg = self.BADGES.get(kind, self.BADGES["engine"])
            f = ft("text", 10.5)
            w = tkfont.Font(font=f).measure(label) + sp(16)
            bpic = rounded_photo(w, sp(19), sp(9), bg)
            self.create_image(bw, sp(10), image=bpic, anchor="nw")
            _keep(self, bpic)
            self.create_text(bw + w / 2, sp(19), text=label, fill=fg, font=f,
                             anchor="center")
            bw += w + sp(6)

        desc_w = max(sp(180), self.w - tx - sp(140))
        self.create_text(tx, sp(42), text=self.preset.desc, anchor="nw",
                         fill=T.MUTED, font=ft("text", 11.5), width=desc_w)

        if self.selected:
            label = "Выбрано"
            tw = tkfont.Font(font=ft("semi", 11.5)).measure(label)
            draw_icon(self, "check", self.w - sp(22) - tw - sp(10),
                      self.h / 2, sp(14), T.ACCENT, 1.8)
            self.create_text(self.w - sp(22), self.h / 2 + 1, text=label,
                             anchor="e", fill=T.ACCENT, font=ft("semi", 11.5))
        if self._focused:
            ring = rounded_photo(self.w, self.h, sp(12), None, T.ACCENT, 2)
            self.create_image(0, 0, image=ring, anchor="nw")
            _keep(self, ring)


# ----------------------------------------------------------------- scrolling
class ScrollFrame(tk.Frame):
    def __init__(self, parent, bg=None, pad_right=0):
        self.bg = bg or _pointer(parent)
        super().__init__(parent, bg=self.bg)
        self.canvas = tk.Canvas(self, bg=self.bg, highlightthickness=0, bd=0)
        self.scroll = VScroll(self, self.canvas.yview, bg=self.bg)
        self.inner = tk.Frame(self.canvas, bg=self.bg)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y", padx=(sp(2), 0))
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        # колесо слушаем глобально, но реагируем только если курсор внутри области
        self.canvas.bind_all("<MouseWheel>", self._wheel, add="+")

    def _on_inner(self, _=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, e):
        self.canvas.itemconfigure(self._win, width=e.width)

    def _wheel(self, e):
        if not self.winfo_ismapped():
            return
        try:
            widget = self.winfo_containing(e.x_root, e.y_root)
        except Exception:
            return
        w = widget
        while w is not None and w is not self.canvas and w is not self.inner:
            w = getattr(w, "master", None)
        if w is None or self.canvas.bbox("all") is None:
            return
        steps = -int(e.delta / 120)
        if steps == 0:
            steps = -1 if e.delta > 0 else 1
        self.canvas.yview_scroll(steps * 3, "units")


class VScroll(tk.Canvas):
    def __init__(self, parent, command, width=8, bg=None):
        self.bg = bg or _pointer(parent)
        super().__init__(parent, width=sp(width), height=sp(100), bg=self.bg,
                         highlightthickness=0, bd=0)
        self.command = command
        self.first, self.last = 0.0, 1.0
        self._drag = None
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag", None))
        self.bind("<Configure>", lambda e: self.redraw())

    def set(self, first, last):
        self.first, self.last = float(first), float(last)
        self.redraw()

    def redraw(self):
        self.delete("all")
        h = self.winfo_height()
        if h <= 2 or self.last - self.first >= 0.999:
            return
        pad = sp(2)
        top = pad + (h - 2 * pad) * self.first
        bot = pad + (h - 2 * pad) * self.last
        w = self.winfo_width()
        pic = rounded_photo(max(2, w - 2 * pad), max(8, int(bot - top)),
                            sp(3), "#C9C9CE")
        self.create_image(pad, top, image=pic, anchor="nw")
        _keep(self, pic)

    def _press(self, e):
        h = self.winfo_height()
        top = sp(2) + (h - 2 * sp(2)) * self.first
        bot = sp(2) + (h - 2 * sp(2)) * self.last
        if top <= e.y <= bot:
            self._drag = (e.y, self.first, self.last)
        else:
            frac = (e.y / h) * (self.last - self.first)
            self.command("moveto", max(0.0, min(1.0, frac)))

    def _motion(self, e):
        if not self._drag:
            return
        y0, first, last = self._drag
        h = self.winfo_height()
        delta = (e.y - y0) / max(1, h - 2 * sp(2)) * (last - first)
        self.command("moveto", max(0.0, min(1.0 - (last - first), first + delta)))


class LogView(tk.Frame):
    def __init__(self, parent, height=8, bg=None):
        box = bg or T.CARD
        super().__init__(parent, bg=box)
        self.text = tk.Text(self, bg=box, fg=T.TEXT_DIM, bd=0, relief="flat",
                            padx=sp(16), pady=sp(12), font=ft("mono", 11),
                            wrap="char", insertbackground=T.ACCENT,
                            spacing1=sp(2), spacing3=sp(2), height=height,
                            selectbackground="#D6E9FF", selectforeground=T.TEXT,
                            highlightthickness=0)
        self.scroll = VScroll(self, self.text.yview, bg=box)
        self.text.configure(yscrollcommand=self.scroll.set)
        self.text.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y", padx=(0, sp(4)), pady=sp(6))
        self._box = box
        self.text.bind("<MouseWheel>", self._wheel)
        self.text.tag_configure("info", foreground=T.TEXT_DIM)
        self.text.tag_configure("ok", foreground=T.GREEN)
        self.text.tag_configure("warn", foreground=T.AMBER)
        self.text.tag_configure("err", foreground=T.RED)
        self.text.tag_configure("accent", foreground=T.ACCENT)
        self.text.tag_configure("muted", foreground=T.MUTED)
        self.text.configure(state="disabled")

    def append(self, line, level="info"):
        self.text.configure(state="normal")
        self.text.insert("end", line + "\n", level)
        if int(self.text.index("end-1c").split(".")[0]) > 2500:
            self.text.delete("1.0", "500.0")
        self.text.configure(state="disabled")
        self.text.see("end")

    def _wheel(self, e):
        steps = -int(e.delta / 120)
        if steps == 0:
            steps = -1 if e.delta > 0 else 1
        self.text.yview_scroll(steps * 3, "units")
        return "break"

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")


class HLine(tk.Canvas):
    def __init__(self, parent, color=T.HAIR, height=1, bg=None):
        self.bg = bg or _pointer(parent)
        super().__init__(parent, height=sp(height), bg=self.bg,
                         highlightthickness=0, bd=0)
        self.color = color
        self.configure(width=10)
        self.bind("<Configure>", self._draw)

    def _draw(self, e=None):
        self.delete("all")
        self.create_line(0, 0, self.winfo_width(), 0, fill=self.color)