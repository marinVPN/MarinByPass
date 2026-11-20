"""Проверка и установка обновлений движков из официальных релизов.

Модуль используется двумя путями:
  * приложением — при запуске, в фоновом потоке (см. main.py);
  * `tools/update_engines.py` — вручную, при сборке новой версии.

Обновление всегда проверяется на временном дереве: новые бинарники должны
пройти `--version` и `--dry-run` всех пресетов, и только потом заменяют файлы
в `engine_dir`. Пользовательские `files/` и `windivert.filter/` не трогаются.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from presets import PRESETS

CREATE_NO_WINDOW = 0x08000000
USER_AGENT = "MarinByPass-engine-updater"
GITHUB_API = "https://api.github.com/repos/{repo}/releases/{ref}"
FETCH_TIMEOUT = 8
DOWNLOAD_TIMEOUT = 180


@dataclass(frozen=True)
class Spec:
    name: str
    repo: str
    asset_pattern: str
    title: str
    exe_rel: str


SPECS: dict[str, Spec] = {
    "zapret": Spec(
        "zapret", "bol-van/zapret", r"^zapret-v[\d.]+\.zip$",
        "zapret (winws)", "zapret/winws.exe",
    ),
    "zapret2": Spec(
        "zapret2", "bol-van/zapret2", r"^zapret2-v[\d.]+\.zip$",
        "zapret2 (winws2 + Lua)", "zapret/winws2.exe",
    ),
    "goodbyedpi": Spec(
        "goodbyedpi", "ValdikSS/GoodbyeDPI", r"^goodbyedpi-[\d.]+\.zip$",
        "GoodbyeDPI", "goodbyedpi/goodbyedpi.exe",
    ),
}

CORE_FILES = {
    "zapret": ["zapret/winws.exe"],
    "zapret2": [
        "zapret/winws2.exe", "zapret/cygwin1.dll",
        "zapret/WinDivert.dll", "zapret/WinDivert64.sys",
    ],
    "goodbyedpi": [
        "goodbyedpi/goodbyedpi.exe", "goodbyedpi/WinDivert.dll",
        "goodbyedpi/WinDivert64.sys", "goodbyedpi/russia-blacklist.txt",
    ],
}

# zapret2 владеет общими DLL, поэтому при полном обновлении идёт первым.
UPDATE_ORDER = ("zapret2", "zapret", "goodbyedpi")


# ------------------------------------------------------------------ утилиты
def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def decode(raw: bytes) -> str:
    for enc in ("utf-8", "cp866"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def run(exe: Path, args: list[str], timeout: int = 40) -> tuple[int, str]:
    proc = subprocess.run(
        [str(exe), *args], capture_output=True, timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
    )
    return proc.returncode, decode(proc.stdout + proc.stderr).strip()


def tail(text: str, limit: int = 160) -> str:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return (lines[-1] if lines else "")[:limit]


def version_tuple(value: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", value or "")
    return tuple(int(n) for n in nums[:4]) or (0,)


def tag_to_version(tag: str) -> str:
    return tag.strip().lstrip("vV")


def version_from_filename(name: str) -> str:
    m = re.search(r"v?(\d+(?:\.\d+)+)", name)
    return m.group(1) if m else ""


def parse_version(name: str, out: str) -> str:
    if name == "goodbyedpi":
        m = re.search(r"GoodbyeDPI\s+v?(\d+(?:\.\d+)+)", out, re.I)
    else:
        m = re.search(r"(?:github\s+version|version)\s+v?(\d+(?:\.\d+)+)", out, re.I)
    return m.group(1) if m else ""


# --------------------------------------------------------------- манифест
def manifest_file(engine_dir: Path) -> Path:
    return engine_dir / "version.json"


def marker_file(engine_dir: Path) -> Path:
    return engine_dir / "version.txt"


def load_manifest(engine_dir: Path) -> dict:
    try:
        data = json.loads(manifest_file(engine_dir).read_text(encoding="utf-8-sig"))
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("schema", 1)
    if not isinstance(data.get("engines"), dict):
        data["engines"] = {}
    return data


def save_manifest(engine_dir: Path, data: dict) -> None:
    import engine_meta

    engine_dir.mkdir(parents=True, exist_ok=True)
    data["schema"] = 1
    data["updated"] = date.today().isoformat()
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    tmp = manifest_file(engine_dir).with_suffix(".json.new")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, manifest_file(engine_dir))
    marker_file(engine_dir).write_text(
        engine_meta.marker(data) + "\n", encoding="utf-8", newline="\n")


def owned_files(engine_dir: Path, name: str, from_manifest: bool = True) -> list[str]:
    if from_manifest:
        info = load_manifest(engine_dir).get("engines", {}).get(name) or {}
        files = info.get("files")
        if isinstance(files, dict) and files:
            return sorted(files)
    owned = list(CORE_FILES[name])
    if name == "zapret2":
        owned += ["zapret/lua/" + p.name
                  for p in sorted((engine_dir / "zapret" / "lua").glob("*.lua"))]
    return owned


def file_hashes(engine_dir: Path, files: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for rel in files:
        p = engine_dir / rel
        if p.exists():
            out[rel] = sha256_file(p)
    return out


# ------------------------------------------------------------------ GitHub
def fetch_release(spec: Spec, ref: str = "latest") -> dict:
    url = GITHUB_API.format(repo=spec.repo, ref=ref)
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT, "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        data = json.load(resp)
    if not isinstance(data, dict) or not data.get("tag_name"):
        raise RuntimeError(f"GitHub не вернул релиз для {spec.repo}")
    return data


def pick_asset(release: dict, spec: Spec) -> dict:
    pattern = re.compile(spec.asset_pattern, re.I)
    for asset in release.get("assets") or []:
        if pattern.match(asset.get("name") or ""):
            return asset
    names = ", ".join(a.get("name", "?") for a in release.get("assets") or [])
    raise RuntimeError(
        f"в релизе {release.get('tag_name')} нет zip-архива {spec.name}. "
        f"Доступно: {names}")


def expected_digest(asset: dict | None) -> str:
    digest = (asset or {}).get("digest") or ""
    if digest.lower().startswith("sha256:"):
        return digest.split(":", 1)[1].lower()
    return ""


def download(url: str, dest: Path, log=print) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    part = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp, open(part, "wb") as f:
        shutil.copyfileobj(resp, f)
    os.replace(part, dest)
    log(f"скачан {dest.name} ({dest.stat().st_size / 1048576:.1f} МБ)")


# ------------------------------------------------------------- план файлов
def archive_prefix(zf: zipfile.ZipFile, marker: str) -> str:
    for name in zf.namelist():
        if name.endswith(marker):
            return name[: -len(marker)]
    raise RuntimeError(f"в архиве нет {marker}; структура релиза изменилась")


def build_plan(name: str, zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    """[(путь в архиве, путь относительно engine/)]"""
    present = set(zf.namelist())
    plan: list[tuple[str, str]] = []

    if name == "zapret":
        base = archive_prefix(zf, "binaries/windows-x86_64/winws.exe")
        plan.append((base + "binaries/windows-x86_64/winws.exe", "zapret/winws.exe"))

    elif name == "zapret2":
        base = archive_prefix(zf, "binaries/windows-x86_64/winws2.exe")
        for fname in ("winws2.exe", "cygwin1.dll",
                      "WinDivert.dll", "WinDivert64.sys"):
            src = base + "binaries/windows-x86_64/" + fname
            if src not in present:
                raise RuntimeError(f"в архиве нет {src}")
            plan.append((src, "zapret/" + fname))

        lua_prefix = base + "lua/"
        lua = sorted(n for n in present
                     if n.startswith(lua_prefix) and n.lower().endswith(".lua"))
        if not lua:
            raise RuntimeError("в архиве zapret2 нет lua/*.lua")
        for src in lua:
            plan.append((src, "zapret/lua/" + src[len(lua_prefix):]))

    else:
        base = archive_prefix(zf, "x86_64/goodbyedpi.exe")
        for fname in ("goodbyedpi.exe", "WinDivert.dll", "WinDivert64.sys"):
            src = base + "x86_64/" + fname
            if src not in present:
                raise RuntimeError(f"в архиве нет {src}")
            plan.append((src, "goodbyedpi/" + fname))
        blacklist = base + "russia-blacklist.txt"
        if blacklist in present:
            plan.append((blacklist, "goodbyedpi/russia-blacklist.txt"))

    return plan


def plan_states(engine_dir: Path, plan: list[tuple[str, str]],
                zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    """[(rel, 'новый'|'без изменений'|'старый -> новый Б')]"""
    states = []
    for src, rel in plan:
        dest = engine_dir / rel
        size = zf.getinfo(src).file_size
        if not dest.exists():
            state = "новый"
        elif sha256(zf.read(src)) == sha256_file(dest):
            state = "без изменений"
        else:
            state = f"{dest.stat().st_size} -> {size} Б"
        states.append((rel, state))
    return states


def stage_update(engine_dir: Path, name: str, plan: list[tuple[str, str]],
                 zf: zipfile.ZipFile, tmp: Path) -> Path:
    """Собирает временное дерево движков и раскладывает туда новые файлы."""
    stage_engine = tmp / "engine"
    top = "goodbyedpi" if name == "goodbyedpi" else "zapret"
    shutil.copytree(engine_dir / top, stage_engine / top, dirs_exist_ok=True)
    for src, rel in plan:
        dest = stage_engine / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(zf.read(src))
    return stage_engine


# --------------------------------------------------------------- проверки
def validate_engine(name: str, stage_engine: Path) -> list[str]:
    """Проверяет новые бинарники: --version и --dry-run всех пресетов."""
    notes: list[str] = []
    if name == "goodbyedpi":
        exe = stage_engine / "goodbyedpi" / "goodbyedpi.exe"
        # У GoodbyeDPI нет --version: флаг печатает баннер с версией и код 1.
        _, out = run(exe, ["--version"])
        m = re.search(r"GoodbyeDPI\s+v?(\d+(?:\.\d+)+)", out, re.I)
        if not m:
            raise RuntimeError(f"goodbyedpi.exe не сообщил версию: {tail(out)}")
        notes.append(f"GoodbyeDPI {m.group(1)}")
        return notes

    engine_id = "zapret1" if name == "zapret" else "zapret2"
    exe_name = "winws.exe" if name == "zapret" else "winws2.exe"
    root = stage_engine / "zapret"
    exe = root / exe_name
    code, out = run(exe, ["--version"])
    if code != 0:
        raise RuntimeError(f"{exe_name} --version завершился с кодом {code}: {tail(out)}")
    version = parse_version(name, out)
    notes.append(f"{exe_name} {version or 'версия не распознана'}")

    checked = 0
    for preset in PRESETS:
        if preset.engine != engine_id:
            continue
        args = ["--dry-run", *[str(a) for a in preset.args_fn(root)]]
        code, out = run(exe, args)
        if code != 0:
            raise RuntimeError(
                f"пресет {preset.id} не прошёл dry-run (код {code}): {tail(out)}")
        checked += 1
    notes.append(f"dry-run: {checked} пресет(ов) ок")
    return notes


# ------------------------------------------------------------------ update
def _stage_temp() -> Path:
    base = Path(tempfile.gettempdir()) / "MarinByPass-engine-stage"
    base.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="update-", dir=base))


def _backup_dir(engine_dir: Path, name: str, old_version: str) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    safe = re.sub(r"[^\d.\w-]", "_", old_version or "unknown")
    return (Path(tempfile.gettempdir()) / "MarinByPass-engine-backup"
            / f"{name}-{safe}-{stamp}")


def commit(engine_dir: Path, name: str, plan: list[tuple[str, str]],
           zf: zipfile.ZipFile, old_version: str) -> Path:
    backup = _backup_dir(engine_dir, name, old_version)
    replaced: list[tuple[Path, Path | None]] = []
    for src, rel in plan:
        dest = engine_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = zf.read(src)
        if dest.exists() and sha256(data) == sha256_file(dest):
            continue  # не трогаем занятые и идентичные файлы
        old_copy = None
        if dest.exists():
            old_copy = backup / rel
            old_copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, old_copy)
        tmp = dest.with_name(dest.name + ".new")
        try:
            tmp.write_bytes(data)
            os.replace(tmp, dest)
        except PermissionError as exc:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            _rollback(replaced)
            raise RuntimeError(
                f"не удалось заменить {rel}: файл занят. "
                "Остановите обход в приложении и повторите.") from exc
        except Exception:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            _rollback(replaced)
            raise
        replaced.append((dest, old_copy))
    return backup


def _rollback(replaced: list[tuple[Path, Path | None]]) -> None:
    for dest, old in reversed(replaced):
        try:
            if old is not None and old.exists():
                shutil.copy2(old, dest)
            elif old is None and dest.exists():
                dest.unlink()
        except Exception:
            pass


def update_one(engine_dir: Path, name: str, *, tag_override: str | None = None,
               zip_override: Path | None = None, dry_run: bool = False,
               force: bool = False, log=print) -> dict:
    """Проверяет и устанавливает один движок. Возвращает результат."""
    spec = SPECS[name]
    manifest = load_manifest(engine_dir)
    old_info = manifest.get("engines", {}).get(name) or {}
    old_version = str(old_info.get("version") or "")

    asset: dict | None = None
    if zip_override:
        zip_path = zip_override.resolve()
        if not zip_path.exists():
            raise RuntimeError(f"архив не найден: {zip_path}")
        tag = tag_override or ("v" + version_from_filename(zip_path.name)
                               if name != "goodbyedpi"
                               else version_from_filename(zip_path.name))
        asset_name = zip_path.name
        digest = ""
    else:
        if not tag_override:
            release = fetch_release(spec, "latest")
            tag = release.get("tag_name") or ""
        else:
            tag = tag_override
            try:
                release = fetch_release(spec, "tags/" + tag)
            except Exception:
                release = {"tag_name": tag, "assets": []}
        if not tag:
            raise RuntimeError(f"не удалось определить тег релиза {name}")
        asset = pick_asset(release, spec)
        asset_name = asset.get("name") or ""
        digest = expected_digest(asset)
        zip_path = (Path(tempfile.gettempdir()) / "MarinByPass-engines"
                    / asset_name)
        if zip_path.exists() and (not digest or sha256_file(zip_path) == digest):
            log(f"используется скачанный {asset_name}")
        else:
            download(asset["browser_download_url"], zip_path, log=log)

    version = tag_to_version(tag) or version_from_filename(asset_name)
    if not version:
        raise RuntimeError(f"не удалось определить версию из тега {tag!r}")

    log(f"{spec.title}: {old_version or 'неизвестно'} -> {version} ({tag})")

    if digest:
        actual = sha256_file(zip_path)
        if actual != digest:
            raise RuntimeError(
                f"SHA256 не совпал: ожидалось {digest[:16]}…, получено {actual[:16]}…")
        log(f"SHA256 архива: {actual[:16]}… ок")
    else:
        log(f"SHA256 архива: {sha256_file(zip_path)[:16]}… (сверка с API недоступна)")

    if not force and old_version == version and not dry_run:
        if all((engine_dir / rel).exists() for rel in owned_files(engine_dir, name)):
            log("уже установлено, пропуск (--force для повторной распаковки)")
            return {"name": name, "title": spec.title, "old": old_version,
                    "new": version, "status": "current", "updated": False}

    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise RuntimeError(f"{zip_path.name} — не zip-архив") from exc

    with zf:
        plan = build_plan(name, zf)
        for rel, state in plan_states(engine_dir, plan, zf):
            log(f"  {rel:<34} {state}")
        tmp = _stage_temp()
        try:
            stage = stage_update(engine_dir, name, plan, zf, tmp)
            log("проверка:")
            for note in validate_engine(name, stage):
                log("  " + note)
            if dry_run:
                log("--dry-run: файлы не изменены")
                return {"name": name, "title": spec.title, "old": old_version,
                        "new": version, "status": "dry-run", "updated": False}
            backup = commit(engine_dir, name, plan, zf, old_version)
            if backup.exists():
                log(f"резервная копия: {backup}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        # Манифест фиксирует именно то, что реально лежит в engine/.
        installed = file_hashes(engine_dir, owned_files(engine_dir, name,
                                                        from_manifest=False))
        manifest = load_manifest(engine_dir)
        manifest.setdefault("engines", {})[name] = {
            "version": version,
            "tag": tag,
            "repo": spec.repo,
            "asset": asset_name,
            "sha256": digest or sha256_file(zip_path),
            "files": installed,
        }
        save_manifest(engine_dir, manifest)

    return {"name": name, "title": spec.title, "old": old_version,
            "new": version, "status": "updated", "updated": True}


# ------------------------------------------------------------------- check
def check_updates(engine_dir: Path, log=None) -> list[dict]:
    """Сравнивает установленные движки с последними релизами GitHub.

    Запросы идут параллельно, чтобы запуск приложения не ждал три таймаута
    подряд. Ошибка сети по одному движку не мешает проверить остальные.
    """
    manifest = load_manifest(engine_dir)

    def probe(name: str) -> dict:
        spec = SPECS[name]
        info = manifest.get("engines", {}).get(name) or {}
        local = str(info.get("version") or "")
        if not local:
            try:
                _, out = run(engine_dir / spec.exe_rel, ["--version"])
                local = parse_version(name, out)
            except Exception:
                local = ""
        item = {
            "name": name, "title": spec.title, "local": local,
            "latest": "", "tag": "", "asset": "", "digest": "",
            "url": "", "newer": False, "error": "",
        }
        try:
            release = fetch_release(spec, "latest")
            asset = pick_asset(release, spec)
            item.update(
                tag=release.get("tag_name") or "",
                latest=tag_to_version(release.get("tag_name") or ""),
                asset=asset.get("name") or "",
                digest=expected_digest(asset),
                url=asset.get("browser_download_url") or "",
            )
            item["newer"] = (not local
                             or version_tuple(item["latest"]) > version_tuple(local))
        except Exception as exc:
            item["error"] = str(exc)
        return item

    with ThreadPoolExecutor(max_workers=len(SPECS)) as pool:
        futures = {name: pool.submit(probe, name) for name in SPECS}
        results = []
        for name in SPECS:
            item = futures[name].result()
            if log:
                log(item)
            results.append(item)
    return results