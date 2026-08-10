import os
import sys
import uuid
import shutil
import random
import time
import logging
import subprocess
import json
import re
import threading
from typing import Optional
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, BackgroundTasks, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import yt_dlp
from dotenv import load_dotenv

# Load các biến môi trường từ file .env nếu có
load_dotenv()

app = FastAPI(title="Bilibili Advanced Downloader")

# --- ĐƯỜNG DẪN HOẠT ĐỘNG ---
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(os.path.abspath(__file__))

# Tự động nạp base_path (thư mục sys._MEIPASS khi đóng gói 1 file exe) vào PATH để yt-dlp tự động nhận diện ffmpeg/ffprobe nhúng sẵn
if base_path not in os.environ.get("PATH", ""):
    os.environ["PATH"] = base_path + os.pathsep + os.environ.get("PATH", "")

STATIC_DIR = os.path.join(base_path, "static")
DOWNLOAD_DIR = os.path.abspath("./downloads")

# Đảm bảo tạo thư mục downloads khi ứng dụng khởi chạy
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

EXE_DIR = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(EXE_DIR, "config.json")

# --- CẤU HÌNH LOGGING GHI FILE ---
# --- CẤU HÌNH LOGGING GHI FILE (OVERWRITE MODE) ---
LOG_FILE = os.path.join(EXE_DIR, "hi_downloader.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='w', encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)

logging.info(f"--- KHOI DONG HE THONG ---")
logging.info(f"Thu muc chay file: {EXE_DIR}")
logging.info(f"File log duoc luu tai: {LOG_FILE}")

# --- MONKEYPATCH YT-DLP ĐỂ BẮT TỔNG SỐ VIDEO KÊNH & DỊCH CHUYỂN PHÂN TRANG TRÁNH LỖI RATE LIMIT (412) ---
from yt_dlp.extractor.bilibili import BilibiliSpaceVideoIE, BilibiliBaseIE

thread_local_data = threading.local()

captured_space_video_count = {}
original_download_json = BilibiliSpaceVideoIE._download_json

def patched_download_json(self, url, video_id, *args, **kwargs):
    res = original_download_json(self, url, video_id, *args, **kwargs)
    if "api.bilibili.com/x/space/wbi/arc/search" in url:
        try:
            count = res.get("page", {}).get("count") or res.get("data", {}).get("page", {}).get("count")
            if count is not None:
                captured_space_video_count[str(video_id)] = int(count)
                logging.info(f"[MONKEYPATCH] Bat duoc tong so video cua mid={video_id}: {count} (Dung de dung phan trang som)")
        except Exception as e:
            logging.warning(f"[MONKEYPATCH] Loi phan tich tong so video: {e}")
    return res

BilibiliSpaceVideoIE._download_json = patched_download_json

# Vá hàm ký WBI để dịch chuyển phân trang trang chính từ trang 1 sang trang mong muốn trực tiếp (bỏ qua các trang trung gian)
original_sign_wbi = BilibiliBaseIE._sign_wbi

def patched_sign_wbi(self, query, *args, **kwargs):
    page_start = getattr(thread_local_data, "page_start", 1)
    if "pn" in query and page_start > 1:
        orig_pn = query["pn"]
        # Tịnh tiến số trang để yt-dlp truy cập trực tiếp trang cần tải
        query["pn"] = orig_pn + (page_start - 1)
        logging.info(f"[MONKEYPATCH] Dich chuyen tham so phan trang truoc khi ky: pn={orig_pn} -> pn={query['pn']}")
    return original_sign_wbi(self, query, *args, **kwargs)

BilibiliBaseIE._sign_wbi = patched_sign_wbi


def detect_working_browsers() -> list:
    working = []
    try:
        from yt_dlp.cookies import extract_cookies_from_browser
    except Exception:
        # Fallback nếu không import được
        return ["firefox", "chrome", "safari", "edge"]
        
    for browser in ["firefox", "chrome", "safari", "edge"]:
        try:
            cj = extract_cookies_from_browser(browser)
            # Chỉ ghi nhận trình duyệt nếu đọc và giải mã thành công cookies (>0 cookies)
            if cj and len(cj) > 0:
                working.append(browser)
        except Exception:
            pass
    return working

WORKING_BROWSERS = detect_working_browsers()
logging.info(f"[BROWSER PROBER] Phat hien cac trinh duyet co the dung de nap cookies: {WORKING_BROWSERS}")

def get_default_browser() -> str:
    """Trả về trình duyệt mặc định khả dụng trên hệ thống"""
    if WORKING_BROWSERS:
        return WORKING_BROWSERS[0]
    return "firefox"

def reset_run_environment_if_idle():
    """Reset tasks và log file trước khi bắt đầu một đợt tải mới nếu không có task nào đang chạy"""
    has_active = any(t.get("status") in ["downloading", "merging"] for t in tasks.values())
    if not has_active and tasks:
        tasks.clear()
        try:
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [INFO] --- BAT DAU LUOT TAI MOI (BENCHMARK) ---\n")
            logging.info("Da reset danh sach task va tui log file cho luot tai moi.")
        except Exception as e:
            logging.error(f"Loi reset log file: {e}")


# --- QUẢN LÝ CACHE THƯ MỤC LƯU TRỮ ---
def load_cached_dir() -> str:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                cached = data.get("download_dir")
                if cached:
                    try:
                        # Neu thu muc da xoa hoac chua ton tai, tu dong tao ra no
                        os.makedirs(cached, exist_ok=True)
                        return os.path.abspath(cached)
                    except Exception as e:
                        logging.warning(f"Khong the tu dong tao thu muc cache {cached}: {e}. Fallback ve download dir mac dinh.")
        except Exception as e:
            logging.error(f"Loi doc file cache config: {e}")
    return DOWNLOAD_DIR

def save_cached_dir(path: str):
    try:
        abs_path = os.path.abspath(path)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"download_dir": abs_path}, f, ensure_ascii=False, indent=4)
        logging.info(f"Da ghi nhan thu muc luu tru vao cache: {abs_path}")
    except Exception as e:
        logging.error(f"Loi ghi file cache config: {e}")

def get_run_target_dir(base_dir: str) -> str:
    """Tự động tạo cấu trúc thư mục A/DDMMYYYY/Lần_chạy/ dựa trên số lượng đếm đã có"""
    date_str = time.strftime("%d%m%Y")
    day_dir = os.path.join(os.path.abspath(base_dir), date_str)
    os.makedirs(day_dir, exist_ok=True)
    
    existing_runs = []
    try:
        for item in os.listdir(day_dir):
            item_path = os.path.join(day_dir, item)
            if os.path.isdir(item_path) and item.isdigit():
                existing_runs.append(int(item))
    except Exception as e:
        logging.warning(f"Loi quet thu muc lan chay: {e}")
        
    next_run = max(existing_runs) + 1 if existing_runs else 1
    run_dir = os.path.join(day_dir, str(next_run))
    os.makedirs(run_dir, exist_ok=True)
    logging.info(f"[RUN DIR] Tao thu muc lan chay moi: {run_dir}")
    return run_dir

# --- CẤU HÌNH PROXY & WORKER ---
PROXY_USER = os.getenv("PROXY_USER", "")
PROXY_PASS = os.getenv("PROXY_PASS", "")
MAX_CONCURRENT_DOWNLOADS = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "2"))

executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_DOWNLOADS)
tasks = {}

class AnalyzeRequest(BaseModel):
    url: str
    cookies_browser: Optional[str] = None

class DownloadRequest(BaseModel):
    url: str
    cookies_browser: Optional[str] = None
    quality: str = "best"
    page_start: int = 1
    page_end: int = 1
    max_videos: Optional[int] = None
    output_dir: Optional[str] = None

# Custom Logger de yt-dlp ghi log ra file hi_downloader.log
class YDLLogger:
    def debug(self, msg):
        if not msg.startswith('[debug] '):
            logging.info(f"[yt-dlp] {msg}")

    def info(self, msg):
        logging.info(f"[yt-dlp] {msg}")

    def warning(self, msg):
        logging.warning(f"[yt-dlp] {msg}")

    def error(self, msg):
        logging.error(f"[yt-dlp] {msg}")

def clean_url(url: str) -> str:
    cleaned = url.split('?')[0]
    if "space.bilibili.com" in cleaned and "/upload/video" in cleaned:
        cleaned = cleaned.replace("/upload/video", "/video")
    return cleaned

def check_ffmpeg():
    in_path = shutil.which("ffmpeg") is not None
    in_base_dir = os.path.exists(os.path.join(base_path, "ffmpeg.exe")) or os.path.exists(os.path.join(base_path, "ffmpeg"))
    in_exe_dir = os.path.exists(os.path.join(EXE_DIR, "ffmpeg.exe")) or os.path.exists(os.path.join(EXE_DIR, "ffmpeg"))
    return in_path or in_base_dir or in_exe_dir

def get_rotational_proxy() -> Optional[str]:
    proxy_file = os.path.join(EXE_DIR, "proxies.txt")
    if not os.path.exists(proxy_file):
        return None
    try:
        with open(proxy_file, "r") as f:
            lines = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
        if not lines:
            return None
        selected_proxy = random.choice(lines)
        if PROXY_USER and PROXY_PASS:
            return f"http://{PROXY_USER}:{PROXY_PASS}@{selected_proxy}"
        return f"http://{selected_proxy}"
    except Exception as e:
        logging.error(f"[PROXY ERROR] Loi doc file proxies.txt: {e}")
        return None

# --- API PHÂN TÍCH (ANALYZE/SEARCH) - TÍCH HỢP RETRY 3 LẦN & ROTATION PROXY/COOKIES ---
@app.post("/api/analyze")
def analyze_url(req: AnalyzeRequest):
    # Reset thread local de dam bao khong bi anh huong phan trang khi analyze
    if hasattr(thread_local_data, 'page_start'):
        del thread_local_data.page_start
    url = clean_url(req.url)
    logging.info(f"Bat dau phan tich URL (Tim kiem): {url}")
    
    max_attempts = 3
    browsers = list(WORKING_BROWSERS) if WORKING_BROWSERS else ["firefox", "chrome", "safari", "edge"]
    primary_browser = req.cookies_browser or (browsers[0] if browsers else "firefox")
    
    last_err = None
    
    for attempt in range(1, max_attempts + 1):
        if attempt == 1:
            browser = primary_browser
        else:
            remaining = [b for b in browsers if b != primary_browser]
            browser = remaining[(attempt - 2) % len(remaining)] if remaining else primary_browser
            logging.info(f"[ANALYZE RETRY] Lan thu {attempt}/{max_attempts}: Xoay trinh duyet sang {browser} va doi proxy de thu lai...")
            time.sleep(1.5)
            
        ydl_opts = {
            'extract_flat': True,
            'skip_download': True,
            'sleep_interval_requests': 2,  # Delay 2s giữa các request lấy dữ liệu (tránh bị chặn 412)
            'playlistend': 1,              # CHỈ QUÉT TRANG ĐẦU TIÊN
            'logger': YDLLogger(),
            'cookiesfrombrowser': (browser,)
        }
            
        proxy = get_rotational_proxy()
        if proxy:
            logging.info(f"[ANALYZE] Lan thu {attempt}/{max_attempts} - Su dung Proxy: {proxy.split('@')[-1]} (Cookies: {browser})")
            ydl_opts['proxy'] = proxy

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
            if 'entries' in info:
                # Trích xuất mid (creator id) từ url để đối chiếu với biến global đã bắt
                mid_match = re.search(r'space\.bilibili\.com/(\d+)', url)
                mid = mid_match.group(1) if mid_match else None
                
                total_videos = 0
                if mid and str(mid) in captured_space_video_count:
                    total_videos = captured_space_video_count[str(mid)]
                else:
                    # Fallback nếu không bắt được
                    total_videos = len(info.get('entries', []))

                total_pages = (total_videos + 29) // 30
                logging.info(f"Phan tich Space thanh cong sau {attempt} lan thu: {info.get('title')} ({total_videos} videos)")
                return {
                    "type": "space",
                    "title": info.get("title", "Bilibili Space"),
                    "total_videos": total_videos,
                    "total_pages": total_pages,
                    "working_browser": browser
                }
            else:
                formats = info.get("formats", [])
                heights = set()
                for fmt in formats:
                    h = fmt.get("height")
                    if h and h >= 360:
                        heights.add(h)
                
                available_qualities = sorted(list(heights), reverse=True)
                quality_labels = []
                for h in available_qualities:
                    if h >= 2160: quality_labels.append({"value": str(h), "label": f"{h}p (4K ULTRA HD)"})
                    elif h >= 1080: quality_labels.append({"value": str(h), "label": f"{h}p (FULL HD)"})
                    elif h >= 720: quality_labels.append({"value": str(h), "label": f"{h}p (HD)"})
                    else: quality_labels.append({"value": str(h), "label": f"{h}p (SD)"})
                    
                if not quality_labels:
                    quality_labels.append({"value": "best", "label": "CHAT LUONG TOT NHAT (AUTO)"})

                logging.info(f"Phan tich Video don le thanh cong sau {attempt} lan thu: {info.get('title')}")
                return {
                    "type": "video",
                    "title": info.get("title", "Video Don Le"),
                    "uploader": info.get("uploader", "Unknown"),
                    "duration": info.get("duration", 0),
                    "qualities": quality_labels,
                    "working_browser": browser
                }
        except Exception as e:
            last_err = e
            err_str = str(e)
            logging.warning(f"[ANALYZE ATTEMPT {attempt}/{max_attempts}] That bai voi trinh duyet {browser}: {err_str}")
                
    logging.error(f"Loi khi phan tich URL {url} sau {max_attempts} lan thu: {last_err}")
    clean_err_msg = str(last_err).replace("\u001b[0;31m", "").replace("\u001b[0m", "")
    raise HTTPException(status_code=500, detail=f"Loi Bilibili sau 3 lan thu: {clean_err_msg}")

# --- HÀM TẢI WORKER ĐA LUỒNG TÍCH HỢP RETRY & ĐO THỜI GIAN ---
def download_worker(task_id: str, url: str, cookies_browser: str, quality: str, page_start: int, page_end: int, target_dir: str):
    start_time = time.time()
    tasks[task_id]["status"] = "downloading"
    
    def hook(d):
        if tasks[task_id]["status"] == "canceled":
            raise ValueError("CANCELED")
            
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            percentage = (downloaded / total * 100) if total > 0 else 0
            
            elapsed = time.time() - start_time
            tasks[task_id].update({
                "progress": round(percentage, 2),
                "speed": d.get('_speed_str', 'N/A'),
                "eta": d.get('_eta_str', 'N/A'),
                "elapsed_time": round(elapsed, 1),
                "filename": os.path.basename(d.get('filename', ''))
            })
        elif d['status'] == 'finished':
            tasks[task_id].update({
                "status": "merging",
                "progress": 99.9
            })

    has_ffmpeg = check_ffmpeg()
    
    logging.info(f"[TASK {task_id}] Bat dau xu ly tai: {url}")
    logging.info(f"[TASK {task_id}] Thu muc luu tru: {target_dir}")
    
    if not has_ffmpeg:
        logging.warning(f"[TASK {task_id}] HE THONG THIEU FFMPEG! Bat buoc fallback ve format single merged 'best' de khong bi crash.")
        fmt_str = "best"
    else:
        if quality != "best":
            fmt_str = f"bestvideo[height<={quality}]+bestaudio/best"
        else:
            fmt_str = "bestvideo+bestaudio/best"

    has_ffmpeg_file = os.path.exists(os.path.join(EXE_DIR, "ffmpeg.exe")) or os.path.exists(os.path.join(EXE_DIR, "ffmpeg"))

    ydl_opts = {
        'outtmpl': os.path.join(target_dir, '%(uploader)s/%(title)s.%(ext)s'),
        'format': fmt_str,
        'progress_hooks': [hook],
        'ffmpeg_location': EXE_DIR if has_ffmpeg_file else None,
        'retries': 3,
        'fragment_retries': 3,
        'sleep_interval': 3,              # Delay ngẫu nhiên từ 3s đến 6s giữa các video (giảm rate limit)
        'max_sleep_interval': 6,
        'sleep_interval_requests': 2,     # Delay 2s giữa các request gọi API lấy dữ liệu phân trang
        'logger': YDLLogger()
    }

    if "space.bilibili.com" in url:
        # Cơ chế tịnh tiến trang để tải trực tiếp trang mong muốn, không quét tuần tự từ trang 1
        page_count = page_end - page_start + 1
        ydl_opts['playliststart'] = 1
        ydl_opts['playlistend'] = page_count * 30
        thread_local_data.page_start = page_start
        logging.info(f"[TASK {task_id}] Su dung co che dich phan trang: Quet tu trang {page_start} (So luong {page_count} trang)")
    else:
        ydl_opts['noplaylist'] = True
        if hasattr(thread_local_data, 'page_start'):
            del thread_local_data.page_start

    max_attempts = 3
    success = False
    last_error_msg = ""

    for attempt in range(1, max_attempts + 1):
        if tasks[task_id]["status"] == "canceled":
            break
            
        try:
            tasks[task_id]["retry_count"] = attempt
            proxy = get_rotational_proxy()
            if proxy:
                logging.info(f"[TASK {task_id}] Lan thu {attempt}/{max_attempts} - Su dung Proxy: {proxy.split('@')[-1]}")
                ydl_opts['proxy'] = proxy
            else:
                if 'proxy' in ydl_opts:
                    del ydl_opts['proxy']

            # Bắt buộc nạp cookies từ trình duyệt ngay từ lượt đầu tiên (mặc định lấy trình duyệt khả dụng)
            active_browser = cookies_browser or get_default_browser()
            if attempt == 1:
                logging.info(f"[TASK {task_id}] Nap san cookies tu trinh duyet: {active_browser}")
                ydl_opts['cookiesfrombrowser'] = (active_browser,)
            else:
                # Lượt 2 hoặc 3: Xoay vòng các trình duyệt khả dụng còn lại (đã kiểm tra lúc khởi động)
                browsers = list(WORKING_BROWSERS)
                if not browsers:
                    browsers = ["firefox", "chrome", "safari", "edge"]
                remaining_browsers = [b for b in browsers if b != active_browser]
                if not remaining_browsers:
                    remaining_browsers = browsers
                selected_browser = remaining_browsers[(attempt - 2) % len(remaining_browsers)]
                logging.info(f"[TASK {task_id}] Tải lại lần {attempt}. Thử nạp cookies từ trình duyệt {selected_browser} để vượt chặn...")
                ydl_opts['cookiesfrombrowser'] = (selected_browser,)

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([clean_url(url)])
            
            success = True
            logging.info(f"[TASK {task_id}] Tai thanh cong video sau {attempt} lan thu.")
            break
            
        except ValueError as ve:
            if str(ve) == "CANCELED":
                tasks[task_id]["status"] = "canceled"
                logging.info(f"[TASK {task_id}] Bi huy boi nguoi dung.")
                break
            last_error_msg = str(ve)
        except Exception as e:
            last_error_msg = str(e)
            logging.error(f"[TASK {task_id}] Gap loi o lan thu {attempt}/{max_attempts}: {last_error_msg}")
            if attempt < max_attempts:
                time.sleep(2)

    total_elapsed = time.time() - start_time
    tasks[task_id]["elapsed_time"] = round(total_elapsed, 1)

    # Clear thread local khi ket thuc task
    if hasattr(thread_local_data, 'page_start'):
        del thread_local_data.page_start

    if tasks[task_id]["status"] == "canceled":
        return
        
    if success:
        tasks[task_id].update({
            "status": "completed",
            "progress": 100
        })
    else:
        tasks[task_id].update({
            "status": "failed",
            "error": f"Loi sau {max_attempts} lan thu: {last_error_msg}"
        })
        logging.error(f"[TASK {task_id}] That bai hoan toan sau {max_attempts} lan thu. Loi: {last_error_msg}")

def space_download_manager(master_task_id: str, url: str, cookies_browser: str, quality: str, page_start: int, page_end: int, target_dir: str, max_videos: Optional[int] = None):
    start_time = time.time()
    tasks[master_task_id]["status"] = "downloading"
    tasks[master_task_id]["filename"] = f"Đang trích xuất video trang {page_start} - {page_end}..."
    
    page_count = page_end - page_start + 1
    ydl_opts = {
        'extract_flat': True,
        'skip_download': True,
        'playliststart': 1,
        'playlistend': page_count * 30,
        'logger': YDLLogger()
    }
    
    active_browser = cookies_browser or get_default_browser()
    ydl_opts['cookiesfrombrowser'] = (active_browser,)
        
    proxy = get_rotational_proxy()
    if proxy:
        ydl_opts['proxy'] = proxy

    thread_local_data.page_start = page_start
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url(url), download=False)
            
        entries = info.get('entries', []) if info else []
        if not entries:
            raise ValueError("Không tìm thấy video nào trong phạm vi trang đã chọn.")
            
        if max_videos and max_videos > 0:
            entries = entries[:max_videos]
            logging.info(f"[MASTER TASK {master_task_id}] Giới hạn số lượng video tải xuống: {len(entries)} video.")

        logging.info(f"[MASTER TASK {master_task_id}] Phân tách thành công {len(entries)} video từ Space. Đang đẩy vào hàng chờ...")
        
        for item in entries:
            video_id = item.get('id') or item.get('url')
            if not video_id:
                continue
            video_title = item.get('title') or f"Video {video_id}"
            video_url = item.get('url') if item.get('url', '').startswith("http") else f"https://www.bilibili.com/video/{video_id}"
                
            sub_task_id = str(uuid.uuid4())
            tasks[sub_task_id] = {
                "id": sub_task_id,
                "url": video_url,
                "status": "pending",
                "progress": 0,
                "speed": "0 KB/s",
                "eta": "N/A",
                "elapsed_time": 0,
                "retry_count": 1,
                "filename": video_title,
                "error": None,
                "target_dir": target_dir
            }
            
            executor.submit(
                download_worker,
                sub_task_id,
                video_url,
                cookies_browser,
                quality,
                1,
                1,
                target_dir
            )
            
        tasks[master_task_id].update({
            "status": "completed",
            "progress": 100,
            "filename": f"Đã trích xuất xong {len(entries)} video và bắt đầu tải song song.",
            "elapsed_time": round(time.time() - start_time, 1)
        })
    except Exception as e:
        err_msg = str(e)
        tasks[master_task_id].update({
            "status": "failed",
            "error": f"Lỗi trích xuất Space: {err_msg}",
            "elapsed_time": round(time.time() - start_time, 1)
        })
        logging.error(f"[MASTER TASK {master_task_id}] Lỗi: {err_msg}")
    finally:
        if hasattr(thread_local_data, 'page_start'):
            del thread_local_data.page_start


@app.post("/api/download")
def trigger_download(req: DownloadRequest):
    # Reset tasks và log buffer nếu lượt trước đã xong để đo Benchmark chính xác cho đợt mới
    reset_run_environment_if_idle()

    base_dir = os.path.abspath(req.output_dir) if req.output_dir else load_cached_dir()
    os.makedirs(base_dir, exist_ok=True)
    save_cached_dir(base_dir)
    
    # Tính đường dẫn thư mục lần chạy mới (A/DDMMYYYY/Lần_chạy/)
    target_dir = get_run_target_dir(base_dir)
    
    clean_req_url = clean_url(req.url)
    
    if "space.bilibili.com" in clean_req_url:
        master_task_id = str(uuid.uuid4())
        tasks[master_task_id] = {
            "id": master_task_id,
            "url": req.url,
            "status": "pending",
            "progress": 0,
            "speed": "0 KB/s",
            "eta": "N/A",
            "elapsed_time": 0,
            "retry_count": 1,
            "filename": f"Kênh Bilibili (Trang {req.page_start} - {req.page_end})",
            "error": None,
            "target_dir": target_dir
        }
        executor.submit(
            space_download_manager,
            master_task_id,
            req.url,
            req.cookies_browser,
            req.quality,
            req.page_start,
            req.page_end,
            target_dir,
            req.max_videos
        )
        return {"task_id": master_task_id, "status": "pending"}
    else:
        task_id = str(uuid.uuid4())
        tasks[task_id] = {
            "id": task_id,
            "url": req.url,
            "status": "pending",
            "progress": 0,
            "speed": "0 KB/s",
            "eta": "N/A",
            "elapsed_time": 0,
            "retry_count": 1,
            "filename": "",
            "error": None,
            "target_dir": target_dir
        }
        executor.submit(
            download_worker,
            task_id,
            req.url,
            req.cookies_browser,
            req.quality,
            req.page_start,
            req.page_end,
            target_dir
        )
        return {"task_id": task_id, "status": "pending"}

@app.post("/api/tasks/clear")
def clear_tasks_api():
    reset_run_environment_if_idle()
    return {"status": "success", "remaining": len(tasks)}

@app.post("/api/tasks/{task_id}/open-folder")
def open_task_folder(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task không tồn tại")
    target_dir = tasks[task_id].get("target_dir")
    if not target_dir or not os.path.exists(target_dir):
        raise HTTPException(status_code=404, detail="Thư mục không tồn tại")
        
    try:
        if sys.platform == "win32":
            os.startfile(target_dir)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target_dir])
        else:
            subprocess.Popen(["xdg-open", target_dir])
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Không thể mở thư mục: {e}")

@app.post("/api/tasks/{task_id}/cancel")
def cancel_task(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    tasks[task_id]["status"] = "canceled"
    return {"status": "canceling"}

@app.get("/api/tasks")
def get_tasks():
    return list(tasks.values())

@app.get("/api/system")
def get_system():
    return {
        "ffmpeg_installed": check_ffmpeg(),
        "download_dir": load_cached_dir()
    }

# --- API LẤY LOG THỜI GIAN THỰC (LIVE SHELL LOGS) ---
@app.get("/api/logs")
def get_logs():
    if not os.path.exists(LOG_FILE):
        return []
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            tail = [line.strip() for line in lines[-20:]]
            clean_tail = []
            for line in tail:
                clean_line = line.replace("\u001b[0;31m", "").replace("\u001b[0m", "")
                clean_tail.append(clean_line)
            return clean_tail
    except Exception as e:
        return [f"Loi doc file log: {e}"]

# --- BỘ TỰ ĐỘNG PHÁT HIỆN PORT ĐỒ HỌA HOẠT ĐỘNG (DISPLAY/XAUTHORITY PROBER) ---
def get_gui_env() -> dict:
    env = os.environ.copy()
    
    # Probing port hien thi hop le de tu dong va cham DISPLAY
    if "DISPLAY" not in env or not env["DISPLAY"]:
        working_disp = None
        for disp in [":0", ":1", ":2"]:
            try:
                test_env = env.copy()
                test_env["DISPLAY"] = disp
                subprocess.check_call(
                    [sys.executable, "-c", "import tkinter as tk; tk.Tk().destroy()"],
                    env=test_env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2
                )
                working_disp = disp
                break
            except Exception:
                continue
        if working_disp:
            env["DISPLAY"] = working_disp
            logging.info(f"[DISPLAY PROBER] Tu dong phat hien display va set DISPLAY={working_disp}")
        else:
            env["DISPLAY"] = ":0"
            logging.warning("[DISPLAY PROBER] Khong tim thay display hoat dong nao, dung mac dinh DISPLAY=:0")
            
    # Tu dong link file Xauthority neu thieu de cap quyen do hoa
    if sys.platform.startswith("linux") and ("XAUTHORITY" not in env or not env["XAUTHORITY"]):
        home = os.path.expanduser("~")
        xauth_file = os.path.join(home, ".Xauthority")
        if os.path.exists(xauth_file):
            env["XAUTHORITY"] = xauth_file
            logging.info(f"[XAUTHORITY PROBER] Tu dong set XAUTHORITY={xauth_file}")
            
    return env

# --- API MỞ HỘP THOẠI NATIVE OS CHỌN THƯ MỤC LƯU TRỮ ---
@app.post("/api/select-directory")
def select_directory():
    env = get_gui_env()

    # 1. TRÊN OS LINUX: Ưu tiên gọi các công cụ đồ họa gốc của hệ điều hành (Zenity/Kdialog) 
    # để mở đúng hộp thoại chuẩn của OS (như Nautilus trên Ubuntu) vô cùng đẹp mắt và mượt mà.
    if sys.platform.startswith("linux"):
        # Thử Zenity (Cực đẹp, mặc định cho Ubuntu/GNOME)
        if shutil.which("zenity"):
            try:
                cmd = ["zenity", "--file-selection", "--directory", "--title=Chon thu muc luu video Bilibili"]
                output = subprocess.check_output(cmd, env=env, text=True, stderr=subprocess.PIPE, timeout=60)
                path = output.strip()
                if path:
                    abs_path = os.path.abspath(path)
                    save_cached_dir(abs_path)
                    return {"status": "success", "path": abs_path}
            except subprocess.CalledProcessError as cpe:
                if cpe.returncode == 1:
                    logging.info("Nguoi dung da huy chon thu muc qua Zenity.")
                    return {"status": "canceled", "path": None}
                logging.warning(f"Zenity loi hoac thieu DISPLAY: {cpe.stderr.decode('utf-8', errors='ignore')}")
            except Exception as e:
                logging.warning(f"Zenity that bai: {e}")

        # Thử Kdialog (Mặc định cho các desktop KDE)
        if shutil.which("kdialog"):
            try:
                cmd = ["kdialog", "--getexistingdirectory", ".", "--title", "Chon thu muc luu video Bilibili"]
                output = subprocess.check_output(cmd, env=env, text=True, stderr=subprocess.PIPE, timeout=60)
                path = output.strip()
                if path:
                    abs_path = os.path.abspath(path)
                    save_cached_dir(abs_path)
                    return {"status": "success", "path": abs_path}
            except subprocess.CalledProcessError as cpe:
                if cpe.returncode == 1:
                    logging.info("Nguoi dung da huy chon thu muc qua Kdialog.")
                    return {"status": "canceled", "path": None}
                logging.warning(f"Kdialog loi: {cpe.stderr.decode('utf-8', errors='ignore')}")
            except Exception as e:
                logging.warning(f"Kdialog that bai: {e}")

    # 2. TRÊN OS MAC-OS: Sử dụng AppleScript mở Finder chọn thư mục gốc
    if sys.platform == "darwin":
        try:
            cmd = ["osascript", "-e", 'POSIX path of (choose folder with prompt "Chon thu muc luu video Bilibili")']
            output = subprocess.check_output(cmd, env=env, text=True, stderr=subprocess.PIPE, timeout=60)
            path = output.strip()
            if path:
                abs_path = os.path.abspath(path)
                save_cached_dir(abs_path)
                return {"status": "success", "path": abs_path}
        except subprocess.CalledProcessError:
            logging.info("Nguoi dung da huy chon thu muc qua AppleScript.")
            return {"status": "canceled", "path": None}
        except Exception as e:
            logging.warning(f"AppleScript that bai: {e}")

    # 3. TRÊN OS WINDOWS / HOẶC PHẦN MỀM KHÁC: Thử dùng Tkinter thông qua tiến trình Python con (Subprocess)
    # Tkinter trên Windows tự động mở Explorer Directory Chooser mặc định của Windows rất đẹp.
    try:
        cmd = [
            sys.executable,
            "-c",
            "import tkinter as tk; from tkinter import filedialog; root=tk.Tk(); root.withdraw(); root.attributes('-topmost', True); print(filedialog.askdirectory(title='Chon thu muc luu video Bilibili'))"
        ]
        output = subprocess.check_output(cmd, env=env, text=True, stderr=subprocess.PIPE, timeout=60)
        path = output.strip()
        if path:
            abs_path = os.path.abspath(path)
            save_cached_dir(abs_path)
            return {"status": "success", "path": abs_path}
        else:
            logging.info("Nguoi dung da huy chon thu muc qua Tkinter Subprocess.")
            return {"status": "canceled", "path": None}
    except Exception as e:
        err_msg = str(e)
        if hasattr(e, 'stderr') and e.stderr:
            err_msg = e.stderr.strip()
        logging.error(f"Khong the mo bat ky hop thoai do hoa nao cua OS: {err_msg}")

    # Nếu tất cả phương pháp đều thất bại do môi trường chạy thiếu DISPLAY
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Không thể kết nối đến giao diện màn hình Desktop của hệ điều hành. Vui lòng kiểm tra cổng DISPLAY hoặc khởi chạy lại ứng dụng bằng terminal mặc định ngoài màn hình chính (không chạy bên trong VS Code terminal)."
        }
    )

@app.get("/")
def read_root():
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    return FileResponse(os.path.join(STATIC_DIR, "index.html"), headers=headers)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
