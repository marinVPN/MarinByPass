"""Проверка запуска всех пресетов движка (dev-утилита)."""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

import engine as eng
from presets import PRESETS

eng.ensure_dirs()
eng.ensure_engine()

for p in PRESETS:
    mgr = eng.EngineManager()
    print("\n=== " + p.id + " (" + p.engine + ") ===", flush=True)
    ok = mgr.start(p, "", False)
    time.sleep(4.0)
    alive = mgr.is_running()
    print("started:", ok, "alive:", alive, flush=True)
    logs = []
    while True:
        try:
            ev = mgr.events.get_nowait()
        except Exception:
            break
        if ev[0] == "log":
            logs.append(ev[1])
        else:
            print("event:", ev, flush=True)
    for line in logs[:14]:
        print("   ", line, flush=True)
    mgr.cleanup()
    time.sleep(1.0)
