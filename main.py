import multiprocessing
import sys
import threading
import time
import webbrowser

import uvicorn

from app import create_app

HOST = "127.0.0.1"
PORT = 8765
APP_URL = f"http://{HOST}:{PORT}"


def wait_for_server(timeout: float = 30.0) -> bool:
    import socket

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((HOST, PORT), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def open_browser():
    time.sleep(1.5)
    webbrowser.open(APP_URL)


def run_uvicorn_server(app) -> None:
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="info")
    uvicorn.Server(config).run()


def run_desktop(app) -> None:
    import webview

    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=PORT, log_level="info"))

    def serve():
        server.run()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()

    if not wait_for_server():
        print("Server failed to start.", file=sys.stderr)
        sys.exit(1)

    webview.create_window(
        "Pickleball Management",
        APP_URL,
        width=1280,
        height=800,
        min_size=(1024, 640),
    )
    webview.start()

    server.should_exit = True
    thread.join(timeout=5)


def main() -> None:
    multiprocessing.freeze_support()
    app = create_app()

    if getattr(sys, "frozen", False):
        run_desktop(app)
    else:
        threading.Thread(target=open_browser, daemon=True).start()
        run_uvicorn_server(app)


if __name__ == "__main__":
    main()
