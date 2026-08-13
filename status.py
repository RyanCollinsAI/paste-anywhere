import ctypes
import json
import os
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
STATE_DIR = SCRIPT_DIR / "state"
LOG_FILE = STATE_DIR / "bridge.log"
CLIPS_DIR = Path(os.environ.get("PASTE_ANYWHERE_DIR", str(Path.home() / "Pictures" / "Clips")))

MUTEX_NAME = "Global\\PasteAnywhereMutex"
SYNCHRONIZE = 0x00100000


def is_running():
    handle = ctypes.windll.kernel32.OpenMutexW(SYNCHRONIZE, False, MUTEX_NAME)
    if handle:
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    return False


def parse_log():
    last_capture = None
    today_count = 0
    last_error = None
    today = datetime.now().date()

    if not LOG_FILE.exists():
        return last_capture, today_count, last_error

    with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            ts_str = line.split(" ", 1)[0]
            try:
                ts = datetime.fromisoformat(ts_str)
            except ValueError:
                ts = None
            if "saved and re-set" in line:
                last_capture = ts_str
                if ts is not None and ts.date() == today:
                    today_count += 1
            lowered = line.lower()
            if "failed" in lowered or "error" in lowered or "unhandled" in lowered:
                last_error = line

    return last_capture, today_count, last_error


def clips_stats():
    count = 0
    total_bytes = 0
    if CLIPS_DIR.exists():
        for f in CLIPS_DIR.glob("clip_*.png"):
            try:
                total_bytes += f.stat().st_size
                count += 1
            except OSError:
                continue
    return count, total_bytes / (1024 * 1024)


def main():
    as_json = "--json" in sys.argv[1:]

    running = is_running()
    last_capture, today_count, last_error = parse_log()
    clip_count, clip_mb = clips_stats()

    data = {
        "running": running,
        "last_capture": last_capture,
        "today_capture_count": today_count,
        "clips_file_count": clip_count,
        "clips_total_mb": round(clip_mb, 2),
        "last_error": last_error,
    }

    if as_json:
        print(json.dumps(data))
    else:
        print(f"running: {running}")
        print(f"last capture: {last_capture if last_capture else 'none'}")
        print(f"today's capture count: {today_count}")
        print(f"clips folder: {clip_count} files, {clip_mb:.2f} MB")
        print(f"last error: {last_error if last_error else 'none'}")

    sys.exit(0 if running else 1)


if __name__ == "__main__":
    main()
