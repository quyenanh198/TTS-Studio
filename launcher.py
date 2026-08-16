"""Desktop launcher: start FastAPI on a free localhost port, open pywebview window.

Usage:
    python launcher.py            # desktop window (needs frontend/dist built)
    python launcher.py --dev      # backend only on :8765, use Vite dev server for UI
"""

from __future__ import annotations

import logging
import os
import socket
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("launcher")


def _setup_file_logging() -> None:
    """Also log to <data dir>/logs/app.log — the only trace when run without a console."""
    try:
        from logging.handlers import RotatingFileHandler

        from app.config import DATA_DIR

        logs = DATA_DIR / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        h = RotatingFileHandler(logs / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logging.getLogger().addHandler(h)
    except Exception as exc:  # noqa: BLE001
        log.warning("file logging disabled: %s", exc)


_WEBVIEW2_CLIENT = r"Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"


def _webview2_installed() -> bool:
    """WebView2 Runtime (Evergreen) presence via the registry keys Microsoft documents."""
    if sys.platform != "win32":
        return True
    import winreg

    keys = [
        (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\WOW6432Node\\" + _WEBVIEW2_CLIENT),
        (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\" + _WEBVIEW2_CLIENT),
        (winreg.HKEY_CURRENT_USER, "Software\\" + _WEBVIEW2_CLIENT),
    ]
    for root, sub in keys:
        try:
            with winreg.OpenKey(root, sub) as k:
                pv, _ = winreg.QueryValueEx(k, "pv")
                if pv and pv != "0.0.0.0":
                    return True
        except OSError:
            continue
    return False


def _require_webview2() -> None:
    if _webview2_installed():
        return
    url = "https://developer.microsoft.com/microsoft-edge/webview2/#download-section"
    msg = ("TTS Studio cần Microsoft Edge WebView2 Runtime (có sẵn trên Windows 10/11 mới).\n\n"
           "Bấm OK để mở trang tải, cài xong rồi mở lại ứng dụng.")
    log.error("WebView2 runtime missing")
    try:
        import ctypes
        import webbrowser

        ctypes.windll.user32.MessageBoxW(None, msg, "TTS Studio — thiếu WebView2", 0x40)
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        print(msg, url)
    sys.exit(2)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(port: int) -> None:
    import uvicorn

    from app.main import app

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", loop="asyncio")
    server = uvicorn.Server(config)
    server.run()


def wait_ready(port: int, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def main() -> None:
    dev = "--dev" in sys.argv
    _setup_file_logging()
    if not dev:
        _require_webview2()
    port = 8765 if dev else free_port()
    os.environ["TTS_STUDIO_PORT"] = str(port)

    t = threading.Thread(target=start_server, args=(port,), daemon=True)
    t.start()
    if not wait_ready(port):
        log.error("Backend không khởi động được")
        sys.exit(1)
    log.info("Backend: http://127.0.0.1:%d", port)

    if dev:
        log.info("Dev mode: chạy `npm run dev` trong frontend/, mở http://localhost:5173")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return

    import webview

    dist = ROOT / "frontend" / "dist" / "index.html"
    if not dist.exists():
        log.error("frontend/dist chưa build. Chạy: cd frontend && npm run build")
        sys.exit(1)

    window = webview.create_window(
        "TTS Studio",
        f"http://127.0.0.1:{port}/",
        width=1280,
        height=820,
        min_size=(960, 640),
        background_color="#0f1024",
    )
    _ = window
    from app.config import DATA_DIR

    try:
        webview.start(private_mode=False, storage_path=str(DATA_DIR / "webview"))
    finally:
        # Worker threads are non-daemon: without this, closing the window leaves an invisible
        # pythonw.exe alive until every running job (or a multi-GB pip install) finishes.
        try:
            from app.jobs import jobs

            jobs.shutdown()
        except Exception:  # noqa: BLE001
            pass
        log.info("window closed — exiting")
        os._exit(0)


if __name__ == "__main__":
    main()
