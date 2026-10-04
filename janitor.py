"""Sort Downloads into month/type folders. Log every move. Undo last run."""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
LOG_PATH = APP_DIR / "moves.jsonl"
LAST_RUN = APP_DIR / "last_run.txt"

SKIP_EXT = {".crdownload", ".tmp", ".temp", ".part", ".partial", ".download", ".opdownload"}
SKIP_NAMES = {"desktop.ini", "thumbs.db"}

TYPES = {
    "pdf": {".pdf"},
    "images": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".bmp", ".svg"},
    "zips": {".zip", ".rar", ".7z", ".tar", ".gz", ".exe", ".msi"},
    "video": {".mp4", ".mkv", ".mov", ".webm", ".avi"},
    "audio": {".mp3", ".wav", ".flac", ".m4a", ".ogg"},
    "docs": {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv", ".md"},
}

stop_event = threading.Event()
state_lock = threading.Lock()
runtime = {"enabled": True, "last": "starting"}


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        example = APP_DIR / "config.example.json"
        if example.exists():
            CONFIG_PATH.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    data.setdefault("enabled", True)
    data.setdefault("check_seconds", 90)
    data.setdefault("min_age_seconds", 120)
    data.setdefault("downloads", "")
    return data


def save_config(data: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def downloads_dir(cfg: dict) -> Path:
    raw = (cfg.get("downloads") or "").strip()
    if raw:
        return Path(raw)
    return Path.home() / "Downloads"


def kind_for(path: Path) -> str:
    ext = path.suffix.lower()
    for name, exts in TYPES.items():
        if ext in exts:
            return name
    return "other"


def still_hot(path: Path, min_age: int) -> bool:
    try:
        st = path.stat()
    except OSError:
        return True
    if path.suffix.lower() in SKIP_EXT:
        return True
    if path.name.lower() in SKIP_NAMES:
        return True
    if path.name.startswith("."):
        return True
    age = time.time() - max(st.st_mtime, st.st_ctime)
    return age < min_age


def unique_dest(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem, ext = dest.stem, dest.suffix
    n = 2
    while True:
        cand = dest.with_name(f"{stem} ({n}){ext}")
        if not cand.exists():
            return cand
        n += 1


def append_move(run_id: str, src: Path, dst: Path) -> None:
    rec = {
        "run_id": run_id,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "from": str(src),
        "to": str(dst),
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def write_last_run(run_id: str, lines: list[str]) -> None:
    body = [
        f"run {run_id}",
        f"when {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "If something looks wrong: tray -> Undo last run",
        "(only moves files back if they are still where the janitor put them)",
        "",
    ]
    body.extend(lines or ["(nothing moved this run)"])
    LAST_RUN.write_text("\n".join(body) + "\n", encoding="utf-8")


def sweep(force: bool = False) -> int:
    cfg = load_config()
    root = downloads_dir(cfg)
    if not root.is_dir():
        with state_lock:
            runtime["last"] = "no Downloads folder"
        return 0
    min_age = 0 if force else int(cfg.get("min_age_seconds") or 120)
    run_id = uuid.uuid4().hex[:8]
    moved_lines = []
    count = 0
    try:
        entries = list(root.iterdir())
    except OSError:
        return 0
    for item in entries:
        if item.is_dir():
            continue
        if still_hot(item, min_age):
            continue
        month = datetime.fromtimestamp(item.stat().st_mtime).strftime("%Y-%m")
        folder = root / month / kind_for(item)
        try:
            folder.mkdir(parents=True, exist_ok=True)
            dest = unique_dest(folder / item.name)
            shutil.move(str(item), str(dest))
            append_move(run_id, item, dest)
            moved_lines.append(f"{item.name}")
            moved_lines.append(f"  {item}")
            moved_lines.append(f"  -> {dest}")
            moved_lines.append("")
            count += 1
        except OSError:
            continue
    if count or force:
        write_last_run(run_id, moved_lines)
    with state_lock:
        runtime["last"] = f"moved {count}" if count else "idle"
    return count


def last_run_id() -> str | None:
    if not LOG_PATH.exists():
        return None
    rid = None
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rid = json.loads(line).get("run_id")
        except json.JSONDecodeError:
            continue
    return rid


def undo_last_run() -> int:
    rid = last_run_id()
    if not rid:
        with state_lock:
            runtime["last"] = "nothing to undo"
        return 0
    rows = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("run_id") == rid:
            rows.append(rec)
    back = 0
    notes = [f"undo run {rid}", ""]
    for rec in reversed(rows):
        src = Path(rec["to"])
        dst = Path(rec["from"])
        try:
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                dest = unique_dest(dst) if dst.exists() else dst
                shutil.move(str(src), str(dest))
                notes.append(f"back: {src.name} -> {dest}")
                back += 1
            else:
                notes.append(f"skip (already gone): {src}")
        except OSError as e:
            notes.append(f"fail: {src.name} ({e})")
    LAST_RUN.write_text("\n".join(notes) + "\n", encoding="utf-8")
    with state_lock:
        runtime["last"] = f"undid {back}"
    return back


def worker() -> None:
    while not stop_event.is_set():
        try:
            cfg = load_config()
            enabled = bool(cfg.get("enabled", True))
            wait = max(30, int(cfg.get("check_seconds") or 90))
            with state_lock:
                runtime["enabled"] = enabled
            if enabled:
                sweep(force=False)
            else:
                with state_lock:
                    runtime["last"] = "paused"
            stop_event.wait(wait)
        except Exception:
            LAST_RUN.write_text(traceback.format_exc(), encoding="utf-8")
            stop_event.wait(30)


def open_last(_i=None, _item=None) -> None:
    if not LAST_RUN.exists():
        LAST_RUN.write_text("No runs yet.\n", encoding="utf-8")
    try:
        os.startfile(str(LAST_RUN))
    except OSError:
        pass


def open_cfg(_i=None, _item=None) -> None:
    load_config()
    try:
        os.startfile(str(CONFIG_PATH))
    except OSError:
        pass


def set_enabled(icon, value: bool) -> None:
    cfg = load_config()
    cfg["enabled"] = value
    save_config(cfg)
    with state_lock:
        runtime["enabled"] = value
        runtime["last"] = "on" if value else "paused"
    try:
        icon.update_menu()
    except Exception:
        pass


def quit_app(icon, _item=None) -> None:
    stop_event.set()
    icon.stop()


def make_icon():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((10, 8, 54, 56), 6, fill=(70, 110, 180, 255))
    d.rectangle((18, 18, 46, 28), fill="white")
    d.rectangle((18, 34, 38, 42), fill=(230, 230, 230, 255))
    return img


def menu(icon):
    with state_lock:
        en = runtime["enabled"]
        last = runtime["last"]
    return pystray.Menu(
        pystray.MenuItem(f"Status: {last}", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Janitor ON", lambda i, _: set_enabled(i, True), checked=lambda _: en, radio=True),
        pystray.MenuItem("Janitor OFF", lambda i, _: set_enabled(i, False), checked=lambda _: not en, radio=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Run once now", lambda i, _: sweep(force=True)),
        pystray.MenuItem("What it did (last run)", open_last),
        pystray.MenuItem("Undo last run", lambda i, _: undo_last_run()),
        pystray.MenuItem("Settings", open_cfg),
        pystray.MenuItem("Quit", quit_app),
    )


def main() -> None:
    load_config()
    t = threading.Thread(target=worker, daemon=True)
    t.start()
    icon = pystray.Icon(
        "DownloadJanitor",
        make_icon(),
        "Download janitor",
        menu=pystray.Menu(lambda: menu(icon)),
    )
    icon.run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        LAST_RUN.write_text(traceback.format_exc(), encoding="utf-8")
        worker()
