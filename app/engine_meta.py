"""Метаданные движков: что упаковано и что реально установлено.

`engine/version.json` в ресурсах — версии, с которыми собрано приложение.
`%LOCALAPPDATA%\\MarinByPass\\engine\\version.json` — фактически установленные
версии; при автоматическом обновлении они могут быть новее встроенных.
`version.txt` — короткий маркер для совместимости и быстрой проверки.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from constants import ENGINE_DIR, res_dir

MANIFEST_NAME = "version.json"
MARKER_NAME = "version.txt"
LEGACY_MARKER = "zapret-winbundle+gdi0.2.2"
ORDER = ("zapret", "zapret2", "goodbyedpi")


def bundled_dir() -> Path:
    return res_dir() / "engine"


def manifest_path() -> Path:
    return bundled_dir() / MANIFEST_NAME


def installed_manifest_path() -> Path:
    return ENGINE_DIR / MANIFEST_NAME


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def load_bundled() -> dict:
    return _read(manifest_path())


def load_installed() -> dict:
    return _read(installed_manifest_path())


def load() -> dict:
    """Для интерфейса: установленный манифест важнее встроенного."""
    installed = load_installed()
    return installed if versions(installed) else load_bundled()


def versions(manifest: dict | None = None) -> dict[str, str]:
    data = load() if manifest is None else manifest
    engines = data.get("engines") or {}
    out: dict[str, str] = {}
    if isinstance(engines, dict):
        for name in ORDER:
            info = engines.get(name)
            if isinstance(info, dict) and info.get("version"):
                out[name] = str(info["version"]).strip()
    return out


def version_tuple(value: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", value or "")
    return tuple(int(n) for n in nums[:4]) or (0,)


def is_newer(candidate: str, current: str) -> bool:
    return version_tuple(candidate) > version_tuple(current)


def marker(manifest: dict | None = None) -> str:
    """Компактный маркер вида `zapret=72.13;zapret2=1.0.7;goodbyedpi=0.2.2`."""
    v = versions(manifest)
    parts = [f"{name}={v[name]}" for name in ORDER if name in v]
    return ";".join(parts) or LEGACY_MARKER


def version_line(manifest: dict | None = None) -> str:
    """Строка для журнала и раздела «О программе»."""
    v = versions(manifest)
    parts: list[str] = []
    if "zapret" in v:
        parts.append("zapret winws " + v["zapret"])
    if "zapret2" in v:
        parts.append("winws2 " + v["zapret2"])
    line = " / ".join(parts)
    if "goodbyedpi" in v:
        line += (" · " if line else "") + "GoodbyeDPI " + v["goodbyedpi"]
    return line or "встроенные движки"