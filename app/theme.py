"""Дизайн-токены MarinByPass.

Одно направление: светлый «системный» интерфейс в духе macOS —
нейтральные поверхности, один синий акцент, hairline-разделители,
никаких градиентов, свечений и стеклянных панелей.

Все размеры берутся из шкалы 4 px и масштабируются через sp()/fs().
"""
from __future__ import annotations

from tkinter import font as tkfont

from constants import fs

# ------------------------------------------------------------------ поверхности
BG = "#FBFBFD"          # холст контента
SIDEBAR = "#F4F4F6"     # боковая панель
CARD = "#FFFFFF"        # карточка
CARD_ALT = "#F5F5F7"    # вложенная поверхность / field
INSET = "#FAFAFC"       # журнал, консоль
SURFACE = "#FFFFFF"

HAIR = "#E5E5EA"        # hairline
HAIR_SOFT = "#EFEFF3"
BORDER = "#E1E1E6"
BORDER_STRONG = "#D2D2D7"

# ----------------------------------------------------------------------- текст
TEXT = "#1D1D1F"
TEXT_DIM = "#48484A"
MUTED = "#6E6E73"
FAINT = "#8E8E93"
WHITE = "#FFFFFF"

# --------------------------------------------------------------------- акценты
ACCENT = "#0066CC"          # текст и иконки
ACCENT_FILL = "#0071E3"     # заливка кнопок
ACCENT_HOVER = "#0077ED"
ACCENT_PRESS = "#0062C4"
ACCENT_SOFT = "#EAF3FF"
ACCENT_LINE = "#B9D7F9"

GREEN = "#197F37"
GREEN_DOT = "#34C759"
GREEN_SOFT = "#EAF7EE"

AMBER = "#B25000"
AMBER_DOT = "#FF9F0A"
AMBER_SOFT = "#FFF4E2"

RED = "#C7162B"
RED_DOT = "#FF3B30"
RED_SOFT = "#FDEDEF"

# ---------------------------------------------------------------------- шрифты
FONTS = {
    "display": "Segoe UI Variable Display",
    "display_semi": "Segoe UI Variable Display Semib",
    "text": "Segoe UI Variable Text",
    "semi": "Segoe UI Variable Text Semibold",
    "mono": "Consolas",
}

_FALLBACK = {
    "display": "Segoe UI",
    "display_semi": "Segoe UI Semibold",
    "text": "Segoe UI",
    "semi": "Segoe UI Semibold",
    "mono": "Consolas",
}


def resolve_fonts(root) -> None:
    """Подбирает лучшие доступные семейства, сохраняя роли шрифтов."""
    try:
        families = set(tkfont.families(root))
    except Exception:
        return
    for role, name in list(FONTS.items()):
        if name in families:
            continue
        fallback = _FALLBACK[role]
        FONTS[role] = fallback if fallback in families else "Tahoma"


def ft(role: str, size: float, minimum: int = 10):
    """Tk-кортеж шрифта: роль + размер в px с учётом масштаба."""
    return (FONTS.get(role, FONTS["text"]), fs(size, minimum))