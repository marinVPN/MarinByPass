"""Общие константы, тема и масштабирование интерфейса."""
from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

APP_NAME = "MarinByPass"
APP_TITLE = "MarinByPass — обход блокировок"
APP_VER = "1.1.0"
APP_TAG = "обход DPI"

# ---------------------------------------------------------------- DPI / scale
_dpi_ready = False


def enable_dpi() -> None:
    global _dpi_ready
    if _dpi_ready:
        return
    _dpi_ready = True
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def detect_scale() -> float:
    try:
        dc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(dc, 88)  # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, dc)
        if dpi:
            return max(1.0, min(2.0, dpi / 96.0))
    except Exception:
        pass
    return 1.0


enable_dpi()
SCALE = detect_scale()


def sp(value: float) -> int:
    """Пиксели с учётом масштаба экрана."""
    return int(round(value * SCALE))


def fs(value: float, minimum: int = 10) -> int:
    """Размер шрифта в пикселях (Tk: отрицательное значение) с учётом DPI."""
    return -max(minimum, int(round(value * SCALE)))


# ---------------------------------------------------------------------- paths
def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def res_dir() -> Path:
    """Каталог с ресурсами (в onefile-сборке — временная папка распаковки)."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base)
    return Path(__file__).resolve().parent.parent


CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
LOG_DIR = DATA_DIR / "logs"
ENGINE_DIR = DATA_DIR / "engine"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE = LOG_DIR / "marinbypass.log"

# Маркер версии движков на случай запуска из неполной копии проекта.
LEGACY_ENGINE_VERSION = "zapret-winbundle+gdi0.2.2"


def engine_version() -> str:
    """Версия упакованных движков: содержимое `engine/version.txt`."""
    try:
        text = (res_dir() / "engine" / "version.txt").read_text(
            encoding="utf-8-sig", errors="ignore").strip()
        if text:
            return text
    except Exception:
        pass
    return LEGACY_ENGINE_VERSION

# ---------------------------------------------------------------------- тема
# Все цвета и шрифты живут в theme.py. Здесь — только чистые утилиты,
# чтобы логика движка не зависела от оформления.


def blend(c1: str, c2: str, t: float) -> str:
    """Смешивает два hex-цвета."""
    t = max(0.0, min(1.0, t))

    def rgb(c: str):
        c = c.lstrip("#")
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)

    r1, g1, b1 = rgb(c1)
    r2, g2, b2 = rgb(c2)
    return "#%02x%02x%02x" % (
        int(r1 + (r2 - r1) * t),
        int(g1 + (g2 - g1) * t),
        int(b1 + (b2 - b1) * t),
    )


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def exe_path() -> str:
    if getattr(sys, "frozen", False):
        return '"' + str(Path(sys.executable).resolve()) + '"'
    return '"' + sys.executable + '" "' + str(Path(sys.argv[0]).resolve()) + '"'
