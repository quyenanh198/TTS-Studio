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


def _ensure_std_streams() -> None:
    """Under pythonw.exe (no console) sys.stdout/stderr are None; anything that writes to them
    (uvicorn's default log config uses ext://sys.stderr) raises. Point them at a log file."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        from app.config import DATA_DIR

        logs = DATA_DIR / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        stream = open(logs / "stdio.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
    except Exception:  # noqa: BLE001
        stream = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


_ensure_std_streams()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("launcher")
_server_error: list[str] = []


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


def _fatal(msg: str, code: int = 1) -> None:
    """Show a message box (GUI mode) and exit — never die silently under pythonw."""
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, msg, "TTS Studio — lỗi khởi động", 0x10)
        except Exception:  # noqa: BLE001
            pass
    print(msg, file=sys.stderr)
    sys.exit(code)


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


def _kill_orphan_webview(storage: Path) -> None:
    """Terminate msedgewebview2.exe processes bound to our profile dir. Killing pythonw does not kill
    them, and while they live the profile is locked and a new window closes instantly."""
    if sys.platform != "win32":
        return
    try:
        import subprocess

        needle = str(storage).replace("'", "''")
        ps = ("Get-CimInstance Win32_Process -Filter \"name='msedgewebview2.exe'\" | "
              f"Where-Object {{ $_.CommandLine -like '*{needle}*' }} | "
              "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True,
                       timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as exc:  # noqa: BLE001
        log.debug("orphan cleanup skipped: %s", exc)


def _rotate_dir(path: Path) -> None:
    """Move a possibly-corrupt directory aside (path -> path.bak), replacing an older .bak."""
    import shutil

    if not path.exists():
        return
    bak = path.with_name(path.name + ".bak")
    shutil.rmtree(bak, ignore_errors=True)
    try:
        path.rename(bak)
    except OSError:
        shutil.rmtree(path, ignore_errors=True)


def _pid_alive(pid: int) -> bool:
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes

    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    ctypes.windll.kernel32.CloseHandle(handle)
    return True


def _acquire_single_instance() -> bool:
    """One window per user: a second launch just exits (the first window is already there)."""
    from app.config import DATA_DIR

    lock = DATA_DIR / "app.lock"
    try:
        old = int(lock.read_text().strip() or 0)
        if old and old != os.getpid() and _pid_alive(old):
            return False
    except (OSError, ValueError):
        pass
    lock.write_text(str(os.getpid()), encoding="utf-8")
    return True


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(port: int) -> None:
    try:
        import uvicorn

        from app.main import app

        # log_config=None: skip uvicorn's dictConfig (it references sys.stderr, which pythonw lacks);
        # our root logger already has console/file handlers.
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", loop="asyncio",
                                log_config=None)
        server = uvicorn.Server(config)
        server.run()
    except Exception:  # noqa: BLE001
        import traceback

        tb = traceback.format_exc()
        _server_error.append(tb)
        log.error("backend crashed: %s", tb)


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
        if not _acquire_single_instance():
            log.info("another instance is running — exiting")
            return
    port = 8765 if dev else free_port()
    os.environ["TTS_STUDIO_PORT"] = str(port)

    t = threading.Thread(target=start_server, args=(port,), daemon=True)
    t.start()
    if not wait_ready(port):
        detail = _server_error[0][-1500:] if _server_error else "Không rõ nguyên nhân (xem logs/app.log)"
        log.error("Backend không khởi động được: %s", detail)
        _fatal("Backend không khởi động được. Chi tiết:  " + detail)
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
        _fatal("Thiếu giao diện (frontend/dist). Hãy cài đặt lại ứng dụng.")

    from app.config import DATA_DIR

    storage = DATA_DIR / "webview"
    _kill_orphan_webview(storage)  # renderers left by a force-killed instance keep the profile locked

    exit_code = 0
    try:
        for attempt in (1, 2):
            window = webview.create_window(
                "TTS Studio",
                f"http://127.0.0.1:{port}/",
                width=1280,
                height=820,
                min_size=(960, 640),
                background_color="#0f1024",
            )
            state = {"loaded": False}

            def _on(name: str):
                def handler(*_a: object) -> None:
                    log.info("window %s", name)
                    if name == "loaded":
                        state["loaded"] = True
                return handler

            for ev in ("shown", "loaded", "closing", "closed"):
                evt = getattr(window.events, ev)
                evt += _on(ev)
            t0 = time.time()
            webview.start(private_mode=False, storage_path=str(storage))
            # If the page never loaded before the loop ended, WebView2 could not initialise
            # (corrupt/locked profile) — retry once with a fresh profile directory.
            if state["loaded"] or attempt == 2:
                break
            log.warning("window closed after %.1fs without loading — resetting WebView2 profile and retrying",
                        time.time() - t0)
            log.warning("window closed immediately — resetting WebView2 profile and retrying")
            _kill_orphan_webview(storage)
            _rotate_dir(storage)
    except Exception:  # noqa: BLE001
        import traceback

        tb = traceback.format_exc()
        log.error("webview crashed: %s", tb)
        exit_code = 1
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, "Không mở được cửa sổ ứng dụng.\n\n" + tb[-1200:],
                                             "TTS Studio — lỗi khởi động", 0x10)
        except Exception:  # noqa: BLE001
            pass
    finally:
        _kill_orphan_webview(storage)  # never leave msedgewebview2.exe children behind
        # Worker threads are non-daemon: without this, closing the window leaves an invisible
        # pythonw.exe alive until every running job (or a multi-GB pip install) finishes.
        try:
            from app.jobs import jobs

            jobs.shutdown()
        except Exception:  # noqa: BLE001
            pass
        log.info("window closed — exiting (%d)", exit_code)
        os._exit(exit_code)


if __name__ == "__main__":
    main()
