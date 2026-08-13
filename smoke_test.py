import io
import struct
import subprocess
import sys
import time
from pathlib import Path

import win32clipboard
import win32con
from PIL import Image

SCRIPT_DIR = Path(__file__).parent
BRIDGE_SCRIPT = SCRIPT_DIR / "clipboard_bridge.py"

CREATE_NO_WINDOW = 0x08000000

results = []


def check(name, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}")
    results.append(condition)
    return condition


def image_to_dib(img):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "BMP")
    return buf.getvalue()[14:]


def open_clipboard_with_retry(attempts=10, delay=0.1):
    for _ in range(attempts):
        try:
            win32clipboard.OpenClipboard()
            return True
        except Exception:
            time.sleep(delay)
    return False


def set_test_bitmap():
    img = Image.new("RGB", (200, 100), (255, 0, 0))
    dib = image_to_dib(img)
    if not open_clipboard_with_retry():
        raise RuntimeError("could not open clipboard to set test bitmap")
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_DIB, dib)
    finally:
        win32clipboard.CloseClipboard()


def set_plain_text(text):
    if not open_clipboard_with_retry():
        raise RuntimeError("could not open clipboard to set text")
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()


def get_seq_number():
    import ctypes

    return ctypes.windll.user32.GetClipboardSequenceNumber()


def read_clipboard_text():
    if not open_clipboard_with_retry():
        raise RuntimeError("could not open clipboard to read text")
    try:
        return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
    finally:
        win32clipboard.CloseClipboard()


def main():
    proc = subprocess.Popen(
        [sys.executable, str(BRIDGE_SCRIPT)],
        creationflags=CREATE_NO_WINDOW,
    )
    time.sleep(2)

    if proc.poll() is not None:
        print(
            "[FAIL] bridge exited at startup - is a production instance already "
            "running holding the mutex?"
        )
        sys.exit(1)

    try:
        marker_id = win32clipboard.RegisterClipboardFormat("ClipboardBridgeMarker")

        set_test_bitmap()

        deadline = time.time() + 10
        triggered = False
        while time.time() < deadline:
            time.sleep(0.3)
            if not open_clipboard_with_retry():
                continue
            try:
                has_hdrop = win32clipboard.IsClipboardFormatAvailable(win32con.CF_HDROP)
                has_text = win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT)
                has_marker = win32clipboard.IsClipboardFormatAvailable(marker_id)
                has_dib = win32clipboard.IsClipboardFormatAvailable(win32con.CF_DIB)
            finally:
                win32clipboard.CloseClipboard()
            if has_hdrop and has_text and has_marker and has_dib:
                triggered = True
                break

        check("bridge triggered and set CF_HDROP + CF_UNICODETEXT + marker + CF_DIB", triggered)

        if not triggered:
            print("[FAIL] bridge did not trigger - skipping checks that depend on it")
        else:
            path_str = read_clipboard_text()
            saved_path = Path(path_str)
            check("clipboard text is a real file path", saved_path.exists())
            if saved_path.exists():
                try:
                    with Image.open(saved_path) as img:
                        img.load()
                        check(
                            "saved file is a valid 200x100 PNG",
                            img.format == "PNG" and img.size == (200, 100),
                        )
                except Exception as e:
                    check(f"saved file is a valid 200x100 PNG (error: {e})", False)

            seq1 = get_seq_number()
            time.sleep(3)
            seq2 = get_seq_number()
            check("loop prevention: clipboard sequence number unchanged after re-set", seq1 == seq2)
            saved_path.unlink(missing_ok=True)

        test_text = "smoke-test-plain-text-no-touch"
        set_plain_text(test_text)
        time.sleep(2)
        if not open_clipboard_with_retry():
            check("negative test: could open clipboard to verify", False)
        else:
            try:
                has_hdrop_after = win32clipboard.IsClipboardFormatAvailable(win32con.CF_HDROP)
                text_after = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            finally:
                win32clipboard.CloseClipboard()
            check("negative test: bridge did not add CF_HDROP to plain text", not has_hdrop_after)
            check("negative test: plain text unchanged", text_after == test_text)

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    if all(results):
        print("ALL CHECKS PASSED")
        sys.exit(0)
    else:
        print("SOME CHECKS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
