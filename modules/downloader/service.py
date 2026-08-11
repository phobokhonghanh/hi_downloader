import os
import sys
import uuid
import shutil
import random
import time
import logging
import subprocess
import re
import threading
import urllib.parse
import json
from typing import Optional, Any, Dict, List
import yt_dlp
from yt_dlp.extractor.bilibili import BilibiliSpaceVideoIE, BilibiliBaseIE

from core.task_store import TaskStore, TaskStatus
from modules.downloader.schemas import AnalyzeRequestData, DownloadRequestData, DownloadTaskResult

BILIBILI_SPACE_DOMAIN = "space.bilibili.com"
BILIBILI_VIDEO_BASE_URL = "https://www.bilibili.com/video/"
BILIBILI_API_DOMAIN = "api.bilibili.com"

# Thread-local storage for page translation
thread_local_data = threading.local()
captured_space_video_count = {}

# Monkeypatch yt-dlp BilibiliSpaceVideoIE download JSON method
original_download_json = BilibiliSpaceVideoIE._download_json

def patched_download_json(self, url, video_id, *args, **kwargs):
    res = original_download_json(self, url, video_id, *args, **kwargs)
    if f"{BILIBILI_API_DOMAIN}/x/space/wbi/arc/search" in url:
        try:
            count = res.get("page", {}).get("count") or res.get("data", {}).get("page", {}).get("count")
            if count is not None:
                captured_space_video_count[str(video_id)] = int(count)
                logging.info(f"[MONKEYPATCH] Captured total video count for mid={video_id}: {count}")
        except Exception as e:
            logging.warning(f"[MONKEYPATCH] Error parsing total video count: {e}")
    return res

BilibiliSpaceVideoIE._download_json = patched_download_json

# Monkeypatch BilibiliBaseIE sign wbi to shift pages directly
original_sign_wbi = BilibiliBaseIE._sign_wbi

def patched_sign_wbi(self, query, *args, **kwargs):
    page_start = getattr(thread_local_data, "page_start", 1)
    if "pn" in query and page_start > 1:
        orig_pn = query["pn"]
        query["pn"] = orig_pn + (page_start - 1)
        logging.info(f"[MONKEYPATCH] Shifted pagination parameter before signing: pn={orig_pn} -> {query['pn']}")
    return original_sign_wbi(self, query, *args, **kwargs)

BilibiliBaseIE._sign_wbi = patched_sign_wbi


def detect_working_browsers() -> list:
    working = []
    try:
        from yt_dlp.cookies import extract_cookies_from_browser
    except Exception:
        return ["firefox", "chrome", "safari", "edge"]
        
    for browser in ["firefox", "chrome", "safari", "edge"]:
        try:
            cj = extract_cookies_from_browser(browser)
            if cj and len(cj) > 0:
                working.append(browser)
        except Exception:
            pass
    return working


WORKING_BROWSERS = detect_working_browsers()


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


class DownloaderService:
    def __init__(self, task_store: Optional[TaskStore] = None, executor: Optional[Any] = None, log_callback: Optional[Any] = None, config: Optional[Dict[str, Any]] = None):
        self.task_store = task_store
        self.executor = executor
        self.log_callback = log_callback
        self.config = config or {}
        self._task_urls: Dict[str, str] = {}

    def _log_user(self, message: str, level: str = "INFO"):
        if self.log_callback:
            self.log_callback(message, level)
        else:
            print(f"[{level}] {message}")

    def validate_url(self, url: str) -> bool:
        """Validate if the URL points to Bilibili domains or shortlinks."""
        if not url:
            return False
        try:
            parsed = urllib.parse.urlparse(url.strip())
            if parsed.scheme not in ("http", "https"):
                return False
            netloc = parsed.netloc.lower()
            if not netloc:
                return False
            
            if ":" in netloc:
                netloc = netloc.split(":")[0]

            is_bilibili = (netloc == "bilibili.com") or netloc.endswith(".bilibili.com")
            is_b23 = (netloc == "b23.tv") or netloc.endswith(".b23.tv")

            if is_bilibili or is_b23:
                return True
        except Exception:
            return False
        return False

    def clean_url(self, url: str) -> str:
        cleaned = url.split('?')[0]
        if BILIBILI_SPACE_DOMAIN in cleaned and "/upload/video" in cleaned:
            cleaned = cleaned.replace("/upload/video", "/video")
        return cleaned

    def check_ffmpeg(self) -> bool:
        base_path = self.config.get("base_path", "")
        exe_dir = self.config.get("exe_dir", "")
        in_path = shutil.which("ffmpeg") is not None
        in_base_dir = os.path.exists(os.path.join(base_path, "ffmpeg.exe")) or os.path.exists(os.path.join(base_path, "ffmpeg"))
        in_exe_dir = os.path.exists(os.path.join(exe_dir, "ffmpeg.exe")) or os.path.exists(os.path.join(exe_dir, "ffmpeg"))
        return in_path or in_base_dir or in_exe_dir

    def get_all_proxies(self) -> List[Optional[str]]:
        exe_dir = self.config.get("exe_dir", "")
        proxy_user = self.config.get("proxy_user", "")
        proxy_pass = self.config.get("proxy_pass", "")
        
        config_file = os.path.join(exe_dir, "config.json")
        custom_proxy_file = None
        if os.path.exists(config_file):
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    cfg_data = json.load(f)
                    custom_proxy_file = cfg_data.get("proxy_file")
            except Exception:
                pass

        proxy_file = None
        if custom_proxy_file and os.path.exists(custom_proxy_file) and os.path.isfile(custom_proxy_file):
            proxy_file = custom_proxy_file
        else:
            proxy_file = os.path.join(exe_dir, "proxies.txt")

        if not os.path.exists(proxy_file):
            return [None]
        try:
            with open(proxy_file, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
            if not lines:
                return [None]
            proxies = []
            for line in lines:
                parts = line.split(":")
                if len(parts) == 4:
                    ip, port, user, password = parts
                    proxies.append(f"http://{user}:{password}@{ip}:{port}")
                elif len(parts) == 2:
                    ip, port = parts
                    if proxy_user and proxy_pass:
                        proxies.append(f"http://{proxy_user}:{proxy_pass}@{ip}:{port}")
                    else:
                        proxies.append(f"http://{ip}:{port}")
                else:
                    if proxy_user and proxy_pass:
                        proxies.append(f"http://{proxy_user}:{proxy_pass}@{line}")
                    else:
                        proxies.append(f"http://{line}")
            return proxies
        except Exception as e:
            logging.error(f"[PROXY ERROR] Failed to read proxy file: {e}")
            return [None]

    def get_rotational_proxy(self) -> Optional[str]:
        proxies = self.get_all_proxies()
        valid = [p for p in proxies if p is not None]
        if not valid:
            return None
        return random.choice(valid)

    def get_retry_pairs(self, primary_browser: Optional[str] = None) -> List[tuple]:
        browsers = self.get_browser_rotation_list(primary_browser)
        proxies = self.get_all_proxies()
        pairs = []
        for p in proxies:
            for b in browsers:
                pairs.append((b, p))
        return pairs

    def get_browser_rotation_list(self, primary_browser: Optional[str] = None) -> List[str]:
        available = list(WORKING_BROWSERS) if WORKING_BROWSERS else ["firefox", "chrome"]
        first = primary_browser if (primary_browser and primary_browser in available) else available[0]
        rotation = [first]
        for b in available:
            if b not in rotation:
                rotation.append(b)
        return rotation

    def analyze(self, data: AnalyzeRequestData) -> dict:
        if hasattr(thread_local_data, 'page_start'):
            del thread_local_data.page_start
        url = self.clean_url(data.url)
        
        pairs = self.get_retry_pairs(data.cookies_browser)
        max_attempts = len(pairs)
        self._log_user(f"Bắt đầu phân tích URL: {url} (Tổng số {max_attempts} tổ hợp Trình duyệt × Proxy)")
        
        last_err = None
        
        for attempt, (browser, proxy) in enumerate(pairs, start=1):
            proxy_info = f" | Proxy: {proxy.split('@')[-1]}" if proxy else " | Không dùng Proxy"
            if attempt == 1:
                self._log_user(f"Lần thử 1/{max_attempts}: Trình duyệt {browser}{proxy_info}")
            else:
                self._log_user(f"Lần thử {attempt}/{max_attempts}: Xoay sang Trình duyệt {browser}{proxy_info}", level="WARNING")
                time.sleep(1.5)
                
            ydl_opts = {
                'extract_flat': True,
                'skip_download': True,
                'sleep_interval_requests': 2,
                'playlistend': 1,
                'logger': YDLLogger(),
                'cookiesfrombrowser': (browser,),
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                    'Referer': 'https://www.bilibili.com/',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                }
            }
                
            if proxy:
                logging.info(f"[ANALYZE] Attempt {attempt}/{max_attempts} - Using Proxy: {proxy.split('@')[-1]} (Cookies: {browser})")
                ydl_opts['proxy'] = proxy

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    
                if 'entries' in info:
                    mid_match = re.search(rf'{re.escape(BILIBILI_SPACE_DOMAIN)}/(\d+)', url)
                    mid = mid_match.group(1) if mid_match else None
                    
                    total_videos = 0
                    if mid and str(mid) in captured_space_video_count:
                        total_videos = captured_space_video_count[str(mid)]
                    else:
                        total_videos = len(info.get('entries', []))

                    total_pages = (total_videos + 29) // 30
                    self._log_user(f"Phân tích Kênh thành công: {info.get('title')} ({total_videos} video)", level="SUCCESS")
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

                    self._log_user(f"Phân tích Video thành công: {info.get('title')}", level="SUCCESS")
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
                logging.warning(f"[ANALYZE ATTEMPT {attempt}/{max_attempts}] Failed with browser {browser}: {err_str}")
                    
        clean_err_msg = str(last_err).replace("\u001b[0;31m", "").replace("\u001b[0m", "")
        self._log_user(f"Lỗi phân tích URL: {clean_err_msg}", level="ERROR")
        raise Exception(f"Loi Bilibili sau 3 lan thu: {clean_err_msg}")

    def download_worker(self, task_id: str, url: str, cookies_browser: str, quality: str, page_start: int, page_end: int, target_dir: str):
        start_time = time.time()
        if self.task_store:
            self.task_store.update_task(task_id, status=TaskStatus.DOWNLOADING)
        
        def hook(d):
            if self.task_store and self.task_store.is_canceled(task_id):
                raise ValueError("CANCELED")
                
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                downloaded = d.get('downloaded_bytes', 0)
                percentage = (downloaded / total * 100) if total > 0 else 0
                
                elapsed = time.time() - start_time
                if self.task_store:
                    self.task_store.update_task(task_id, **{
                        "progress": round(percentage, 2),
                        "speed": d.get('_speed_str', 'N/A'),
                        "eta": d.get('_eta_str', 'N/A'),
                        "elapsed_time": round(elapsed, 1),
                        "filename": os.path.basename(d.get('filename', ''))
                    })
            elif d['status'] == 'finished':
                if self.task_store:
                    self.task_store.update_task(task_id, **{
                        "status": TaskStatus.MERGING,
                        "progress": 99.9
                    })

        has_ffmpeg = self.check_ffmpeg()
        logging.info(f"[TASK {task_id}] Start downloading: {url}")
        logging.info(f"[TASK {task_id}] Target directory: {target_dir}")
        
        if not has_ffmpeg:
            logging.warning(f"[TASK {task_id}] SYSTEM MISSING FFMPEG! Falling back to single merged 'best' format.")
            fmt_str = "best"
        else:
            if quality != "best":
                fmt_str = f"bestvideo[height<={quality}]+bestaudio/best"
            else:
                fmt_str = "bestvideo+bestaudio/best"

        exe_dir = self.config.get("exe_dir", "")
        has_ffmpeg_file = os.path.exists(os.path.join(exe_dir, "ffmpeg.exe")) or os.path.exists(os.path.join(exe_dir, "ffmpeg"))

        ydl_opts = {
            'outtmpl': os.path.join(target_dir, '%(uploader)s/%(title)s.%(ext)s'),
            'format': fmt_str,
            'progress_hooks': [hook],
            'ffmpeg_location': exe_dir if has_ffmpeg_file else None,
            'retries': 3,
            'fragment_retries': 3,
            'sleep_interval': 3,
            'max_sleep_interval': 6,
            'sleep_interval_requests': 2,
            'logger': YDLLogger(),
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Referer': 'https://www.bilibili.com/',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            }
        }

        if BILIBILI_SPACE_DOMAIN in url:
            page_count = page_end - page_start + 1
            ydl_opts['playliststart'] = 1
            ydl_opts['playlistend'] = page_count * 30
            thread_local_data.page_start = page_start
            logging.info(f"[TASK {task_id}] Using page shift: Scan from page {page_start} ({page_count} pages)")
        else:
            ydl_opts['noplaylist'] = True
            if hasattr(thread_local_data, 'page_start'):
                del thread_local_data.page_start

        pairs = self.get_retry_pairs(cookies_browser)
        max_attempts = len(pairs)
        success = False
        last_error_msg = ""

        for attempt, (selected_browser, proxy) in enumerate(pairs, start=1):
            if self.task_store and self.task_store.is_canceled(task_id):
                break
                
            try:
                if self.task_store:
                    self.task_store.update_task(task_id, retry_count=attempt)
                if proxy:
                    logging.info(f"[TASK {task_id}] Attempt {attempt}/{max_attempts} - Using Proxy: {proxy.split('@')[-1]}")
                    ydl_opts['proxy'] = proxy
                else:
                    if 'proxy' in ydl_opts:
                        del ydl_opts['proxy']

                proxy_info = f" | Proxy: {proxy.split('@')[-1]}" if proxy else " | Không dùng Proxy"
                if attempt == 1:
                    logging.info(f"[TASK {task_id}] Loading cookies: {selected_browser}")
                else:
                    self._log_user(f"Lần thử {attempt}/{max_attempts}: Xoay sang Trình duyệt {selected_browser}{proxy_info}", level="WARNING")
                ydl_opts['cookiesfrombrowser'] = (selected_browser,)

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([self.clean_url(url)])
                
                success = True
                self._log_user(f"Tải thành công video: {url}", level="SUCCESS")
                break
                
            except ValueError as ve:
                if str(ve) == "CANCELED":
                    if self.task_store:
                        self.task_store.update_task(task_id, status=TaskStatus.CANCELED)
                    self._log_user(f"Tác vụ bị hủy bởi người dùng.", level="WARNING")
                    break
                last_error_msg = str(ve)
            except Exception as e:
                last_error_msg = str(e)
                logging.error(f"[TASK {task_id}] Error in attempt {attempt}/{max_attempts}: {last_error_msg}")
                if attempt < max_attempts:
                    self._log_user(f"Lần thử {attempt}/{max_attempts} thất bại, thử lại...", level="WARNING")
                    time.sleep(2)

        total_elapsed = time.time() - start_time
        if self.task_store:
            self.task_store.update_task(task_id, elapsed_time=round(total_elapsed, 1))

        if hasattr(thread_local_data, 'page_start'):
            del thread_local_data.page_start

        if self.task_store and self.task_store.is_canceled(task_id):
            return
            
        if success:
            if self.task_store:
                self.task_store.update_task(task_id, status=TaskStatus.COMPLETED, progress=100.0)
        else:
            err_details = f"Loi sau {max_attempts} lan thu: {last_error_msg}"
            if self.task_store:
                self.task_store.update_task(task_id, status=TaskStatus.FAILED, error=err_details)
            self._log_user(f"Tải thất bại sau {max_attempts} lần thử: {last_error_msg}", level="ERROR")

    def space_download_manager(self, master_task_id: str, url: str, cookies_browser: str, quality: str, page_start: int, page_end: int, target_dir: str, max_videos: Optional[int] = None):
        start_time = time.time()
        if self.task_store:
            self.task_store.update_task(master_task_id, status=TaskStatus.DOWNLOADING, filename=f"Đang trích xuất video trang {page_start} - {page_end}...")
        
        page_count = page_end - page_start + 1
        ydl_opts = {
            'extract_flat': True,
            'skip_download': True,
            'playliststart': 1,
            'playlistend': page_count * 30,
            'logger': YDLLogger()
        }
        
        active_browser = cookies_browser or (WORKING_BROWSERS[0] if WORKING_BROWSERS else "firefox")
        ydl_opts['cookiesfrombrowser'] = (active_browser,)
            
        proxy = self.get_rotational_proxy()
        if proxy:
            ydl_opts['proxy'] = proxy

        thread_local_data.page_start = page_start
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.clean_url(url), download=False)
                
            entries = info.get('entries', []) if info else []
            if not entries:
                raise ValueError("Không tìm thấy video nào trong phạm vi trang đã chọn.")
                
            if max_videos and max_videos > 0:
                entries = entries[:max_videos]
                self._log_user(f"Giới hạn số lượng video tải xuống: {len(entries)} video.")

            self._log_user(f"Phân tách thành công {len(entries)} video từ Kênh. Đang đẩy vào hàng chờ...", level="SUCCESS")
            
            for item in entries:
                video_id = item.get('id') or item.get('url')
                if not video_id:
                    continue
                video_title = item.get('title') or f"Video {video_id}"
                video_url = item.get('url') if item.get('url', '').startswith("http") else f"{BILIBILI_VIDEO_BASE_URL.rstrip('/')}/{video_id}"
                    
                sub_task_id = str(uuid.uuid4())
                if self.task_store:
                    self.task_store.create_task(
                        task_id=sub_task_id,
                        module_id="downloader",
                        filename=video_title,
                        target_dir=target_dir
                    )
                self._task_urls[sub_task_id] = video_url
                
                if self.executor:
                    self.executor.submit(
                        self.download_worker,
                        sub_task_id,
                        video_url,
                        cookies_browser,
                        quality,
                        1,
                        1,
                        target_dir
                    )
                
            if self.task_store:
                self.task_store.update_task(master_task_id, **{
                    "status": TaskStatus.COMPLETED,
                    "progress": 100.0,
                    "filename": f"Đã trích xuất xong {len(entries)} video và bắt đầu tải song song.",
                    "elapsed_time": round(time.time() - start_time, 1)
                })
        except Exception as e:
            err_msg = str(e)
            if self.task_store:
                self.task_store.update_task(master_task_id, **{
                    "status": TaskStatus.FAILED,
                    "error": f"Lỗi trích xuất Space: {err_msg}",
                    "elapsed_time": round(time.time() - start_time, 1)
                })
            self._log_user(f"Lỗi trích xuất Kênh: {err_msg}", level="ERROR")
        finally:
            if hasattr(thread_local_data, 'page_start'):
                del thread_local_data.page_start

    def start_download(self, data: DownloadRequestData) -> DownloadTaskResult:
        clean_req_url = self.clean_url(data.url)
        target_dir = data.output_dir or "."
        
        if BILIBILI_SPACE_DOMAIN in clean_req_url:
            master_task_id = str(uuid.uuid4())
            if self.task_store:
                self.task_store.create_task(
                    task_id=master_task_id,
                    module_id="downloader",
                    filename=f"Kênh Bilibili (Trang {data.page_start} - {data.page_end})",
                    target_dir=target_dir
                )
            self._task_urls[master_task_id] = data.url
            if self.executor:
                self.executor.submit(
                    self.space_download_manager,
                    master_task_id,
                    data.url,
                    data.cookies_browser,
                    data.quality,
                    data.page_start,
                    data.page_end,
                    target_dir,
                    data.max_videos
                )
            return DownloadTaskResult(task_id=master_task_id, status="pending")
        else:
            task_id = str(uuid.uuid4())
            if self.task_store:
                self.task_store.create_task(
                    task_id=task_id,
                    module_id="downloader",
                    filename="",
                    target_dir=target_dir
                )
            self._task_urls[task_id] = data.url
            if self.executor:
                self.executor.submit(
                    self.download_worker,
                    task_id,
                    data.url,
                    data.cookies_browser,
                    data.quality,
                    data.page_start,
                    data.page_end,
                    target_dir
                )
            return DownloadTaskResult(task_id=task_id, status="pending")

    def get_tasks(self) -> List[dict]:
        if not self.task_store:
            return []
        tasks = self.task_store.get_all_tasks()
        for t in tasks:
            t["url"] = self._task_urls.get(t["id"], "")
        return tasks

    def clear_tasks(self) -> dict:
        if self.task_store:
            cleared = self.task_store.clear_idle_tasks()
            return {"status": "success", "remaining": len(self.task_store.get_all_tasks())}
        return {"status": "success", "remaining": 0}

    def cancel_task(self, task_id: str) -> dict:
        if self.task_store:
            self.task_store.cancel_task(task_id)
        return {"status": "canceling"}

    def open_task_folder(self, task_id: str) -> dict:
        if not self.task_store:
            raise KeyError("TaskStore not initialized")
        task = self.task_store.get_task(task_id)
        if not task:
            raise KeyError("Task not found")
        target_dir = task.get("target_dir")
        if not target_dir or not os.path.exists(target_dir):
            raise FileNotFoundError("Directory not found")
        
        if sys.platform == "win32":
            os.startfile(target_dir)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target_dir])
        else:
            subprocess.Popen(["xdg-open", target_dir])
        return {"status": "success"}
