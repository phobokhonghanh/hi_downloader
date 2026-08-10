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

def start_server():
    uvicorn.run("app:app", host="127.0.0.1", port=8000, log_level="warning")

def open_browser():
    time.sleep(1.5)
    url = "http://127.0.0.1:8000"
    print(f"\n[DESKTOP LAUNCHER] DANG MO GIAO DIEN TAI: {url}")
    webbrowser.open(url)

if __name__ == "__main__":
    # Sửa lỗi đa luồng nhân bản vô hạn của PyInstaller trên Windows
    multiprocessing.freeze_support()
    
    print("-" * 60)
    print("      KHOI CHAY BILIBILI 4K DOWNLOADER DESKTOP APP      ")
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
