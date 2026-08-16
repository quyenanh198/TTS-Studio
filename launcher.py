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
        background_color="#0b0f19",
    )
    _ = window
    from app.config import DATA_DIR

    webview.start(private_mode=False, storage_path=str(DATA_DIR / "webview"))


if __name__ == "__main__":
    main()
