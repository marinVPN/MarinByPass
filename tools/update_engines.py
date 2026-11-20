"""Обновление движков MarinByPass из официальных релизов (dev-утилита).

Тот же код, что использует приложение при автоматической проверке, но здесь
есть CLI, офлайн-архивы, выбор тега и bootstrap манифеста.

Примеры:
    python tools/update_engines.py --check
    python tools/update_engines.py --init
    python tools/update_engines.py --update zapret
    python tools/update_engines.py --update all
    python tools/update_engines.py --update zapret --tag v72.13
    python tools/update_engines.py --update zapret --zip zapret=C:\\tmp\\zapret-v72.13.zip
    python tools/update_engines.py --update zapret2 --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "engine"
sys.path.insert(0, str(ROOT / "app"))

import engine_update as EU  # noqa: E402


# ------------------------------------------------------------------- check
def check_one(name: str) -> None:
    spec = EU.SPECS[name]
    manifest = EU.load_manifest(ENGINE)
    info = manifest.get("engines", {}).get(name) or {}
    local = str(info.get("version") or "")
    if not local:
        try:
            _, out = EU.run(ENGINE / spec.exe_rel, ["--version"])
            local = EU.parse_version(name, out)
        except Exception:
            local = ""

    print(f"\n{spec.title}")
    print(f"  в приложении: {local or 'не установлено'}")
    if local:
        broken = []
        for rel, want in (info.get("files") or {}).items():
            p = ENGINE / rel
            if not p.exists():
                broken.append(rel + " отсутствует")
            elif EU.sha256_file(p) != want:
                broken.append(rel + " изменён")
        print("  целостность: " + ("ок" if not broken else "; ".join(broken)))

    item = next((u for u in EU.check_updates(ENGINE) if u["name"] == name), {})
    if item.get("error"):
        print(f"  ! не удалось проверить GitHub: {item['error']}")
        return
    print(f"  последний релиз: {item['tag']} ({item['asset']})")
    if not local:
        print("  -> движок не установлен, есть что завозить")
    elif item["newer"]:
        print("  -> доступно обновление")
    elif EU.version_tuple(item["latest"]) < EU.version_tuple(local):
        print("  -> локальная версия новее релиза")
    else:
        print("  -> обновлений нет")
    if item["digest"]:
        print(f"  SHA256 релиза: {item['digest'][:16]}…")


# -------------------------------------------------------------------- init
def init_manifest() -> None:
    manifest = EU.load_manifest(ENGINE)
    engines = manifest.setdefault("engines", {})
    for name, spec in EU.SPECS.items():
        exe = ENGINE / spec.exe_rel
        if not exe.exists():
            print(f"{spec.title}: нет {exe}, пропуск")
            continue
        try:
            _, out = EU.run(exe, ["--version"])
        except Exception as exc:
            print(f"{spec.title}: не удалось определить версию: {exc}")
            continue
        version = EU.parse_version(name, out)
        if not version:
            print(f"{spec.title}: версия не распознана: {EU.tail(out)}")
            continue
        tag = version if name == "goodbyedpi" else "v" + version
        asset = (f"goodbyedpi-{version}.zip" if name == "goodbyedpi"
                 else f"{name}-v{version}.zip")
        engines[name] = {
            "version": version,
            "tag": tag,
            "repo": spec.repo,
            "asset": asset,
            "sha256": None,
            "files": EU.file_hashes(
                ENGINE, EU.owned_files(ENGINE, name, from_manifest=False)),
        }
        print(f"{spec.title}: {version} ({tag})")
    EU.save_manifest(ENGINE, manifest)
    print(f"манифест: {EU.manifest_file(ENGINE)}")
    print(f"маркер:   {EU.marker_file(ENGINE)}")


# -------------------------------------------------------------------- CLI
def parse_named(items: list[str], targets: list[str], flag: str) -> dict[str, str]:
    out: dict[str, str] = {}
    plain: list[str] = []
    for item in items:
        if "=" in item:
            key, value = item.split("=", 1)
            out[key.strip()] = value.strip()
        else:
            plain.append(item)
    if plain:
        if len(targets) != 1:
            raise SystemExit(f"{flag}: укажите {flag} имя=значение для каждого движка")
        out[targets[0]] = plain[0]
    unknown = set(out) - set(targets)
    if unknown:
        raise SystemExit(f"{flag}: неизвестный движок {', '.join(sorted(unknown))}")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Обновление движков MarinByPass из официальных релизов.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true",
                        help="сравнить установленные версии с последними релизами")
    action.add_argument("--init", action="store_true",
                        help="создать version.json по текущим файлам engine/")
    action.add_argument("--update", choices=[*EU.SPECS, "all"],
                        help="обновить выбранный движок или все сразу")
    parser.add_argument("--tag", action="append", default=[], metavar="[ИМЯ=]ТЕГ",
                        help="конкретный релиз вместо latest (можно повторять)")
    parser.add_argument("--zip", action="append", default=[], metavar="[ИМЯ=]ПУТЬ",
                        help="локальный архив вместо скачивания")
    parser.add_argument("--dry-run", action="store_true",
                        help="скачать и проверить, но не менять engine/")
    parser.add_argument("--force", action="store_true",
                        help="переустановить файлы, даже если версия совпадает")
    args = parser.parse_args(argv)

    if args.check:
        for name in EU.SPECS:
            check_one(name)
        return 0

    if args.init:
        init_manifest()
        return 0

    targets = list(EU.SPECS) if args.update == "all" else [args.update]
    tags = parse_named(args.tag, targets, "--tag")
    zips = parse_named(args.zip, targets, "--zip")

    failed = 0
    for name in [n for n in EU.UPDATE_ORDER if n in targets]:
        print(f"\n=== {EU.SPECS[name].title} ===")
        try:
            result = EU.update_one(
                ENGINE, name,
                tag_override=tags.get(name),
                zip_override=Path(zips[name]) if name in zips else None,
                dry_run=args.dry_run,
                force=args.force,
                log=lambda msg: print("  " + str(msg)),
            )
            if result["status"] == "updated":
                print(f"  установлено: {result['title']} {result['new']}")
                print(f"  манифест: {EU.manifest_file(ENGINE)}")
        except Exception as exc:
            failed += 1
            print(f"  ошибка: {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())