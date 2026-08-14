import os
import sys
import uuid
import shutil
import time
import logging
import subprocess
import json
import threading
from typing import Optional
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, BackgroundTasks, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from core.task_store import TaskStore, TaskStatus
from modules.downloader.schemas import AnalyzeRequestData, DownloadRequestData
from modules.downloader.service import DownloaderService
from core.module_registry import ModuleRegistry
from modules.downloader.module import DownloaderModule
from modules.subtitle.module import SubtitleModule
from workflow.engine import WorkflowEngine
from workflow.schemas import WorkflowConfig, StepConfig

# Load environment variables
load_dotenv()

APP_TITLE = os.getenv("APP_TITLE", "Hi Downloader")
app = FastAPI(title=APP_TITLE)

# Domain configurations and file config
from modules.downloader.service import BILIBILI_API_DOMAIN, BILIBILI_VIDEO_BASE_URL
PROXY_FILE_NAME = 'proxies.txt'
BILIBILI_SPACE_DOMAIN = "space.bilibili.com"
DIALOG_TITLE = os.getenv("DIALOG_TITLE", "Chon thu muc luu video")

if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(os.path.abspath(__file__))

# Auto register base_path in PATH for yt-dlp to locate packaged ffmpeg/ffprobe
if base_path not in os.environ.get("PATH", ""):
    os.environ["PATH"] = base_path + os.pathsep + os.environ.get("PATH", "")

STATIC_DIR = os.path.join(base_path, "static")
DOWNLOAD_DIR = os.path.abspath(os.getenv("DOWNLOAD_DIR", "./downloads"))

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

EXE_DIR = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))

from modules.common.paths import get_app_dir
CONFIG_FILE = os.path.join(get_app_dir("config"), os.getenv("CONFIG_FILE", "config.json"))
os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)

# Setup Logging
LOG_FILE = os.path.join(get_app_dir("log"), os.getenv("LOG_FILE", "hi_downloader.log"))
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
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


# User Log Buffer for UI
class UserLogBuffer:
    def __init__(self, max_size: int = 500):
        self.max_size = max_size
        self._buffer: list[dict] = []
        self._lock = threading.Lock()

    def append(self, message: str, level: str = "INFO"):
        timestamp = time.strftime("%H:%M:%S")
        entry = {
            "time": timestamp,
            "level": level,
            "message": message
        }
        with self._lock:
            self._buffer.append(entry)
            if len(self._buffer) > self.max_size:
                self._buffer.pop(0)

    def get_logs(self) -> list[dict]:
        with self._lock:
            return list(self._buffer)

    def clear(self):
        with self._lock:
            self._buffer.clear()


user_log_buffer = UserLogBuffer()


def log_user(message: str, level: str = "INFO"):
    user_log_buffer.append(message, level)
    log_msg = f"[USER] {message}"
    if level == "ERROR":
        logging.error(log_msg)
    elif level == "WARNING":
        logging.warning(log_msg)
    else:
        logging.info(log_msg)


log_user("Khởi động hệ thống thành công.")


# Cache download directory config helpers
def load_cached_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Loi doc file cache config: {e}")
    return {}


def load_cached_dir() -> str:
    config = load_cached_config()
    cached = config.get("download_dir")
    if cached:
        try:
            os.makedirs(cached, exist_ok=True)
            return os.path.abspath(cached)
        except Exception as e:
            logging.warning(f"Khong the tu dong tao thu muc cache {cached}: {e}")
    return DOWNLOAD_DIR


def save_cached_dir(path: str):
    try:
        abs_path = os.path.abspath(path)
        config = load_cached_config()
        config["download_dir"] = abs_path
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        logging.info(f"Da ghi nhan thu muc luu tru vao cache: {abs_path}")
    except Exception as e:
        logging.error(f"Loi ghi file cache config: {e}")


def load_cached_proxy_file() -> Optional[str]:
    config = load_cached_config()
    cached = config.get("proxy_file")
    if cached and os.path.exists(cached) and os.path.isfile(cached):
        return os.path.abspath(cached)
    return None


def load_cached_proxy_mode() -> str:
    config = load_cached_config()
    mode = config.get("proxy_mode", "system")
    if mode not in ["system", "custom", "none"]:
        return "system"
    return mode


def load_cached_proxy_disabled() -> bool:
    config = load_cached_config()
    disabled = config.get("proxy_disabled", False)
    if config.get("proxy_mode") == "none":
        disabled = True
    return disabled


def save_cached_proxy_disabled(disabled: bool):
    try:
        config = load_cached_config()
        config["proxy_disabled"] = disabled
        if disabled:
            config["proxy_mode"] = "none"
        else:
            custom = config.get("proxy_file")
            if custom and os.path.exists(custom) and os.path.isfile(custom):
                config["proxy_mode"] = "custom"
            else:
                config["proxy_mode"] = "system"
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        logging.info(f"Da thiet lap proxy_disabled={disabled}")
    except Exception as e:
        logging.error(f"Loi ghi cache config proxy_disabled: {e}")


def save_cached_proxy_file(path: str):
    try:
        abs_path = os.path.abspath(path)
        config = load_cached_config()
        config["proxy_file"] = abs_path
        config["proxy_mode"] = "custom"
        config["proxy_disabled"] = False
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        logging.info(f"Da ghi nhan file proxy vao cache: {abs_path}")
    except Exception as e:
        logging.error(f"Loi ghi file cache config cho proxy_file: {e}")


def get_run_target_dir(base_dir: str) -> str:
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
    log_user(f"Tạo thư mục lần chạy mới: {run_dir}")
    return run_dir


# ThreadPoolExecutor & TaskStore initiation
PROXY_USER = os.getenv("PROXY_USER", "")
PROXY_PASS = os.getenv("PROXY_PASS", "")
MAX_CONCURRENT_DOWNLOADS = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "2"))

executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_DOWNLOADS)
task_store = TaskStore()

config_downloader = {
    "base_path": base_path,
    "exe_dir": EXE_DIR,
    "download_dir": DOWNLOAD_DIR,
    "proxy_user": PROXY_USER,
    "proxy_pass": PROXY_PASS,
    "log_file": LOG_FILE
}

downloader_service = DownloaderService(
    task_store=task_store,
    executor=executor,
    log_callback=log_user,
    config=config_downloader
)

module_registry = ModuleRegistry()
module_registry.register(DownloaderModule(downloader_service))
module_registry.register(SubtitleModule())

def app_subtitle_provider_runner(video_path: str, params: dict, progress_callback, cancel_event):
    from core.base_module import ModuleContext
    context = ModuleContext(
        task_id=f"batch_job_{uuid.uuid4().hex[:8]}",
        input_files=[video_path],
        output_dir=None,
        params={
            "action": "generate_whisper",
            "video_path": video_path,
            "model": params.get("model", "base"),
            "task": params.get("task", "transcribe"),
            "language": params.get("language")
        },
        cancel_event=cancel_event,
        progress_callback=progress_callback
    )
    
    module = module_registry.get("subtitle")
    res = module.run(context)
    if not res.success:
        if res.canceled or cancel_event.is_set():
            raise RuntimeError("Task was canceled cooperatively")
        raise RuntimeError(res.error or "Lỗi nhận diện phụ đề")
        
    return {
        "srt_text": res.metrics.get("srt_text"),
        "segments": res.metrics.get("segments"),
        "metadata": res.metrics.get("metadata")
    }

from modules.subtitle.batch_service import SubtitleBatchService
subtitle_batch_service = SubtitleBatchService(provider_runner=app_subtitle_provider_runner)

# Initialize Translation Service Cache under isolated app-data path
translate_cache_dir = os.path.join(get_app_dir("cache"), "translate")
os.makedirs(translate_cache_dir, exist_ok=True)
from modules.translate.cache import TranslationCache
translate_cache = TranslationCache(translate_cache_dir)

# Initialize Credentials Store and Provider factory
from modules.translate.credentials import GeminiCredentialStore
from modules.translate.providers.gemini import GeminiTranslateProvider
translate_credential_store = GeminiCredentialStore()

def translate_provider_factory(api_key: str):
    return GeminiTranslateProvider(api_key=api_key)

# Initialize Translation Batch Queue Service
from modules.translate.batch_service import TranslateBatchService
translate_batch_service = TranslateBatchService(
    provider_factory=translate_provider_factory,
    credential_store=translate_credential_store,
    cache=translate_cache
)

# Register TranslateModule in Workflow Registry
from modules.translate.module import TranslateModule
module_registry.register(TranslateModule(
    provider_factory=translate_provider_factory,
    credential_store=translate_credential_store,
    cache=translate_cache
))

# Open Location Callback utilizing app.py safe subprocess logic
def app_open_location_callback(path: str):
    target = os.path.dirname(path) if os.path.isfile(path) else path
    if sys.platform == "win32":
        os.startfile(target)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", target])
    else:
        subprocess.Popen(["xdg-open", target])

# Register Translation Modular APIRouter
from modules.translate.routes import create_translate_router
translate_router = create_translate_router(
    batch_service=translate_batch_service,
    credential_store=translate_credential_store,
    provider_factory=translate_provider_factory,
    open_location_cb=app_open_location_callback
)
app.include_router(translate_router)

@app.on_event("shutdown")
def app_shutdown():
    subtitle_batch_service.shutdown()
    translate_batch_service.shutdown()

workflow_engine = WorkflowEngine(task_store=task_store, module_registry=module_registry)


def reset_run_environment_if_idle():
    tasks = task_store.get_all_tasks()
    has_active = any(t.get("status") in ["downloading", "merging"] for t in tasks)
    if not has_active and tasks:
        task_store.clear_idle_tasks()
        user_log_buffer.clear()
        try:
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [INFO] --- BAT DAU LUOT TAI MOI (BENCHMARK) ---\n")
            log_user("Đã bắt đầu lượt tải mới.")
        except Exception as e:
            logging.error(f"Loi reset log file: {e}")


def check_ffmpeg():
    return downloader_service.check_ffmpeg()


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


# FastAPI Routes
@app.post("/api/analyze")
def analyze_url(req: AnalyzeRequest):
    try:
        data = AnalyzeRequestData(url=req.url, cookies_browser=req.cookies_browser)
        return downloader_service.analyze(data)
    except Exception as e:
        clean_err_msg = str(e).replace("\u001b[0;31m", "").replace("\u001b[0m", "")
        raise HTTPException(status_code=500, detail=clean_err_msg)


@app.post("/api/download")
def trigger_download(req: DownloadRequest):
    reset_run_environment_if_idle()

    base_dir = os.path.abspath(req.output_dir) if req.output_dir else load_cached_dir()
    os.makedirs(base_dir, exist_ok=True)
    save_cached_dir(base_dir)
    
    target_dir = get_run_target_dir(base_dir)
    
    data = DownloadRequestData(
        url=req.url,
        cookies_browser=req.cookies_browser,
        quality=req.quality,
        page_start=req.page_start,
        page_end=req.page_end,
        max_videos=req.max_videos,
        output_dir=target_dir
    )
    
    res = downloader_service.start_download(data)
    return {"task_id": res.task_id, "status": res.status}


@app.post("/api/tasks/clear")
def clear_tasks_api():
    reset_run_environment_if_idle()
    return {"status": "success", "remaining": len(task_store.get_all_tasks())}


@app.post("/api/tasks/{task_id}/open-folder")
def open_task_folder(task_id: str):
    try:
        return downloader_service.open_task_folder(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Task không tồn tại")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Thư mục không tồn tại")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Không thể mở thư mục: {e}")


@app.post("/api/tasks/{task_id}/cancel")
def cancel_task(task_id: str):
    return downloader_service.cancel_task(task_id)


@app.get("/api/tasks")
def get_tasks():
    return downloader_service.get_tasks()


@app.get("/api/system")
def get_system():
    system_path = os.path.join(get_app_dir("config"), PROXY_FILE_NAME)
    system_proxy_file = os.path.abspath(system_path) if os.path.exists(system_path) else None
    return {
        "ffmpeg_installed": check_ffmpeg(),
        "download_dir": load_cached_dir(),
        "proxy_file": load_cached_proxy_file(),
        "system_proxy_file": system_proxy_file,
        "proxy_mode": load_cached_proxy_mode(),
        "proxy_disabled": load_cached_proxy_disabled()
    }


class ProxyModeRequest(BaseModel):
    mode: str


class ProxyDisabledRequest(BaseModel):
    disabled: bool


@app.post("/api/proxy-mode/set")
def set_proxy_mode(req: ProxyModeRequest):
    if req.mode not in ["system", "custom", "none"]:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Chế độ proxy không hợp lệ."})
    try:
        config = load_cached_config()
        config["proxy_mode"] = req.mode
        if req.mode == "none":
            config["proxy_disabled"] = True
        else:
            config["proxy_disabled"] = False
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        logging.info(f"Đã thiết lập chế độ proxy sang: {req.mode}")
        return {"status": "success", "mode": req.mode}
    except Exception as e:
        logging.error(f"Lỗi thiết lập chế độ proxy: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/proxy-disabled/set")
def set_proxy_disabled(req: ProxyDisabledRequest):
    try:
        save_cached_proxy_disabled(req.disabled)
        return {"status": "success", "proxy_disabled": req.disabled}
    except Exception as e:
        logging.error(f"Lỗi thiết lập proxy_disabled: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/proxy-file/clear")
def clear_proxy_file():
    try:
        config = load_cached_config()
        if "proxy_file" in config:
            del config["proxy_file"]
        
        current_mode = config.get("proxy_mode", "system")
        if current_mode != "none":
            config["proxy_mode"] = "system"
        if config.get("proxy_mode") == "none":
            config["proxy_disabled"] = True
        else:
            config["proxy_disabled"] = False
            
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        logging.info("Đã xóa file proxy cá nhân trong cache.")
        return {"status": "success", "message": "Đã xóa file proxy cá nhân."}
    except Exception as e:
        logging.error(f"Lỗi xóa file cache config proxy_file: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Không thể xóa cache: {str(e)}"}
        )


@app.get("/api/logs")
def get_logs():
    return user_log_buffer.get_logs()


@app.post("/api/logs/clear")
def clear_logs():
    user_log_buffer.clear()
    return {"status": "success"}


class ModuleRunRequest(BaseModel):
    params: dict = Field(default_factory=dict)
    input_files: list[str] = Field(default_factory=list)
    output_dir: Optional[str] = None


def run_standalone_module_task(task_id: str, module_id: str, params: dict, input_files: list, output_dir: Optional[str]):
    try:
        module = module_registry.get(module_id)
    except KeyError:
        task_store.update_task(task_id, status=TaskStatus.FAILED, error=f"Module '{module_id}' not found")
        return

    # Setup cancel event
    cancel_event = task_store.get_cancel_event(task_id) or threading.Event()

    # Update status to PROCESSING and set initial milestone to 5% (preparing)
    task = task_store.get_task(task_id)
    current_metrics = task.get("metrics", {}) or {} if task else {}
    updated_metrics = {**current_metrics, "phase": "preparing"}
    task_store.update_task(task_id, status=TaskStatus.PROCESSING, progress=5.0, metrics=updated_metrics)

    # Thread-safe progress callback preserving existing metrics, clamping, and enforcing monotonic increase
    def update_progress(pct: float, phase: str = ""):
        clamped_pct = max(0.0, min(100.0, float(pct)))
        task = task_store.get_task(task_id)
        if task:
            if clamped_pct > task.get("progress", 0.0):
                current_metrics = task.get("metrics", {}) or {}
                updated_metrics = {**current_metrics, "phase": phase}
                task_store.update_task(task_id, progress=clamped_pct, metrics=updated_metrics)

    # Build context
    from core.base_module import ModuleContext
    context = ModuleContext(
        task_id=task_id,
        input_files=input_files,
        output_dir=output_dir,
        params=params,
        cancel_event=cancel_event,
        progress_callback=update_progress
    )

    try:
        res = module.run(context)
        if res.canceled or cancel_event.is_set():
            task_store.update_task(task_id, status=TaskStatus.CANCELED)
        elif not res.success:
            task_store.update_task(task_id, status=TaskStatus.FAILED, error=res.error or "Module run failed")
        else:
            task_store.update_task(
                task_id,
                status=TaskStatus.COMPLETED,
                progress=100.0,
                artifacts=res.output_files,
                metrics=res.metrics
            )
    except Exception as e:
        task_store.update_task(task_id, status=TaskStatus.FAILED, error=str(e))


@app.get("/api/modules")
def get_modules():
    return module_registry.list_module_dicts()


@app.post("/api/modules/{module_id}/run")
def run_module(module_id: str, req: ModuleRunRequest):
    if not module_registry.has(module_id):
        raise HTTPException(status_code=404, detail=f"Module '{module_id}' không tồn tại")

    module = module_registry.get(module_id)
    if not module.metadata.supports_standalone:
        raise HTTPException(status_code=400, detail="Module không hỗ trợ chạy độc lập (standalone)")

    if not module.validate_params(req.params):
        raise HTTPException(status_code=400, detail="Tham số không hợp lệ cho module")

    task_id = f"run_{module_id}_{uuid.uuid4().hex[:8]}"
    if module.metadata.requires_output_dir:
        base_dir = os.path.abspath(req.output_dir) if req.output_dir else load_cached_dir()
        os.makedirs(base_dir, exist_ok=True)
        save_cached_dir(base_dir)
        target_dir = get_run_target_dir(base_dir)
    else:
        target_dir = None

    # Create pending task in task_store
    task_store.create_task(
        task_id=task_id,
        module_id=module_id,
        filename=f"Standalone: {module.metadata.name}",
        target_dir=target_dir
    )

    # Submit task execution to thread executor
    executor.submit(run_standalone_module_task, task_id, module_id, req.params, req.input_files, target_dir)

    return {"task_id": task_id, "status": "pending"}


class ScanFolderRequest(BaseModel):
    folder_path: str


class SaveImportedSrtRequest(BaseModel):
    source_path: str
    content: str


@app.post("/api/subtitle/scan-folder")
def api_scan_folder(req: ScanFolderRequest):
    try:
        from modules.subtitle.batch_service import scan_video_folder
        res = scan_video_folder(req.folder_path)
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Lỗi quét thư mục: {str(e)}")


@app.post("/api/subtitle/save-imported-srt")
def api_save_imported_srt(req: SaveImportedSrtRequest):
    try:
        from modules.subtitle.batch_service import save_imported_srt
        res = save_imported_srt(req.source_path, req.content)
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Lỗi lưu file phụ đề: {str(e)}")


class CreateBatchRequest(BaseModel):
    video_paths: list[str]
    provider: str
    model: str = "base"
    language: Optional[str] = None
    concurrency: int = 2


class BatchActionRequest(BaseModel):
    action: str
    job_ids: list[str]


@app.post("/api/subtitle/batches")
def api_create_batch(req: CreateBatchRequest):
    prov = req.provider.lower()
    if prov == "ocr":
        raise HTTPException(status_code=400, detail="OCR method is not implemented yet")
    if prov != "whisper":
        raise HTTPException(status_code=400, detail="Unsupported provider")

    if not (1 <= req.concurrency <= 10):
        raise HTTPException(status_code=400, detail="Concurrency must be between 1 and 10")

    if not req.video_paths:
        raise HTTPException(status_code=400, detail="Danh sách video không được trống")

    seen = set()
    unique_paths = [p for p in req.video_paths if not (p in seen or seen.add(p))]

    allowed_exts = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}
    for p in unique_paths:
        if not os.path.exists(p):
            raise HTTPException(status_code=400, detail=f"Tệp tin không tồn tại: {p}")
        if not os.path.isfile(p):
            raise HTTPException(status_code=400, detail=f"Đường dẫn không phải tệp thường: {p}")
        _, ext = os.path.splitext(p)
        if ext.lower() not in allowed_exts:
            raise HTTPException(status_code=400, detail=f"Định dạng tệp không được hỗ trợ: {p}")

    try:
        provider_params = {
            "model": req.model,
            "language": req.language,
            "task": "transcribe"
        }
        batch_id = subtitle_batch_service.create_batch(
            files=unique_paths,
            provider_params=provider_params,
            concurrency=req.concurrency
        )
        subtitle_batch_service.start_batch(batch_id)
        
        snap = subtitle_batch_service.get_batch_snapshot(batch_id)
        if snap is None:
            raise HTTPException(status_code=500, detail="Lỗi tạo snapshot cho batch")
            
        snap["provider"] = req.provider
        snap["provider_params"] = provider_params
        
        return {
            "batch_id": batch_id,
            "snapshot": snap
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Không thể khởi tạo batch: {str(e)}")


@app.get("/api/subtitle/batches/{batch_id}")
def api_get_batch(batch_id: str):
    snap = subtitle_batch_service.get_batch_snapshot(batch_id)
    if not snap:
        raise HTTPException(status_code=404, detail="Batch không tồn tại")
        
    with subtitle_batch_service.lock:
        batch = subtitle_batch_service.batches.get(batch_id)
        if batch:
            snap["provider"] = "whisper"
            snap["provider_params"] = batch.get("provider_params", {})
            
    return snap


@app.post("/api/subtitle/batches/{batch_id}/action")
def api_batch_action(batch_id: str, req: BatchActionRequest):
    act = req.action.lower()
    if act not in ["cancel", "retry", "save"]:
        raise HTTPException(status_code=400, detail="Action không hợp lệ")

    if not req.job_ids:
        raise HTTPException(status_code=400, detail="Danh sách job_ids không được trống")

    snap = subtitle_batch_service.get_batch_snapshot(batch_id)
    if not snap:
        raise HTTPException(status_code=404, detail="Batch không tồn tại")

    if act == "cancel":
        outcomes = subtitle_batch_service.cancel_batch_jobs(batch_id, req.job_ids)
        return {"success": True, "results": outcomes}

    elif act == "retry":
        try:
            outcomes = subtitle_batch_service.retry_batch_jobs(batch_id, req.job_ids)
            return {"success": True, "results": outcomes}
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e))

    elif act == "save":
        outcomes = {}
        for jid in req.job_ids:
            job_snap = next((j for j in snap["jobs"] if j["job_id"] == jid), None)
            if not job_snap:
                outcomes[jid] = {"outcome": "skipped", "reason": "Job không tồn tại trong batch"}
                continue

            if job_snap["status"] != "done" or not job_snap["srt_text"]:
                outcomes[jid] = {"outcome": "skipped", "reason": "Job chưa hoàn thành hoặc không có nội dung phụ đề"}
                continue

            video_path = job_snap["video_path"]
            try:
                video_dir = os.path.dirname(video_path)
                video_name = os.path.basename(video_path)
                base_name, _ = os.path.splitext(video_name)
                srt_path = os.path.join(video_dir, base_name + ".srt")

                import tempfile
                temp_fd, temp_path = tempfile.mkstemp(dir=video_dir, prefix=".tmp_srt_", suffix=".srt")
                try:
                    with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                        f.write(job_snap["srt_text"])
                    os.replace(temp_path, srt_path)
                except Exception as ex:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                    raise ex

                saved_abs = os.path.abspath(srt_path)
                subtitle_batch_service.update_job_saved_path(batch_id, jid, saved_abs)
                outcomes[jid] = {
                    "outcome": "applied",
                    "reason": None,
                    "saved_path": saved_abs
                }
            except Exception as e:
                outcomes[jid] = {"outcome": "skipped", "reason": f"Không thể lưu file: {str(e)}"}

        return {"success": True, "results": outcomes}


class UpdateJobSrtRequest(BaseModel):
    srt_text: str
    segments: list


@app.post("/api/subtitle/batches/{batch_id}/jobs/{job_id}/update-srt")
def update_job_srt(batch_id: str, job_id: str, req: UpdateJobSrtRequest):
    if not req.srt_text or not req.srt_text.strip():
        raise HTTPException(status_code=400, detail="Nội dung phụ đề không được để trống")

    if not isinstance(req.segments, list):
        raise HTTPException(status_code=400, detail="Danh sách segments không hợp lệ")

    for seg in req.segments:
        if not isinstance(seg, dict):
            raise HTTPException(status_code=400, detail="Segment phải là một đối tượng")
        required_keys = {"index", "start_ms", "end_ms", "text"}
        if not required_keys.issubset(seg.keys()):
            raise HTTPException(status_code=400, detail=f"Segment thiếu trường bắt buộc")
        if not isinstance(seg["index"], int) or not isinstance(seg["start_ms"], int) or not isinstance(seg["end_ms"], int) or not isinstance(seg["text"], str):
            raise HTTPException(status_code=400, detail="Kiểu dữ liệu của các trường trong segment không hợp lệ")

    snap = subtitle_batch_service.get_batch_snapshot(batch_id)
    if not snap:
        raise HTTPException(status_code=404, detail="Batch không tồn tại")

    job_snap = next((j for j in snap["jobs"] if j["job_id"] == job_id), None)
    if not job_snap:
        raise HTTPException(status_code=404, detail="Job không tồn tại trong batch")

    if job_snap["status"] != "done":
        raise HTTPException(status_code=400, detail="Chỉ có thể cập nhật và lưu các tác vụ đã hoàn thành")

    video_path = job_snap["video_path"]
    try:
        video_dir = os.path.dirname(video_path)
        video_name = os.path.basename(video_path)
        base_name, _ = os.path.splitext(video_name)
        srt_path = os.path.join(video_dir, base_name + ".srt")

        import tempfile
        temp_fd, temp_path = tempfile.mkstemp(dir=video_dir, prefix=".tmp_srt_", suffix=".srt")
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                f.write(req.srt_text)
            os.replace(temp_path, srt_path)
        except Exception as ex:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise ex

        saved_abs = os.path.abspath(srt_path)
        
        success = subtitle_batch_service.update_job_content(
            batch_id=batch_id,
            job_id=job_id,
            srt_text=req.srt_text,
            segments=req.segments,
            saved_path=saved_abs
        )
        if not success:
            raise HTTPException(status_code=500, detail="Không thể cập nhật trạng thái job trong bộ nhớ")

        updated_snap = subtitle_batch_service.get_batch_snapshot(batch_id)
        
        return {
            "status": "success",
            "saved_path": saved_abs,
            "snapshot": updated_snap
        }
    except Exception as e:
        logging.error(f"Loi cap nhat va luu file SRT cho job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Không thể cập nhật và lưu file SRT: {str(e)}")


class StepRunRequest(BaseModel):
    step_id: str
    module_id: str
    params: dict = Field(default_factory=dict)
    on_error: str = "stop"


class WorkflowRunRequest(BaseModel):
    workflow_id: Optional[str] = None
    name: str
    steps: list[StepRunRequest] = Field(default_factory=list)
    output_dir: Optional[str] = None
    initial_inputs: list[str] = Field(default_factory=list)


def run_workflow_task(task_id: str, config: WorkflowConfig):
    try:
        res = workflow_engine.execute_workflow(task_id, config)
        serialized_res = res.to_dict()
        
        # update task in task_store with serialized result under key "workflow"
        task_store.update_task(
            task_id,
            metrics={"workflow": serialized_res}
        )
        
        # update status, error or progress if not already completed/failed/canceled
        task = task_store.get_task(task_id)
        if task and task.get("status") not in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELED):
            if res.canceled:
                task_store.update_task(task_id, status=TaskStatus.CANCELED)
            elif not res.success:
                task_store.update_task(task_id, status=TaskStatus.FAILED, error=res.error or "Workflow failed")
            else:
                task_store.update_task(task_id, status=TaskStatus.COMPLETED, progress=100.0, artifacts=res.final_outputs)
    except Exception as e:
        task_store.update_task(task_id, status=TaskStatus.FAILED, error=str(e))


@app.post("/api/workflows/run")
def run_workflow(req: WorkflowRunRequest):
    # validate workflow name
    if not req.name or not req.name.strip():
        raise HTTPException(status_code=400, detail="Tên workflow không được để trống")

    # validate at least one step
    if not req.steps:
        raise HTTPException(status_code=400, detail="Workflow phải có ít nhất 1 bước (step)")

    # validate each step module exists and supports workflow, and on_error is valid
    steps_config = []
    seen_step_ids = set()
    for step in req.steps:
        # validate step_id and module_id
        if not step.step_id or not step.step_id.strip():
            raise HTTPException(status_code=400, detail="ID của step không được để trống")
        if not step.module_id or not step.module_id.strip():
            raise HTTPException(status_code=400, detail="ID của module không được để trống")
            
        sid = step.step_id.strip()
        if sid in seen_step_ids:
            raise HTTPException(status_code=400, detail=f"ID của step '{sid}' bị trùng lặp")
        seen_step_ids.add(sid)

        if step.on_error not in ("stop", "skip"):
            raise HTTPException(status_code=400, detail=f"Giá trị on_error '{step.on_error}' không hợp lệ (chỉ chấp nhận 'stop' hoặc 'skip')")

        if not module_registry.has(step.module_id):
            raise HTTPException(status_code=404, detail=f"Module '{step.module_id}' không tồn tại trong hệ thống")

        module = module_registry.get(step.module_id)
        if not module.metadata.supports_workflow:
            raise HTTPException(status_code=400, detail=f"Module '{step.module_id}' không hỗ trợ chạy trong workflow")

        # Convert step request model to StepConfig schema
        steps_config.append(StepConfig(
            step_id=sid,
            module_id=step.module_id.strip(),
            params=step.params,
            on_error=step.on_error
        ))

    # Resolve workflow_id
    wf_id = req.workflow_id or f"wf_{uuid.uuid4().hex[:8]}"
    task_id = f"wf_{uuid.uuid4().hex[:8]}"

    # Resolve output directory
    base_dir = os.path.abspath(req.output_dir) if req.output_dir else load_cached_dir()
    os.makedirs(base_dir, exist_ok=True)
    save_cached_dir(base_dir)

    target_dir = get_run_target_dir(base_dir)

    # Convert to WorkflowConfig
    config = WorkflowConfig(
        workflow_id=wf_id,
        name=req.name,
        steps=steps_config,
        output_dir=target_dir,
        initial_inputs=req.initial_inputs
    )

    # create task in TaskStore with module_id="workflow"
    task_store.create_task(
        task_id=task_id,
        module_id="workflow",
        filename=req.name,
        target_dir=target_dir
    )

    # Submit execution to background executor
    executor.submit(run_workflow_task, task_id, config)

    return {"task_id": task_id, "workflow_id": wf_id, "status": "pending"}


# Display/Xauthority prober helper for Linux
def get_gui_env() -> dict:
    env = os.environ.copy()
    
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
            
    if sys.platform.startswith("linux") and ("XAUTHORITY" not in env or not env["XAUTHORITY"]):
        home = os.path.expanduser("~")
        xauth_file = os.path.join(home, ".Xauthority")
        if os.path.exists(xauth_file):
            env["XAUTHORITY"] = xauth_file
            logging.info(f"[XAUTHORITY PROBER] Tu dong set XAUTHORITY={xauth_file}")
            
    return env


@app.post("/api/select-directory")
def select_directory():
    env = get_gui_env()

    if sys.platform.startswith("linux"):
        if shutil.which("zenity"):
            try:
                cmd = ["zenity", "--file-selection", "--directory", f"--title={DIALOG_TITLE}"]
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

        if shutil.which("kdialog"):
            try:
                cmd = ["kdialog", "--getexistingdirectory", ".", "--title", DIALOG_TITLE]
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

    if sys.platform == "darwin":
        try:
            cmd = ["osascript", "-e", f'POSIX path of (choose folder with prompt "{DIALOG_TITLE}")']
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

    try:
        cmd = [
            sys.executable,
            "-c",
            f"import tkinter as tk; from tkinter import filedialog; root=tk.Tk(); root.withdraw(); root.attributes('-topmost', True); print(filedialog.askdirectory(title='{DIALOG_TITLE}'))"
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

    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Không thể kết nối đến giao diện màn hình Desktop của hệ điều hành. Vui lòng kiểm tra cổng DISPLAY hoặc khởi chạy lại ứng dụng bằng terminal mặc định ngoài màn hình chính."
        }
    )


@app.post("/api/subtitle/select-video-folder")
def select_video_folder():
    env = get_gui_env()
    dialog_title = "Chọn thư mục chứa video phụ đề"

    if sys.platform.startswith("linux"):
        if shutil.which("zenity"):
            try:
                cmd = ["zenity", "--file-selection", "--directory", f"--title={dialog_title}"]
                output = subprocess.check_output(cmd, env=env, text=True, stderr=subprocess.PIPE, timeout=60)
                path = output.strip()
                if path:
                    return {"status": "success", "path": os.path.abspath(path)}
            except subprocess.CalledProcessError as cpe:
                if cpe.returncode == 1:
                    logging.info("Nguoi dung da huy chon thu muc video qua Zenity.")
                    return {"status": "canceled", "path": None}
                logging.warning(f"Zenity loi: {cpe.stderr.decode('utf-8', errors='ignore')}")
            except Exception as e:
                logging.warning(f"Zenity that bai: {e}")

        if shutil.which("kdialog"):
            try:
                cmd = ["kdialog", "--getexistingdirectory", ".", "--title", dialog_title]
                output = subprocess.check_output(cmd, env=env, text=True, stderr=subprocess.PIPE, timeout=60)
                path = output.strip()
                if path:
                    return {"status": "success", "path": os.path.abspath(path)}
            except subprocess.CalledProcessError as cpe:
                if cpe.returncode == 1:
                    logging.info("Nguoi dung da huy chon thu muc video qua Kdialog.")
                    return {"status": "canceled", "path": None}
                logging.warning(f"Kdialog loi: {cpe.stderr.decode('utf-8', errors='ignore')}")
            except Exception as e:
                logging.warning(f"Kdialog that bai: {e}")

    if sys.platform == "darwin":
        try:
            cmd = ["osascript", "-e", f'POSIX path of (choose folder with prompt "{dialog_title}")']
            output = subprocess.check_output(cmd, env=env, text=True, stderr=subprocess.PIPE, timeout=60)
            path = output.strip()
            if path:
                return {"status": "success", "path": os.path.abspath(path)}
        except subprocess.CalledProcessError:
            logging.info("Nguoi dung da huy chon thu muc video qua AppleScript.")
            return {"status": "canceled", "path": None}
        except Exception as e:
            logging.warning(f"AppleScript that bai: {e}")

    try:
        cmd = [
            sys.executable,
            "-c",
            f"import tkinter as tk; from tkinter import filedialog; root=tk.Tk(); root.withdraw(); root.attributes('-topmost', True); print(filedialog.askdirectory(title='{dialog_title}'))"
        ]
        output = subprocess.check_output(cmd, env=env, text=True, stderr=subprocess.PIPE, timeout=60)
        path = output.strip()
        if path:
            return {"status": "success", "path": os.path.abspath(path)}
        else:
            logging.info("Nguoi dung da huy chon thu muc video qua Tkinter Subprocess.")
            return {"status": "canceled", "path": None}
    except Exception as e:
        err_msg = str(e)
        if hasattr(e, 'stderr') and e.stderr:
            err_msg = e.stderr.strip()
        logging.error(f"Khong the mo bat ky hop thoai do hoa nao cua OS de chon thu muc video: {err_msg}")

    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Không thể kết nối đến giao diện màn hình Desktop để chọn thư mục video."
        }
    )


@app.post("/api/select-proxy-file")
def select_proxy_file():
    env = get_gui_env()
    dialog_title = "Chon file proxy txt"

    if sys.platform.startswith("linux"):
        if shutil.which("zenity"):
            try:
                cmd = ["zenity", "--file-selection", "--file-filter=*.txt", f"--title={dialog_title}"]
                output = subprocess.check_output(cmd, env=env, text=True, stderr=subprocess.PIPE, timeout=60)
                path = output.strip()
                if path:
                    abs_path = os.path.abspath(path)
                    save_cached_proxy_file(abs_path)
                    return {"status": "success", "path": abs_path}
            except subprocess.CalledProcessError as cpe:
                if cpe.returncode == 1:
                    logging.info("Nguoi dung da huy chon file proxy qua Zenity.")
                    return {"status": "canceled", "path": None}
                logging.warning(f"Zenity loi hoac thieu DISPLAY: {cpe.stderr.decode('utf-8', errors='ignore')}")
            except Exception as e:
                logging.warning(f"Zenity that bai: {e}")

        if shutil.which("kdialog"):
            try:
                cmd = ["kdialog", "--getopenfilename", ".", "*.txt", "--title", dialog_title]
                output = subprocess.check_output(cmd, env=env, text=True, stderr=subprocess.PIPE, timeout=60)
                path = output.strip()
                if path:
                    abs_path = os.path.abspath(path)
                    save_cached_proxy_file(abs_path)
                    return {"status": "success", "path": abs_path}
            except subprocess.CalledProcessError as cpe:
                if cpe.returncode == 1:
                    logging.info("Nguoi dung da huy chon file proxy qua Kdialog.")
                    return {"status": "canceled", "path": None}
                logging.warning(f"Kdialog loi: {cpe.stderr.decode('utf-8', errors='ignore')}")
            except Exception as e:
                logging.warning(f"Kdialog that bai: {e}")

    if sys.platform == "darwin":
        try:
            cmd = ["osascript", "-e", 'POSIX path of (choose file of type {"txt"} with prompt "Chon file proxy txt")']
            output = subprocess.check_output(cmd, env=env, text=True, stderr=subprocess.PIPE, timeout=60)
            path = output.strip()
            if path:
                abs_path = os.path.abspath(path)
                save_cached_proxy_file(abs_path)
                return {"status": "success", "path": abs_path}
        except subprocess.CalledProcessError:
            logging.info("Nguoi dung da huy chon file proxy qua AppleScript.")
            return {"status": "canceled", "path": None}
        except Exception as e:
            logging.warning(f"AppleScript that bai: {e}")

    try:
        cmd = [
            sys.executable,
            "-c",
            f"import tkinter as tk; from tkinter import filedialog; root=tk.Tk(); root.withdraw(); root.attributes('-topmost', True); print(filedialog.askopenfilename(filetypes=[('Text files', '*.txt')], title='{dialog_title}'))"
        ]
        output = subprocess.check_output(cmd, env=env, text=True, stderr=subprocess.PIPE, timeout=60)
        path = output.strip()
        if path:
            abs_path = os.path.abspath(path)
            save_cached_proxy_file(abs_path)
            return {"status": "success", "path": abs_path}
        else:
            logging.info("Nguoi dung da huy chon file proxy qua Tkinter Subprocess.")
            return {"status": "canceled", "path": None}
    except Exception as e:
        err_msg = str(e)
        if hasattr(e, 'stderr') and e.stderr:
            err_msg = e.stderr.strip()
        logging.error(f"Khong the mo bat ky hop thoai do hoa nao cua OS de chon file proxy: {err_msg}")

    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Không thể kết nối đến giao diện màn hình Desktop của hệ điều hành để chọn file proxy."
        }
    )


@app.post("/api/select-video-file")
def select_video_file():
    env = get_gui_env()
    dialog_title = "Chon file video"

    if sys.platform.startswith("linux"):
        if shutil.which("zenity"):
            try:
                cmd = ["zenity", "--file-selection", "--file-filter=*.mp4 *.mkv *.mov *.avi *.webm *.m4v", f"--title={dialog_title}"]
                output = subprocess.check_output(cmd, env=env, text=True, stderr=subprocess.PIPE, timeout=60)
                path = output.strip()
                if path:
                    abs_path = os.path.abspath(path)
                    return {"status": "success", "path": abs_path}
            except subprocess.CalledProcessError as cpe:
                if cpe.returncode == 1:
                    logging.info("Nguoi dung da huy chon file video qua Zenity.")
                    return {"status": "canceled", "path": None}
                logging.warning(f"Zenity loi hoac thieu DISPLAY: {cpe.stderr.decode('utf-8', errors='ignore')}")
            except Exception as e:
                logging.warning(f"Zenity that bai: {e}")

        if shutil.which("kdialog"):
            try:
                cmd = ["kdialog", "--getopenfilename", ".", "*.mp4 *.mkv *.mov *.avi *.webm *.m4v", "--title", dialog_title]
                output = subprocess.check_output(cmd, env=env, text=True, stderr=subprocess.PIPE, timeout=60)
                path = output.strip()
                if path:
                    abs_path = os.path.abspath(path)
                    return {"status": "success", "path": abs_path}
            except subprocess.CalledProcessError as cpe:
                if cpe.returncode == 1:
                    logging.info("Nguoi dung da huy chon file video qua Kdialog.")
                    return {"status": "canceled", "path": None}
                logging.warning(f"Kdialog loi: {cpe.stderr.decode('utf-8', errors='ignore')}")
            except Exception as e:
                logging.warning(f"Kdialog that bai: {e}")

    if sys.platform == "darwin":
        try:
            cmd = ["osascript", "-e", 'POSIX path of (choose file of type {"mp4", "mkv", "mov", "avi", "webm", "m4v"} with prompt "Chon file video")']
            output = subprocess.check_output(cmd, env=env, text=True, stderr=subprocess.PIPE, timeout=60)
            path = output.strip()
            if path:
                abs_path = os.path.abspath(path)
                return {"status": "success", "path": abs_path}
        except subprocess.CalledProcessError:
            logging.info("Nguoi dung da huy chon file video qua AppleScript.")
            return {"status": "canceled", "path": None}
        except Exception as e:
            logging.warning(f"AppleScript that bai: {e}")

    try:
        cmd = [
            sys.executable,
            "-c",
            f"import tkinter as tk; from tkinter import filedialog; root=tk.Tk(); root.withdraw(); root.attributes('-topmost', True); print(filedialog.askopenfilename(filetypes=[('Video files', ('*.mp4', '*.mkv', '*.mov', '*.avi', '*.webm', '*.m4v'))], title='{dialog_title}'))"
        ]
        output = subprocess.check_output(cmd, env=env, text=True, stderr=subprocess.PIPE, timeout=60)
        path = output.strip()
        if path:
            abs_path = os.path.abspath(path)
            return {"status": "success", "path": abs_path}
        else:
            logging.info("Nguoi dung da huy chon file video qua Tkinter Subprocess.")
            return {"status": "canceled", "path": None}
    except Exception as e:
        err_msg = str(e)
        if hasattr(e, 'stderr') and e.stderr:
            err_msg = e.stderr.strip()
        logging.error(f"Khong the mo bat ky hop thoai do hoa nao cua OS de chon file video: {err_msg}")

    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Không thể kết nối đến giao diện màn hình Desktop của hệ điều hành. Vui lòng kiểm tra cổng DISPLAY hoặc khởi chạy lại ứng dụng bằng terminal mặc định ngoài màn hình chính."
        }
    )


@app.post("/api/select-srt-file")
def select_srt_file():
    env = get_gui_env()
    dialog_title = "Chon file phu de SRT"

    path = None
    if sys.platform.startswith("linux"):
        if shutil.which("zenity"):
            try:
                cmd = ["zenity", "--file-selection", "--file-filter=*.srt", f"--title={dialog_title}"]
                output = subprocess.check_output(cmd, env=env, text=True, stderr=subprocess.PIPE, timeout=60)
                path = output.strip()
            except subprocess.CalledProcessError as cpe:
                if cpe.returncode == 1:
                    logging.info("Nguoi dung da huy chon file srt qua Zenity.")
                    return {"status": "canceled", "path": None}
                logging.warning(f"Zenity loi hoac thieu DISPLAY: {cpe.stderr.decode('utf-8', errors='ignore')}")
            except Exception as e:
                logging.warning(f"Zenity that bai: {e}")

        if not path and shutil.which("kdialog"):
            try:
                cmd = ["kdialog", "--getopenfilename", ".", "*.srt", "--title", dialog_title]
                output = subprocess.check_output(cmd, env=env, text=True, stderr=subprocess.PIPE, timeout=60)
                path = output.strip()
            except subprocess.CalledProcessError as cpe:
                if cpe.returncode == 1:
                    logging.info("Nguoi dung da huy chon file srt qua Kdialog.")
                    return {"status": "canceled", "path": None}
                logging.warning(f"Kdialog loi: {cpe.stderr.decode('utf-8', errors='ignore')}")
            except Exception as e:
                logging.warning(f"Kdialog that bai: {e}")

    if not path and sys.platform == "darwin":
        try:
            cmd = ["osascript", "-e", 'POSIX path of (choose file of type {"srt"} with prompt "Chon file phu de SRT")']
            output = subprocess.check_output(cmd, env=env, text=True, stderr=subprocess.PIPE, timeout=60)
            path = output.strip()
        except subprocess.CalledProcessError:
            logging.info("Nguoi dung da huy chon file srt qua AppleScript.")
            return {"status": "canceled", "path": None}
        except Exception as e:
            logging.warning(f"AppleScript that bai: {e}")

    if not path:
        try:
            cmd = [
                sys.executable,
                "-c",
                f"import tkinter as tk; from tkinter import filedialog; root=tk.Tk(); root.withdraw(); root.attributes('-topmost', True); print(filedialog.askopenfilename(filetypes=[('SRT files', '*.srt')], title='{dialog_title}'))"
            ]
            output = subprocess.check_output(cmd, env=env, text=True, stderr=subprocess.PIPE, timeout=60)
            path = output.strip()
            if not path:
                logging.info("Nguoi dung da huy chon file srt qua Tkinter Subprocess.")
                return {"status": "canceled", "path": None}
        except Exception as e:
            err_msg = str(e)
            if hasattr(e, 'stderr') and e.stderr:
                err_msg = e.stderr.strip()
            logging.error(f"Khong the mo bat ky hop thoai do hoa nao cua OS de chon file srt: {err_msg}")

    if not path:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Không thể kết nối đến giao diện màn hình Desktop của hệ điều hành để chọn file srt."
            }
        )

    try:
        abs_path = os.path.abspath(path)
        with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return {"status": "success", "path": abs_path, "content": content}
    except Exception as e:
        logging.error(f"Loi doc file srt: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Không thể đọc file srt: {str(e)}"
            }
        )


class SaveSrtRequest(BaseModel):
    video_path: str
    content: str


class OpenFileLocationRequest(BaseModel):
    path: str


@app.post("/api/subtitle/save-srt")
def save_srt(req: SaveSrtRequest):
    if not req.video_path.strip():
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Đường dẫn tệp video không được để trống."}
        )
    
    try:
        video_dir = os.path.dirname(req.video_path)
        video_name = os.path.basename(req.video_path)
        base_name, _ = os.path.splitext(video_name)
        srt_filename = base_name + ".srt"
        srt_path = os.path.join(video_dir, srt_filename)
        
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(req.content)
            
        logging.info(f"Da xuat file SRT thanh cong: {srt_path}")
        return {"status": "success", "path": os.path.abspath(srt_path)}
    except Exception as e:
        logging.error(f"Loi luu file SRT: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Không thể lưu file SRT: {str(e)}"}
        )


@app.post("/api/subtitle/open-file-location")
def open_file_location(req: OpenFileLocationRequest):
    path = req.path.strip()
    if not path:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Đường dẫn không được để trống."}
        )
    
    if not os.path.exists(path):
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Tệp tin hoặc thư mục không tồn tại."}
        )
        
    try:
        target = os.path.dirname(path) if os.path.isfile(path) else path
        if sys.platform == "win32":
            os.startfile(target)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])
        return {"status": "success"}
    except Exception as e:
        logging.error(f"Loi mo vi tri file: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Không thể mở vị trí file: {str(e)}"}
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
