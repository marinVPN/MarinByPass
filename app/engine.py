"""Управление движком обхода DPI, настройками и автозапуском."""
from __future__ import annotations

import ctypes
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import engine_meta
import engine_update
from constants import (
    APP_NAME, CONFIG_DIR, CONFIG_FILE, DATA_DIR, ENGINE_DIR, LOG_DIR, LOG_FILE,
    engine_version, exe_path, res_dir,
)
from engine_update import CORE_FILES
from presets import ENGINE_NAMES, Preset, preset_by_id

CREATE_NO_WINDOW = 0x08000000
TASKSCHED_NAME = "MarinByPass"


# --------------------------------------------------------------------- config
@dataclass
class Config:
    preset: str = "z2-universal"
    extra_args: str = ""
    autostart: bool = False
    auto_enable: bool = True
    start_minimized: bool = True
    debug_log: bool = False
    auto_update_engines: bool = True


def load_config() -> Config:
    try:
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        cfg = Config()
        for k, v in raw.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg
    except Exception:
        return Config()


def save_config(cfg: Config) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        tmp = CONFIG_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(CONFIG_FILE)
    except Exception:
        pass


# --------------------------------------------------------------------- logging
def log_line(text: str) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + text + "\n")
    except Exception:
        pass


# --------------------------------------------------------------------- staging
def _same_bytes(a: Path, b: Path) -> bool:
    try:
        if a.stat().st_size != b.stat().st_size:
            return False
        return a.read_bytes() == b.read_bytes()
    except Exception:
        return False


PRESERVE_PREFIXES = ("zapret/files/", "zapret/windivert.filter/")


def _sync_files(src: Path, dst: Path, rels: list[str], *,
               preserve_existing: bool = False,
               preserve_prefixes: tuple[str, ...] = PRESERVE_PREFIXES) -> bool:
    """Копирует только отличающиеся файлы; занятые идентичные не трогает."""
    ok = True
    for rel in rels:
        key = Path(rel).as_posix()
        target = dst / rel
        if preserve_existing and target.exists():
            if any(key.startswith(p) for p in preserve_prefixes):
                continue
        source = src / rel
        if not source.exists():
            continue
        if target.exists() and _same_bytes(source, target):
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        except OSError:
            # Драйвер WinDivert может быть загружен и занят, даже если обход
            # выключен. Если содержимое совпадает — обновлять нечего.
            if target.exists() and _same_bytes(source, target):
                continue
            ok = False
    return ok


def _sync_tree(src: Path, dst: Path) -> bool:
    rels = [str(p.relative_to(src)) for p in src.rglob("*") if p.is_file()]
    return _sync_files(src, dst, rels, preserve_existing=True,
                       preserve_prefixes=("files/", "windivert.filter/"))


def _restore_missing(src: Path, dst: Path, prefixes: tuple[str, ...]) -> bool:
    """Дополняет недостающие файлы в пользовательских папках."""
    ok = True
    for item in src.rglob("*"):
        if not item.is_file():
            continue
        rel = item.relative_to(src)
        if not any(rel.as_posix().startswith(p) for p in prefixes):
            continue
        target = dst / rel
        if target.exists():
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
        except OSError:
            ok = False
    return ok


def _engine_files(name: str, manifest: dict, src: Path | None = None) -> list[str]:
    """Файлы конкретного движка: из манифеста или минимальный набор."""
    info = manifest.get("engines", {}).get(name) or {}
    files = info.get("files")
    if isinstance(files, dict) and files:
        return sorted(files)
    rels = list(CORE_FILES[name])
    if name == "zapret2" and src:
        rels += ["zapret/lua/" + p.name
                 for p in sorted((src / "zapret" / "lua").glob("*.lua"))]
    return rels


def ensure_engine(repair: bool = False) -> bool:
    """Приводит LOCALAPPDATA к актуальным движкам, не откатывая обновления.

    Если установленные версии новее встроенных, они сохраняются: приложение
    может обновлять движки самостоятельно, а бандл — отставать.
    `repair=True` дополнительно восстанавливает недостающие файлы, не трогая
    более новые движки и пользовательские списки.
    """
    src = res_dir() / "engine"
    if not src.exists():
        return False
    ENGINE_DIR.mkdir(parents=True, exist_ok=True)
    bundled = engine_meta.load_bundled()
    installed = engine_meta.load_installed()
    bv = engine_meta.versions(bundled)
    iv = engine_meta.versions(installed)

    # Первый запуск или установка из старой сборки без манифеста:
    # раскладываем деревья целиком, чтобы появились files/ и windivert.filter/.
    if not bv or not iv:
        ok = True
        for top in ("zapret", "goodbyedpi"):
            if (src / top).exists():
                ok = _sync_tree(src / top, ENGINE_DIR / top) and ok
        if ok:
            if bv:
                engine_update.save_manifest(ENGINE_DIR, bundled)
            else:
                (ENGINE_DIR / engine_meta.MARKER_NAME).write_text(
                    engine_version(), encoding="utf-8")
            return True
        log_line("Не все файлы движков удалось обновить: часть занята. "
                 "Повтор при следующем запуске.")
        return False

    merged = {"schema": 1,
              "engines": dict(installed.get("engines") or {})}
    ok_all = True
    changed = False
    for name in engine_meta.ORDER:
        if name not in bv:
            continue
        newer_local = (name in iv
                       and engine_meta.is_newer(iv[name], bv[name]))
        if newer_local:
            # Автообновление уже поставило версию новее встроенной.
            continue
        need_version = (name not in iv
                        or engine_meta.is_newer(bv[name], iv[name]))
        need_files = any(not (ENGINE_DIR / rel).exists()
                         for rel in CORE_FILES[name])
        if not (repair or need_version or need_files):
            continue
        rels = _engine_files(name, bundled, src)
        if _sync_files(src, ENGINE_DIR, rels):
            merged["engines"][name] = bundled["engines"].get(name) or {}
            changed = True
        else:
            ok_all = False

    if repair and (src / "zapret").exists():
        ok_all = _restore_missing(src / "zapret", ENGINE_DIR / "zapret",
                                  ("files/", "windivert.filter/")) and ok_all

    if changed:
        engine_update.save_manifest(ENGINE_DIR, merged)
    elif ok_all and not (ENGINE_DIR / engine_meta.MANIFEST_NAME).exists():
        engine_update.save_manifest(ENGINE_DIR, installed)
    if not ok_all:
        log_line("Не все файлы движков удалось обновить: часть занята. "
                 "Повтор при следующем запуске.")
    return ok_all


def engine_root(engine: str) -> Path:
    return ENGINE_DIR / ("goodbyedpi" if engine == "goodbyedpi" else "zapret")


# --------------------------------------------------------------------- process
def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return raw.decode("cp866")
        except UnicodeDecodeError:
            return raw.decode("utf-8", errors="replace")


def _kill_tree(pid: int) -> None:
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                       creationflags=CREATE_NO_WINDOW,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
    except Exception:
        pass


def kill_own_stale() -> None:
    """Убивает зависшие процессы движка именно из нашей папки."""
    ps = (
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
        "Get-CimInstance Win32_Process -Filter \"Name='winws.exe' OR Name='winws2.exe' "
        "OR Name='goodbyedpi.exe'\" | Select-Object ProcessId,ExecutablePath | ConvertTo-Json -Compress"
    )
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                             capture_output=True, timeout=15,
                             creationflags=CREATE_NO_WINDOW)
        data = json.loads(_decode(out.stdout or b"").strip() or "[]")
        if isinstance(data, dict):
            data = [data]
        base = str(ENGINE_DIR).lower()
        for item in data:
            path = (item.get("ExecutablePath") or "").lower()
            if path.startswith(base):
                _kill_tree(int(item["ProcessId"]))
    except Exception:
        pass


class EngineManager:
    """Запуск/остановка winws / goodbyedpi с журналом в UI."""

    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.preset: Preset | None = None
        self.started_at: float | None = None
        self.events: queue.Queue = queue.Queue()
        self._reader: threading.Thread | None = None
        self._lock = threading.Lock()

    # -- public --------------------------------------------------------
    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def uptime(self) -> int:
        if not self.is_running() or not self.started_at:
            return 0
        return int(time.time() - self.started_at)

    def command(self, preset: Preset, extra: str, debug: bool) -> tuple[list[str], Path]:
        root = engine_root(preset.engine)
        if preset.engine == "goodbyedpi":
            exe = root / "goodbyedpi.exe"
        elif preset.engine == "zapret2":
            exe = root / "winws2.exe"
        else:
            exe = root / "winws.exe"
        args = preset.args_fn(root)
        if debug and preset.engine != "goodbyedpi":
            args = ["--debug"] + args
        extra = (extra or "").strip()
        if extra:
            args = args + extra.split()
        return [str(exe)] + args, root

    def start(self, preset: Preset, extra: str, debug: bool) -> bool:
        self.stop(silent=True)
        cmd, cwd = self.command(preset, extra, debug)
        if not Path(cmd[0]).exists():
            self.events.put(("error", f"Не найден файл движка: {cmd[0]}"))
            return False
        flags = CREATE_NO_WINDOW
        try:
            proc = subprocess.Popen(
                cmd, cwd=str(cwd),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=flags,
            )
        except Exception as exc:
            self.events.put(("error", f"Не удалось запустить движок: {exc}"))
            return False
        with self._lock:
            self.proc = proc
            self.preset = preset
            self.started_at = time.time()
        self.events.put(("started", f"{ENGINE_NAMES.get(preset.engine, preset.engine)} · {preset.title}"))
        log_line("START " + " ".join(cmd))
        self._reader = threading.Thread(target=self._read, args=(proc,), daemon=True)
        self._reader.start()
        return True

    def stop(self, silent: bool = False) -> None:
        proc = self.proc
        if proc is None:
            return
        with self._lock:
            self.proc = None
            self.started_at = None
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    _kill_tree(proc.pid)
        except Exception:
            _kill_tree(proc.pid)
        log_line("STOP")
        if not silent:
            self.events.put(("stopped", "Защита выключена"))

    def _read(self, proc: subprocess.Popen) -> None:
        try:
            assert proc.stdout is not None
            for raw in iter(proc.stdout.readline, b""):
                line = _decode(raw).rstrip()
                if not line:
                    continue
                low = line.lower()
                if "error" in low or "failed" in low or "cannot" in low:
                    level = "err"
                elif "initialized" in low or "started" in low or "loaded" in low:
                    level = "ok"
                elif "warning" in low or "warn" in low:
                    level = "warn"
                else:
                    level = "info"
                self.events.put(("log", line, level))
        except Exception:
            pass
        code = proc.poll()
        if self.proc is proc:
            # процесс завершился сам
            with self._lock:
                self.proc = None
                self.started_at = None
            self.events.put(("died", code))

    def cleanup(self) -> None:
        self.stop(silent=True)


# --------------------------------------------------------------------- autostart
def _run_hidden(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True,
                          creationflags=CREATE_NO_WINDOW, timeout=25)


def autostart_enabled() -> bool:
    try:
        r = _run_hidden(["schtasks", "/Query", "/TN", TASKSCHED_NAME])
        return r.returncode == 0
    except Exception:
        return False


def set_autostart(enabled: bool) -> tuple[bool, str]:
    try:
        if enabled:
            cmd = exe_path() + " --autostart"
            r = _run_hidden(["schtasks", "/Create", "/TN", TASKSCHED_NAME,
                             "/TR", cmd, "/SC", "ONLOGON", "/RL", "HIGHEST", "/F"])
            if r.returncode != 0:
                msg = _decode(r.stderr or r.stdout or b"").strip()
                return False, msg or "schtasks завершился с ошибкой"
        else:
            _run_hidden(["schtasks", "/Delete", "/TN", TASKSCHED_NAME, "/F"])
        return True, ""
    except Exception as exc:
        return False, str(exc)


# --------------------------------------------------------------------- misc
def open_path(path: Path) -> None:
    try:
        os.startfile(str(path))  # type: ignore[attr-defined]
    except Exception:
        pass


def ensure_dirs() -> None:
    for d in (CONFIG_DIR, DATA_DIR, LOG_DIR):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass


def single_instance() -> bool:
    """True, если это первый запущенный экземпляр."""
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW(None, False, "Global\\MarinByPass_SingleInstance")
        return kernel32.GetLastError() != 183
    except Exception:
        return True
