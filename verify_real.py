import os
import sys
import shutil

# Xóa các biến môi trường loopback proxy của sandbox để sử dụng mạng thật của máy host
for env_var in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"]:
    if env_var in os.environ:
        del os.environ[env_var]

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app import clean_url, check_ffmpeg
import yt_dlp

def verify():
    url = "https://www.bilibili.com/video/BV1UvMQ6UEU1/"
    print(f"\n--- BẮT ĐẦU TẢI KIỂM CHỨNG THỰC TẾ ---")
    print(f"Đường dẫn video: {url}")
    
    has_ffmpeg = check_ffmpeg()
    print(f"Trạng thái FFmpeg: {'SẴN SÀNG' if has_ffmpeg else 'THIẾU (TỰ ĐỘNG CHUYỂN VỀ BEST FORMAT)'}")
    
    # Cấu hình lưu tạm để test tải
    test_dir = "./downloads/test_verify"
    os.makedirs(test_dir, exist_ok=True)
    
    project_dir = os.path.dirname(os.path.abspath(__file__))
    has_ffmpeg_file = os.path.exists(os.path.join(project_dir, "ffmpeg.exe")) or os.path.exists(os.path.join(project_dir, "ffmpeg"))
    
    ydl_opts = {
        'outtmpl': os.path.join(test_dir, '%(title)s.%(ext)s'),
        'format': 'best' if not has_ffmpeg else 'bestvideo+bestaudio/best',
        'noplaylist': True,
        'ffmpeg_location': project_dir if has_ffmpeg_file else None,
    }
    
    try:
        print("Đang kết nối Bilibili CDN và tiến hành tải thực tế...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        print("\n--- KẾT QUẢ: TẢI VIDEO THÀNH CÔNG! ---")
        files = os.listdir(test_dir)
        print(f"Tệp tin đã tải về thành công trong thư mục: {files}")
        
        # Dọn dẹp thư mục verify sau khi test
        shutil.rmtree(test_dir)
        print("Đã dọn dẹp các tệp tin thử nghiệm.")
        return True
    except Exception as e:
        print(f"\n--- KẾT QUẢ: TẢI THẤT BẠI ---")
        print(f"Lỗi chi tiết: {e}")
        return False

if __name__ == "__main__":
    verify()
