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
    try:
        import webview
        webview.create_window(APP_TITLE, url, width=1280, height=800, resizable=True, maximized=True)
        if sys.platform.startswith("linux"):
            try:
                import webview.platforms.qt as webview_qt
                if hasattr(webview_qt, 'BrowserView'):
                    def safe_perm(self, url, feature):
                        try:
                            from qtpy.QtWebEngineCore import QWebEnginePage
                            self.setFeaturePermission(url, feature, QWebEnginePage.PermissionPolicy.PermissionDeniedByUser)
                        except Exception:
                            pass
                    webview_qt.BrowserView.onFeaturePermissionRequested = safe_perm
            except Exception:
                pass
            try:
                webview.start(gui="qt")
            except Exception:
                webview.start()
        else:
            webview.start()
        print("\n[DESKTOP LAUNCHER] CUA SO UNG DUNG DA DONG. DANG THOAT...")
        sys.exit(0)
    except Exception as e:
        print(f"[DESKTOP LAUNCHER] (Không mở được cửa sổ pywebview: {e}) -> Bật trình duyệt hệ thống...")
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
    
    # Khởi chạy giao diện Desktop
    open_browser()
    
    # Giữ luồng chính chạy (nếu dùng fallback webbrowser)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[DESKTOP LAUNCHER] DA DONG UNG DUNG.")
        sys.exit(0)
