#!/usr/bin/env python3
import uvicorn
import webbrowser
import threading
import time
import sys
import multiprocessing

# --- IMPORT BẮT BUỘC ĐỂ TRÁNH PYINSTALLER BỎ SÓT UVICORN MODULES ---
import uvicorn.loops
import uvicorn.loops.auto
import uvicorn.protocols
import uvicorn.protocols.http
import uvicorn.protocols.http.auto
import uvicorn.protocols.websockets
import uvicorn.protocols.websockets.auto
import uvicorn.lifespan
import uvicorn.lifespan.on

import os
from dotenv import load_dotenv

# Nạp các biến cấu hình từ .env nếu có
load_dotenv()

APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
APP_TITLE = os.getenv("APP_TITLE", "Hi Downloader")

def start_server():
    from app import app
    uvicorn.run(app, host=APP_HOST, port=APP_PORT, log_level="warning")

def open_browser():
    time.sleep(1.5)
    url = f"http://{APP_HOST}:{APP_PORT}"
    print(f"\n[DESKTOP LAUNCHER] DANG MO GIAO DIEN TAI: {url}")
    webbrowser.open(url)

if __name__ == "__main__":
    # Sửa lỗi đa luồng nhân bản vô hạn của PyInstaller trên Windows
    multiprocessing.freeze_support()
    
    print("-" * 60)
    print(f"      KHOI CHAY {APP_TITLE.upper()}      ")
    print("-" * 60)
    
    # Chạy server FastAPI ở luồng phụ
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    
    # Tự động mở trình duyệt
    open_browser()
    
    # Giữ luồng chính chạy
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[DESKTOP LAUNCHER] DA DONG UNG DUNG.")
        sys.exit(0)
