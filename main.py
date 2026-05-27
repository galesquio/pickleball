import multiprocessing
import threading
import time
import webbrowser

import uvicorn

from app import create_app


def open_browser():
    time.sleep(1.5)
    webbrowser.open("http://localhost:8765")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    app = create_app()
    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")
