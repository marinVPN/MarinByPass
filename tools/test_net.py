"""Проверка доступности сайтов при работающем движке (dev-утилита)."""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

import engine as eng
from netcheck import SERVICES, _probe
from presets import PRESETS

eng.ensure_engine()
preset_id = sys.argv[1] if len(sys.argv) > 1 else "z2-universal"
preset = next(p for p in PRESETS if p.id == preset_id)

mgr = eng.EngineManager()
mgr.start(preset, "", False)
time.sleep(3)
for name, url in SERVICES:
    ok, ms, detail = _probe(url, timeout=10)
    print(f"{name:10} ok={ok} ms={ms} {detail}", flush=True)
mgr.cleanup()
time.sleep(1)
