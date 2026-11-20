"""Скриншот окна приложения (dev-утилита).

Захватывает реальный пиксель клиентской области через ImageGrab: PrintWindow
на Tk теряет часть вложенных Canvas-виджетов. Окно на время съёмки
поднимается на передний план. Результат кладётся в previews/.
"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parent.parent
PAGE = sys.argv[1] if len(sys.argv) > 1 else "home"
PREVIEW_DIR = ROOT / "previews"
OUT = PREVIEW_DIR / f"{PAGE}.png"
TITLE = "MarinByPass — обход блокировок"

user32 = ctypes.windll.user32

env = os.environ.copy()
env["FDPI_PAGE"] = PAGE
exe = os.environ.get("SHOT_EXE")
cmd = [exe] if exe else [sys.executable, str(ROOT / "app" / "main.py")]
proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env)
hwnd = 0
for _ in range(60):
    time.sleep(0.4)
    hwnd = user32.FindWindowW(None, TITLE)
    if hwnd:
        break
if not hwnd:
    print("window not found, exit code:", proc.poll())
    proc.kill()
    sys.exit(1)

time.sleep(float(os.environ.get("SHOT_WAIT", "1.8")))
res = {}
for attr, val in ((20, 0), (19, 0), (33, 2)):
    v = ctypes.c_int(val)
    res[attr] = ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr,
                                                           ctypes.byref(v), 4)
print("dwm attrs:", res)

SWP = 0x0001 | 0x0002 | 0x0040  # NOSIZE | NOMOVE | SHOWWINDOW
user32.ShowWindow(hwnd, 9)
user32.SetWindowPos(hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, SWP)
user32.SetWindowPos(hwnd, ctypes.c_void_p(-2), 0, 0, 0, 0, SWP)
user32.SetForegroundWindow(hwnd)
time.sleep(0.7)

rect = wintypes.RECT()
user32.GetClientRect(hwnd, ctypes.byref(rect))
pt = wintypes.POINT(0, 0)
user32.ClientToScreen(hwnd, ctypes.byref(pt))
box = (pt.x, pt.y, pt.x + rect.right, pt.y + rect.bottom)
PREVIEW_DIR.mkdir(exist_ok=True)
img = ImageGrab.grab(bbox=box, all_screens=True).convert("RGB")
img.save(OUT)
print("saved", OUT, img.size)

# закрываем по-человечески, чтобы приложение остановило движок
user32.PostMessageW(hwnd, 0x0010, 0, 0)
try:
    proc.wait(10)
except Exception:
    subprocess.run(["taskkill", "/F", "/IM", "MarinByPass.exe"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)