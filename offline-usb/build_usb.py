#!/usr/bin/env python3
"""Build an offline knowledge USB drive: Wikipedia and survival guides as Kiwix
ZIM archives, the kiwix-serve reader for Windows, macOS and Linux, start
scripts, and a small Swedish emergency portal that opens without any server.

Run it on a computer with internet, pointing --target at an exFAT-formatted
USB drive (or any folder). Run it again later to update: newer editions
replace older ones, finished files are skipped, broken downloads resume.

    python build_usb.py --target E:\\ --tier lite
    python build_usb.py --target /media/me/OFFLINE --tier standard --lang sv,en
    python build_usb.py --target E:\\ --dry-run          # show the plan only
    python build_usb.py --list                           # what is in the catalog

Only the Python standard library is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "catalog.json"
KIT_DIR = HERE / "kit"
DEFAULT_MIRROR = "https://download.kiwix.org"
USER_AGENT = "desk-robot-offline-usb/1.0 (+https://github.com/cgro00/desk-robot)"
CHUNK = 1 << 20
FOUR_GIB = 4 * 1024**3
RETRIES = 4

ZIM_DATE = re.compile(r"_(\d{4}-\d{2})\.zim$")


# ---------------------------------------------------------------- catalog

@dataclass
class Item:
    id: str
    lang: str
    tier: str
    dir: str
    prefixes: list[str]
    title: str
    desc: str = ""
    not_in: list[str] = field(default_factory=list)
    optional: bool = False


@dataclass
class Resolved:
    item: Item
    prefix: str
    file: str
    url: str
    size: int | None


def load_catalog(path: Path = CATALOG) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["items"] = [Item(**{k: v for k, v in i.items()}) for i in data["items"]]
    return data


def select_items(items: list[Item], tiers: list[str], tier: str, langs: list[str],
                 include: set[str] = frozenset(), exclude: set[str] = frozenset()) -> list[Item]:
    """Items for this tier and these languages. --include adds anything by id
    (optional items, other languages, a bigger tier); --exclude wins over all."""
    rank = {t: n for n, t in enumerate(tiers)}
    unknown = (set(include) | set(exclude)) - {i.id for i in items}
    if unknown:
        raise SystemExit(f"Okänt id i katalogen: {', '.join(sorted(unknown))} (se --list)")
    chosen = []
    for i in items:
        if i.id in exclude:
            continue
        default = (not i.optional and i.lang in langs and rank[i.tier] <= rank[tier]
                   and tier not in i.not_in)
        if default or i.id in include:
            chosen.append(i)
    return chosen


# ---------------------------------------------------------------- http

def _request(url: str, method: str = "GET", headers: dict | None = None):
    req = urllib.request.Request(url, method=method,
                                 headers={"User-Agent": USER_AGENT, **(headers or {})})
    return urllib.request.urlopen(req, timeout=60)


def list_links(url: str) -> list[str]:
    """File names linked from an HTTP directory index."""
    with _request(url) as r:
        html = r.read().decode("utf-8", "replace")
    names = []
    for href in re.findall(r'href="([^"?#]+)"', html):
        name = href.rstrip("/").rsplit("/", 1)[-1]
        if name and name not in names:
            names.append(urllib.request.unquote(name))
    return names


def remote_size(url: str) -> int | None:
    try:
        with _request(url, "HEAD") as r:
            n = r.headers.get("Content-Length")
            return int(n) if n else None
    except (urllib.error.URLError, OSError, ValueError):
        return None


def remote_sha256(url: str) -> str | None:
    """Kiwix mirrors publish <file>.sha256 next to every file. Best effort."""
    try:
        with _request(url + ".sha256") as r:
            text = r.read(4096).decode("ascii", "replace")
    except (urllib.error.URLError, OSError):
        return None
    m = re.match(r"\s*([0-9a-fA-F]{64})\b", text)
    return m.group(1).lower() if m else None


# ---------------------------------------------------------------- resolve

def newest_zim(names: list[str], prefix: str) -> str | None:
    pat = re.compile(re.escape(prefix) + r"_(\d{4}-\d{2})\.zim$")
    dated = [(m.group(1), n) for n in names if (m := pat.match(n))]
    return max(dated)[1] if dated else None


def resolve(items: list[Item], mirror: str, with_size: bool = True, log=print) -> tuple[list[Resolved], list[Item]]:
    listings: dict[str, list[str]] = {}
    found, missing = [], []
    for item in items:
        if item.dir not in listings:
            try:
                listings[item.dir] = list_links(f"{mirror}/zim/{item.dir}/")
            except (urllib.error.URLError, OSError) as e:
                log(f"  ! kunde inte läsa {mirror}/zim/{item.dir}/: {e}")
                listings[item.dir] = []
        for prefix in item.prefixes:
            if name := newest_zim(listings[item.dir], prefix):
                url = f"{mirror}/zim/{item.dir}/{name}"
                found.append(Resolved(item, prefix, name, url, remote_size(url) if with_size else None))
                break
        else:
            missing.append(item)
    return found, missing


def newest_kiwix_tools(names: list[str], build: str, ext: str) -> str | None:
    pat = re.compile(r"^kiwix-tools_" + re.escape(build) + r"-(\d+)\.(\d+)\.(\d+)(?:-(\d+))?\." + re.escape(ext) + "$")
    versions = [(tuple(int(g or 0) for g in m.groups()), n) for n in names if (m := pat.match(n))]
    return max(versions)[1] if versions else None


# ---------------------------------------------------------------- download

def human(n: float | None) -> str:
    if n is None:
        return "? B"
    for unit in ("B", "kB", "MB", "GB", "TB"):
        if abs(n) < 1000 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1000
    return f"{n:.1f} TB"


def _hash_file(path: Path, h) -> None:
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)


def download(url: str, dest: Path, size: int | None = None, verify: bool = True, log=print) -> None:
    """Download to dest via dest.part, resuming a partial file, then check the
    size and (if the mirror publishes one) the SHA-256."""
    part = dest.with_name(dest.name + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)
    expected_hash = remote_sha256(url) if verify else None
    h = hashlib.sha256() if expected_hash else None

    have = part.stat().st_size if part.exists() else 0
    if size is not None and have > size:
        part.unlink()
        have = 0
    if h and have:
        log(f"  läser in {human(have)} som redan hämtats ...")
        _hash_file(part, h)

    attempt = 0
    while size is None or have < size:
        headers = {"Range": f"bytes={have}-"} if have else {}
        try:
            with _request(url, headers=headers) as r:
                if have and r.status != 206:            # server ignored Range: start over
                    have = 0
                    h = hashlib.sha256() if expected_hash else None
                    part.unlink(missing_ok=True)
                if size is None:
                    n = r.headers.get("Content-Length")
                    size = have + int(n) if n else None
                mode = "ab" if have else "wb"
                t0, last, start = time.monotonic(), 0.0, have
                with open(part, mode) as f:
                    while chunk := r.read(CHUNK):
                        f.write(chunk)
                        if h:
                            h.update(chunk)
                        have += len(chunk)
                        now = time.monotonic()
                        if now - last > 1:
                            last = now
                            rate = (have - start) / max(now - t0, 1e-6)
                            pct = f"{100 * have / size:5.1f}%" if size else "     "
                            print(f"\r  {pct} {human(have)} / {human(size)}  {human(rate)}/s   ",
                                  end="", flush=True)
            if size is None:
                break
            if have < size:
                raise ConnectionError("anslutningen bröts")
        except urllib.error.HTTPError as e:
            if e.code == 416 and size is not None and have == size:
                break
            raise
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            if isinstance(e, OSError) and e.errno in (27, 22) and have >= FOUR_GIB - CHUNK:
                raise SystemExit(f"\nKan inte skriva filer större än 4 GB på {dest.parent}. "
                                 "Formatera stickan som exFAT (inte FAT32).") from e
            attempt += 1
            if attempt > RETRIES:
                raise
            wait = 2 ** attempt
            print(f"\n  ! {e}; försöker igen om {wait} s (fortsätter där den slutade)")
            time.sleep(wait)
            continue
        attempt = 0
    print()

    if size is not None and part.stat().st_size != size:
        raise RuntimeError(f"{dest.name}: fick {part.stat().st_size} byte, väntade {size}")
    if expected_hash:
        got = h.hexdigest()
        if got != expected_hash:
            part.unlink()
            raise RuntimeError(f"{dest.name}: SHA-256 stämmer inte (filen togs bort, kör igen)")
        log("  SHA-256 ok")
    os.replace(part, dest)


# ---------------------------------------------------------------- kiwix-serve

def install_kiwix_tools(target: Path, mirror: str, builds: dict, log=print) -> None:
    base = f"{mirror}/release/kiwix-tools/"
    names = list_links(base)
    for build, spec in builds.items():
        latest = newest_kiwix_tools(names, build, spec["ext"])
        dest = target / "kiwix" / spec["folder"]
        if not latest:
            log(f"  ! ingen kiwix-tools för {build}")
            continue
        marker = dest / (latest + ".installed")
        if marker.exists():
            log(f"  ok {spec['folder']}: {latest}")
            continue
        with tempfile.TemporaryDirectory(dir=target) as tmp:
            archive = Path(tmp) / latest
            log(f"  hämtar {latest}")
            download(base + latest, archive, remote_size(base + latest), verify=True, log=log)
            install_flat(archive, "kiwix-serve", dest, Path(tmp) / "x")
        marker.touch()


def install_flat(archive: Path, exe: str, dest: Path, scratch: Path) -> None:
    """Unpack archive and copy the folder that holds `exe` to dest."""
    scratch.mkdir(parents=True)
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            z.extractall(scratch)                       # zipfile strips ../ and absolute paths
    else:
        with tarfile.open(archive) as t:
            t.extractall(scratch, filter="data")
    hit = next((p for p in scratch.rglob("*") if p.is_file() and p.name in (exe, exe + ".exe")), None)
    if not hit:
        raise RuntimeError(f"{exe} saknas i {archive.name}")
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(hit.parent, dest)


# ---------------------------------------------------------------- portal

def write_library_index(target: Path, items: list[Item]) -> list[dict]:
    """portal/bibliotek.js lists the archives on the drive for the portal page.
    A .js file (not .json) so it also loads when the page is opened as a file."""
    by_prefix = {p: i for i in items for p in i.prefixes}
    books = []
    for z in sorted((target / "library").glob("*.zim")):
        prefix = ZIM_DATE.sub("", z.name)
        it = by_prefix.get(prefix)
        books.append({
            "file": z.name,
            "book": z.stem,                              # kiwix-serve's URL name: /content/<book>
            "title": it.title if it else prefix,
            "desc": it.desc if it else "",
            "lang": it.lang if it else "",
            "size": z.stat().st_size,
        })
    js = "// Skapad av build_usb.py\nwindow.BIBLIOTEK = " + json.dumps(books, ensure_ascii=False, indent=1) + ";\n"
    (target / "portal").mkdir(parents=True, exist_ok=True)
    (target / "portal" / "bibliotek.js").write_text(js, encoding="utf-8")
    return books


def copy_kit(target: Path) -> None:
    for src in KIT_DIR.rglob("*"):
        if src.is_file():
            out = target / src.relative_to(KIT_DIR)
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, out)
            if src.suffix in (".sh", ".command"):
                try:
                    out.chmod(0o755)
                except OSError:
                    pass                                 # exFAT has no exec bit; the launcher copes
    (target / "egna-filer").mkdir(exist_ok=True)


# ---------------------------------------------------------------- main

def plan_text(found: list[Resolved], missing: list[Item], target: Path | None) -> tuple[str, int]:
    lines, todo = [], 0
    for r in found:
        have = target and (target / "library" / r.file).exists()
        if not have:
            todo += r.size or 0
        mark = "finns" if have else "hämtas"
        lines.append(f"  {mark:7} {human(r.size):>9}  {r.file}")
    for i in missing:
        lines.append(f"  saknas            {i.id}: ingen fil med {', '.join(i.prefixes)}")
    return "\n".join(lines), todo


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Bygg en offline-USB med Wikipedia och överlevnadsguider.")
    ap.add_argument("--target", type=Path, help="USB-stickans rot eller en mapp, t.ex. E:\\ eller /media/me/OFFLINE")
    ap.add_argument("--tier", default="lite", help="lite (~16 GB sticka), standard (~64 GB), full (256 GB+)")
    ap.add_argument("--lang", default="sv,en", help="språk, kommaseparerat: sv,en")
    ap.add_argument("--include", default="", help="extra id:n från katalogen, t.ex. gutenberg-en")
    ap.add_argument("--exclude", default="", help="id:n att hoppa över")
    ap.add_argument("--mirror", default=DEFAULT_MIRROR, help=argparse.SUPPRESS)
    ap.add_argument("--catalog", type=Path, default=CATALOG, help=argparse.SUPPRESS)
    ap.add_argument("--no-verify", action="store_true", help="hoppa över SHA-256-kontrollen")
    ap.add_argument("--skip-tools", action="store_true", help="hämta inte kiwix-serve")
    ap.add_argument("--dry-run", action="store_true", help="visa planen, hämta inget")
    ap.add_argument("--yes", "-y", action="store_true", help="fråga inte innan nedladdning")
    ap.add_argument("--list", action="store_true", help="visa katalogen och avsluta")
    a = ap.parse_args(argv)

    cat = load_catalog(a.catalog)
    if a.list:
        for i in cat["items"]:
            extra = " (valfri)" if i.optional else ""
            print(f"{i.id:24} {i.lang}  {i.tier:8}{extra:9} {i.title}")
        return 0
    if not a.target:
        ap.error("--target behövs")
    if a.tier not in cat["tiers"]:
        ap.error(f"--tier måste vara en av {', '.join(cat['tiers'])}")

    split = lambda s: [x.strip().lower() for x in s.split(",") if x.strip()]
    items = select_items(cat["items"], cat["tiers"], a.tier, split(a.lang),
                         set(split(a.include)), set(split(a.exclude)))
    target: Path = a.target.expanduser()
    mirror = a.mirror.rstrip("/")

    print(f"Letar upp senaste utgåvorna på {mirror} ...")
    found, missing = resolve(items, mirror)
    text, todo = plan_text(found, missing, target if target.exists() else None)
    print(text)
    print(f"\nAtt hämta: {human(todo)}" + ("" if a.skip_tools else " (plus kiwix-serve, cirka 60 MB)"))
    if any((r.size or 0) >= FOUR_GIB for r in found):
        print("Obs: minst en fil är över 4 GB. Stickan måste vara exFAT eller NTFS, inte FAT32.")
    if target.exists():
        free = shutil.disk_usage(target).free
        print(f"Ledigt på {target}: {human(free)}")
        if todo > free:
            print("Får inte plats. Välj en mindre --tier, --exclude något, eller en större sticka.")
            return 2
    if a.dry_run:
        return 0
    if not a.yes and input("\nStarta? [j/N] ").strip().lower() not in ("j", "ja", "y", "yes"):
        return 1

    target.mkdir(parents=True, exist_ok=True)
    copy_kit(target)

    if not a.skip_tools:
        print("\nkiwix-serve (läsaren) för Windows, Mac och Linux")
        install_kiwix_tools(target, mirror, cat["kiwix_tools"])

    lib = target / "library"
    lib.mkdir(exist_ok=True)
    failed = []
    for n, r in enumerate(found, 1):
        dest = lib / r.file
        print(f"\n[{n}/{len(found)}] {r.item.title}  ({r.file}, {human(r.size)})")
        if dest.exists() and (r.size is None or dest.stat().st_size == r.size):
            print("  finns redan")
        else:
            try:
                download(r.url, dest, r.size, verify=not a.no_verify)
            except (RuntimeError, urllib.error.URLError, OSError) as e:
                print(f"  ! misslyckades: {e}")
                failed.append(r.file)
                continue
        for old in lib.glob(f"{r.prefix}_*.zim"):         # older editions of the same archive
            if old.name != r.file and ZIM_DATE.search(old.name):
                old.unlink()
                print(f"  tog bort äldre utgåva {old.name}")

    books = write_library_index(target, cat["items"])
    manifest = {
        "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tier": a.tier, "lang": split(a.lang), "mirror": mirror,
        "books": [b["file"] for b in books], "failed": failed,
    }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")

    print(f"\nKlart: {len(books)} arkiv på {target}.")
    if missing:
        print(f"Fanns inte på servern (hoppades över): {', '.join(i.id for i in missing)}")
    if failed:
        print(f"Misslyckades: {', '.join(failed)}. Kör samma kommando igen så fortsätter den.")
    print("Testa nu: starta START-WINDOWS.bat / START-MAC.command / START-LINUX.sh från stickan.")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nAvbrutet. Kör samma kommando igen så fortsätter nedladdningen.")
        sys.exit(130)
