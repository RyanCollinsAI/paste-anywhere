import ctypes
import io
import os
import struct
import time
import traceback
from datetime import datetime
from pathlib import Path

import win32clipboard
import win32con
import win32gui
from PIL import ImageGrab

MUTEX_NAME = "Global\\ClipboardBridgeMutex"
MARKER_FORMAT_NAME = "ClipboardBridgeMarker"
MARKER_DATA = b"present"
CLIPS_DIR = Path(os.environ.get("CLIPBOARD_BRIDGE_DIR", str(Path.home() / "Pictures" / "Clips")))
STATE_DIR = Path(__file__).parent / "state"
LOG_FILE = STATE_DIR / "bridge.log"
LOG_MAX_BYTES = 512 * 1024
LOG_KEEP_LINES = 100

marker_format_id = None

TRIM_INTERVAL_SECONDS = 3600
_last_trim_time = 0.0


def log(msg):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}\n"
    f = open(LOG_FILE, "a", encoding="utf-8")
    f.write(line)
    f.close()


def trim_log_if_needed():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not LOG_FILE.exists():
        return
    if LOG_FILE.stat().st_size <= LOG_MAX_BYTES:
        return
    f = open(LOG_FILE, "r", encoding="utf-8", errors="ignore")
    lines = f.readlines()
    f.close()
    tail = lines[-LOG_KEEP_LINES:]
    f = open(LOG_FILE, "w", encoding="utf-8")
    f.writelines(tail)
    f.close()


def maybe_trim_log():
    global _last_trim_time
    now = time.time()
    if now - _last_trim_time < TRIM_INTERVAL_SECONDS:
        return
    trim_log_if_needed()
    _last_trim_time = now


def next_clip_path():
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = CLIPS_DIR / f"clip_{stamp}.png"
    if not base.exists():
        return base
    n = 2
    while True:
        candidate = CLIPS_DIR / f"clip_{stamp}_{n}.png"
        if not candidate.exists():
            return candidate
        n += 1


def image_to_dib(img):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "BMP")
    return buf.getvalue()[14:]


def build_hdrop(path_str):
    header = struct.pack("Iiiii", 20, 0, 0, 0, 1)
    files_bytes = (path_str + "\0\0").encode("utf-16-le")
    return header + files_bytes


def open_clipboard_with_retry(hwnd=None, attempts=10, delay=0.1):
    for i in range(attempts):
        try:
            win32clipboard.OpenClipboard(hwnd)
            return True
        except Exception:
            time.sleep(delay)
    return False


def is_pure_bitmap_clip():
    has_bitmap = win32clipboard.IsClipboardFormatAvailable(
        win32con.CF_DIB
    ) or win32clipboard.IsClipboardFormatAvailable(win32con.CF_BITMAP)
    if not has_bitmap:
        return False
    blockers = [
        win32con.CF_UNICODETEXT,
        win32con.CF_TEXT,
        win32con.CF_HDROP,
    ]
    for fmt in blockers:
        if win32clipboard.IsClipboardFormatAvailable(fmt):
            return False
    for name in ("HTML Format", "Rich Text Format"):
        fmt_id = win32clipboard.RegisterClipboardFormat(name)
        if win32clipboard.IsClipboardFormatAvailable(fmt_id):
            return False
    return True


def handle_clip():
    if not open_clipboard_with_retry():
        log("handle_clip: could not open clipboard to check marker")
        return
    try:
        has_marker = win32clipboard.IsClipboardFormatAvailable(marker_format_id)
        if has_marker:
            return
        if not is_pure_bitmap_clip():
            return
        seq_before = ctypes.windll.user32.GetClipboardSequenceNumber()
    finally:
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass

    img = ImageGrab.grabclipboard()
    if img is None or isinstance(img, list):
        log("handle_clip: grabclipboard returned None or file list, skipping")
        return

    try:
        out_path = next_clip_path()
        img.save(out_path, "PNG")
    except Exception as e:
        log(f"handle_clip: failed to save PNG: {e}")
        return

    try:
        png_bytes = out_path.read_bytes()
        dib_bytes = image_to_dib(img)
        path_str = str(out_path)
        hdrop_bytes = build_hdrop(path_str)
        png_format_id = win32clipboard.RegisterClipboardFormat("PNG")
    except Exception as e:
        log(f"handle_clip: failed to build clipboard payloads: {e}")
        out_path.unlink(missing_ok=True)
        return

    if not open_clipboard_with_retry():
        log("handle_clip: could not open clipboard to re-set data")
        out_path.unlink(missing_ok=True)
        return

    seq_now = ctypes.windll.user32.GetClipboardSequenceNumber()
    if seq_now != seq_before:
        log("handle_clip: clipboard changed during processing, aborting")
        out_path.unlink(missing_ok=True)
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass
        return

    reset_ok = False
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(marker_format_id, MARKER_DATA)
        win32clipboard.SetClipboardData(win32con.CF_DIB, dib_bytes)
        win32clipboard.SetClipboardData(png_format_id, png_bytes)
        win32clipboard.SetClipboardData(win32con.CF_HDROP, hdrop_bytes)
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, path_str)
        log(f"handle_clip: saved and re-set clipboard for {out_path}")
        reset_ok = True
    except Exception as e:
        log(f"handle_clip: failed to set clipboard data (possible race): {e}")
    finally:
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass

    if reset_ok:
        maybe_trim_log()
    else:
        out_path.unlink(missing_ok=True)


def wndproc(hwnd, msg, wparam, lparam):
    if msg == 0x031D:
        try:
            handle_clip()
        except Exception as e:
            log(f"wndproc: unhandled error in handle_clip: {e}")
        return 0
    if msg == win32con.WM_DESTROY:
        win32gui.PostQuitMessage(0)
        return 0
    return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)


def create_message_window():
    wc = win32gui.WNDCLASS()
    wc.lpfnWndProc = wndproc
    wc.lpszClassName = "ClipboardBridgeWindowClass"
    wc.hInstance = win32gui.GetModuleHandle(None)
    class_atom = win32gui.RegisterClass(wc)
    hwnd = win32gui.CreateWindow(
        class_atom,
        "ClipboardBridge",
        0,
        0,
        0,
        0,
        0,
        win32con.HWND_MESSAGE,
        0,
        wc.hInstance,
        None,
    )
    return hwnd


def main():
    global marker_format_id

    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    last_error = ctypes.windll.kernel32.GetLastError()
    if last_error == 183:
        return
    if not mutex:
        log("main: failed to create mutex, exiting")
        return

    try:
        trim_log_if_needed()
        CLIPS_DIR.mkdir(parents=True, exist_ok=True)
        marker_format_id = win32clipboard.RegisterClipboardFormat(MARKER_FORMAT_NAME)

        hwnd = create_message_window()
        ok = ctypes.windll.user32.AddClipboardFormatListener(hwnd)
        if not ok:
            log("main: AddClipboardFormatListener failed")
            return

        log("main: clipboard bridge started")
        win32gui.PumpMessages()
    except Exception:
        log(f"main: unhandled exception, exiting:\n{traceback.format_exc()}")


if __name__ == "__main__":
    main()
