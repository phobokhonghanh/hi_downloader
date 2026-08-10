import os
import sys
import time
import threading
import urllib.request
import urllib.parse
import json

# Xóa các biến môi trường proxy để kết nối trực tiếp đến localhost
for env_var in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"]:
    if env_var in os.environ:
        del os.environ[env_var]

# Thêm thư mục hiện tại vào PATH để import app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app import app
import uvicorn

def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8999, log_level="warning")

if __name__ == "__main__":
    # Khởi chạy server FastAPI ở port 8999
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # Chờ server khởi động
    time.sleep(2.0)
    
    print("\n--- BẮT ĐẦU CHẠY KIỂM THỬ TỰ ĐỘNG API ---")
    
    # Test 1: GET /api/system
    try:
        url = "http://127.0.0.1:8999/api/system"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            print("\n[TEST 1] GET /api/system: THÀNH CÔNG")
            print("Kết quả phản hồi JSON:")
            print(json.dumps(res_data, indent=4))
    except Exception as e:
        print(f"\n[TEST 1] GET /api/system: THẤT BẠI - Lỗi: {e}")

    # Test 2: POST /api/analyze (Phân tích thử link video Bilibili)
    try:
        url = "http://127.0.0.1:8999/api/analyze"
        # Một URL video Bilibili công khai làm ví dụ test
        post_data = json.dumps({
            "url": "https://www.bilibili.com/video/BV1UvMQ6UEU1/?spm_id_from=333.1387.upload.video_card.click"
        }).encode('utf-8')
        
        req = urllib.request.Request(
            url, 
            data=post_data, 
            headers={'Content-Type': 'application/json'}
        )
        
        print("\n[TEST 2] Đang gọi POST /api/analyze để kiểm tra kết nối Bilibili...")
        with urllib.request.urlopen(req, timeout=15) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            print("[TEST 2] POST /api/analyze: THÀNH CÔNG")
            print("Kết quả phân tích JSON:")
            print(json.dumps(res_data, indent=4))
    except Exception as e:
        print(f"\n[TEST 2] POST /api/analyze: THẤT BẠI (Có thể do lỗi mạng hoặc IP bị Bilibili rate-limit) - Lỗi: {e}")

    print("\n--- KẾT THÚC KIỂM THỬ ---")
    sys.exit(0)
