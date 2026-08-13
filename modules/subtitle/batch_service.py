import os
import time
import uuid
import copy
import threading
import tempfile
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List, Dict, Any, Callable


class SubtitleBatchService:
    def __init__(self, provider_runner: Optional[Callable] = None):
        """
        Initialize the Subtitle Batch Service with a dedicated bounded ThreadPoolExecutor.
        provider_runner: A callable with signature:
            (video_path: str, params: dict, progress_callback: Callable[[float, str], None], cancel_event: threading.Event) -> dict
        """
        self.provider_runner = provider_runner
        self.batches: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()
        # Isolated thread pool dedicated to subtitle jobs
        self.executor = ThreadPoolExecutor(max_workers=10)
        self.dispatcher_threads: List[threading.Thread] = []
        self.is_shutdown = False

    def shutdown(self):
        """Explicit clean shutdown of the underlying executor and dispatcher threads."""
        with self.lock:
            if self.is_shutdown:
                return
            self.is_shutdown = True
            
            # Cancel all waiting and running jobs in all active batches cooperatively
            for batch in self.batches.values():
                batch["cancel_event"].set()
                for job in batch["jobs"]:
                    job["cancel_event"].set()
                    if job["status"] == "waiting":
                        job["status"] = "canceled"
                        job["phase"] = "canceled"

        # Shutdown job executor, waiting for active threads to wrap up
        self.executor.shutdown(wait=True)

        # Wait for all dispatcher daemon threads to settle
        for t in self.dispatcher_threads:
            if t.is_alive():
                t.join()

    def create_batch(self, files: List[str], provider_params: dict, concurrency: int = 2) -> str:
        """
        Create a new batch of subtitle jobs.
        """
        with self.lock:
            if self.is_shutdown:
                raise RuntimeError("Service has been shutdown")

        if not (1 <= concurrency <= 10):
            raise ValueError("Concurrency limit must be between 1 and 10 inclusive.")

        batch_id = f"batch_{uuid.uuid4().hex[:8]}"
        
        jobs = []
        for file_path in files:
            job_id = f"job_{uuid.uuid4().hex[:8]}"
            display_name = file_path
            # Truncate path to maximum 3 segments for display
            parts = file_path.replace("\\", "/").split("/")
            if len(parts) > 3:
                display_name = ".../" + "/".join(parts[-3:])

            job = {
                "job_id": job_id,
                "batch_id": batch_id,
                "video_path": file_path,
                "display_name": display_name,
                "status": "waiting",
                "progress": 0.0,
                "phase": "preparing",
                "elapsed_time": 0.0,
                "error": None,
                "srt_text": None,
                "segments": None,
                "saved_path": None,
                "detected_language": None,
                "cancel_event": threading.Event()
            }
            jobs.append(job)

        batch = {
            "batch_id": batch_id,
            "status": "waiting",
            "concurrency": concurrency,
            "created_at": time.time(),
            "start_time": None,
            "settle_time": None,
            "jobs": jobs,
            "cancel_event": threading.Event(),
            "provider_params": copy.deepcopy(provider_params),
            "active_futures": []
        }

        with self.lock:
            self.batches[batch_id] = batch

        return batch_id

    def start_batch(self, batch_id: str):
        """Submit the batch task execution to the isolated thread pool."""
        with self.lock:
            if self.is_shutdown:
                raise RuntimeError("Service has been shutdown")
            batch = self.batches.get(batch_id)
            if not batch:
                return
            if batch["status"] != "waiting":
                return
            batch["status"] = "running"

        # Dispatch execution on dedicated background dispatcher thread (isolated from self.executor)
        t = threading.Thread(target=self._dispatch_batch, args=(batch_id,), daemon=True)
        with self.lock:
            self.dispatcher_threads.append(t)
        t.start()

    def _dispatch_batch(self, batch_id: str):
        with self.lock:
            batch = self.batches.get(batch_id)
            if not batch:
                return
            concurrency = batch["concurrency"]

        semaphore = threading.Semaphore(concurrency)
        futures = []

        with self.lock:
            jobs_list = list(batch["jobs"])

        for job_def in jobs_list:
            # Check for cancellation before picking up from queue under lock
            with self.lock:
                if self.is_shutdown or batch["cancel_event"].is_set():
                    if job_def["status"] == "waiting":
                        job_def["status"] = "canceled"
                        job_def["phase"] = "canceled"
                    continue
                if job_def["status"] != "waiting":
                    continue
                job_id = job_def["job_id"]

            # Bounded dispatch: Block on semaphore slot availability
            semaphore.acquire()

            # Double check conditions under lock AFTER acquiring semaphore slot
            with self.lock:
                if self.is_shutdown or batch["cancel_event"].is_set() or job_def["cancel_event"].is_set() or job_def["status"] == "canceled":
                    semaphore.release()
                    if job_def["status"] == "waiting":
                        job_def["status"] = "canceled"
                        job_def["phase"] = "canceled"
                    continue

                # Submit task to job executor (only active running tasks enter the ThreadPoolExecutor)
                try:
                    future = self.executor.submit(self._run_job, batch_id, job_id, semaphore)
                    futures.append(future)
                except RuntimeError:
                    semaphore.release()
                    if job_def["status"] == "waiting":
                        job_def["status"] = "canceled"
                        job_def["phase"] = "canceled"
                    continue

        # Wait for all submitted futures in this dispatch pass to resolve
        for f in futures:
            try:
                f.result()
            except Exception:
                pass

        # Update batch overall settled status
        self._settle_batch(batch_id)

    def _run_job(self, batch_id: str, job_id: str, semaphore: threading.Semaphore):
        try:
            with self.lock:
                if self.is_shutdown:
                    return
                batch = self.batches.get(batch_id)
                if not batch:
                    return
                job = next((j for j in batch["jobs"] if j["job_id"] == job_id), None)
                if not job:
                    return

                if batch["cancel_event"].is_set() or job["cancel_event"].is_set() or job["status"] == "canceled":
                    job["status"] = "canceled"
                    job["phase"] = "canceled"
                    return

                # Mark start of first job as the start of the batch wall-clock
                if batch["start_time"] is None:
                    batch["start_time"] = time.time()

                job["status"] = "running"
                job["phase"] = "preparing"
                job["progress"] = 5.0
                video_path = job["video_path"]
                provider_params = copy.deepcopy(batch["provider_params"])
                job_cancel_event = job["cancel_event"]

            job_start_time = time.time()
            error_occurred = None
            res = None
            result_srt = None
            result_segments = None

            # Progress callback logic preserving metrics, clamping, and enforcing monotonicity under lock
            def progress_callback(pct: float, phase: str = ""):
                clamped_pct = max(0.0, min(100.0, float(pct)))
                with self.lock:
                    if clamped_pct > job["progress"]:
                        job["progress"] = clamped_pct
                        job["phase"] = phase

            try:
                if self.provider_runner:
                    res = self.provider_runner(
                        video_path,
                        provider_params,
                        progress_callback,
                        job_cancel_event
                    )
                    # Deep copy return values
                    result_srt = copy.deepcopy(res.get("srt_text"))
                    result_segments = copy.deepcopy(res.get("segments"))
                else:
                    # Fallback default runner
                    progress_callback(100.0, "completed")
            except Exception as e:
                error_occurred = str(e)

            job_elapsed = time.time() - job_start_time

            with self.lock:
                job["elapsed_time"] = job_elapsed
                if job["cancel_event"].is_set():
                    job["status"] = "canceled"
                    job["phase"] = "canceled"
                elif error_occurred:
                    job["status"] = "error"
                    job["phase"] = "failed"
                    job["error"] = error_occurred
                else:
                    job["status"] = "done"
                    job["phase"] = "completed"
                    job["progress"] = 100.0
                    job["srt_text"] = result_srt
                    job["segments"] = result_segments
                    if res and isinstance(res, dict) and "metadata" in res:
                        meta = res.get("metadata")
                        if meta and "raw_language" in meta:
                            job["detected_language"] = meta["raw_language"]

        finally:
            semaphore.release()

    def _settle_batch(self, batch_id: str):
        with self.lock:
            batch = self.batches.get(batch_id)
            if not batch:
                return

            # Check if all jobs settled
            all_settled = all(j["status"] in ("done", "error", "canceled") for j in batch["jobs"])
            if all_settled:
                batch["settle_time"] = time.time()
                # If any job failed or was canceled, set batch to error, otherwise done
                has_failures = any(j["status"] in ("error", "canceled") for j in batch["jobs"])
                batch["status"] = "error" if has_failures else "done"

    def cancel_batch_jobs(self, batch_id: str, job_ids: List[str]) -> Dict[str, Dict[str, str]]:
        """
        Cancel a selection of jobs.
        Returns outcome per-job outcomes mapping.
        """
        outcomes = {}
        with self.lock:
            batch = self.batches.get(batch_id)
            if not batch:
                return {}

            for job in batch["jobs"]:
                if job["job_id"] not in job_ids:
                    continue

                status = job["status"]
                if status == "waiting":
                    job["status"] = "canceled"
                    job["phase"] = "canceled"
                    outcomes[job["job_id"]] = {"outcome": "applied", "reason": "Job canceled while waiting in queue."}
                elif status == "running":
                    job["cancel_event"].set()
                    outcomes[job["job_id"]] = {"outcome": "applied", "reason": "Cancellation signal sent to running job."}
                else:
                    outcomes[job["job_id"]] = {"outcome": "skipped", "reason": f"Job is already in settled status: {status}."}

        # Check if cancellation requires triggering batch settlement update
        self._settle_batch(batch_id)
        return outcomes

    def retry_batch_jobs(self, batch_id: str, job_ids: List[str]) -> Dict[str, Dict[str, str]]:
        """
        Retry a selection of error or canceled jobs within the same batch.
        """
        outcomes = {}
        jobs_to_restart = []

        with self.lock:
            if self.is_shutdown:
                raise RuntimeError("Service has been shutdown")
            batch = self.batches.get(batch_id)
            if not batch:
                return {}

            for job in batch["jobs"]:
                if job["job_id"] not in job_ids:
                    continue

                status = job["status"]
                if status in ("error", "canceled"):
                    job["status"] = "waiting"
                    job["progress"] = 0.0
                    job["phase"] = "preparing"
                    job["error"] = None
                    job["elapsed_time"] = 0.0
                    job["cancel_event"] = threading.Event()
                    outcomes[job["job_id"]] = {"outcome": "applied", "reason": "Job reset to waiting state."}
                    jobs_to_restart.append(job)
                else:
                    outcomes[job["job_id"]] = {"outcome": "skipped", "reason": f"Only error or canceled jobs can be retried. Status: {status}."}

            if jobs_to_restart:
                # If batch was settled, reset times and status to run again
                if batch["status"] in ("done", "error"):
                    batch["status"] = "running"
                    batch["settle_time"] = None

        if jobs_to_restart:
            t = threading.Thread(target=self._dispatch_batch, args=(batch_id,), daemon=True)
            with self.lock:
                self.dispatcher_threads.append(t)
            t.start()

        return outcomes

    def update_job_saved_path(self, batch_id: str, job_id: str, saved_path: str):
        """
        Update the saved path for a specific job within a batch.
        """
        with self.lock:
            batch = self.batches.get(batch_id)
            if not batch:
                return
            job = next((j for j in batch["jobs"] if j["job_id"] == job_id), None)
            if job:
                job["saved_path"] = saved_path

    def update_job_content(self, batch_id: str, job_id: str, srt_text: str, segments: list, saved_path: str = None):
        """
        Update srt_text, segments, and optionally saved_path for a specific job within a batch.
        """
        with self.lock:
            batch = self.batches.get(batch_id)
            if not batch:
                return False
            job = next((j for j in batch["jobs"] if j["job_id"] == job_id), None)
            if job:
                job["srt_text"] = srt_text
                job["segments"] = segments
                if saved_path is not None:
                    job["saved_path"] = saved_path
                return True
            return False

    def get_batch_snapshot(self, batch_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a defensive read-only snapshot of a batch.
        """
        with self.lock:
            batch = self.batches.get(batch_id)
            if not batch:
                return None

            # Calculate total duration based on wall-clock elapsed time
            total_duration = 0.0
            if batch["start_time"] is not None:
                if batch["settle_time"] is not None:
                    total_duration = batch["settle_time"] - batch["start_time"]
                else:
                    total_duration = time.time() - batch["start_time"]

            parent_provider = batch.get("provider") or "whisper"
            if parent_provider.lower() not in ("whisper", "ocr"):
                parent_provider = "whisper"
                
            raw_lang = batch.get("provider_params", {}).get("language")
            if not raw_lang or raw_lang.strip().lower() in ("auto", "none", "null", ""):
                normalized_lang = "auto"
            else:
                normalized_lang = raw_lang.strip()

            jobs_snapshots = []
            for j in batch["jobs"]:
                jobs_snapshots.append({
                    "job_id": j["job_id"],
                    "batch_id": j["batch_id"],
                    "video_path": j["video_path"],
                    "display_name": j["display_name"],
                    "status": j["status"],
                    "progress": j["progress"],
                    "phase": j["phase"],
                    "elapsed_time": j["elapsed_time"],
                    "error": j["error"],
                    "srt_text": j["srt_text"],
                    "segments": j["segments"],
                    "saved_path": j["saved_path"],
                    "provider": parent_provider,
                    "language": j.get("detected_language") or normalized_lang,
                    "detected_language": j.get("detected_language")
                })

            # Calculate counters for stats (waiting, running, done, error - grouping canceled in error)
            stats = {"waiting": 0, "running": 0, "done": 0, "error": 0}
            for j in batch["jobs"]:
                st = j["status"]
                if st == "waiting":
                    stats["waiting"] += 1
                elif st == "running":
                    stats["running"] += 1
                elif st == "done":
                    stats["done"] += 1
                elif st in ("error", "canceled"):
                    stats["error"] += 1

            snapshot = {
                "batch_id": batch["batch_id"],
                "status": batch["status"],
                "concurrency": batch["concurrency"],
                "created_at": batch["created_at"],
                "start_time": batch["start_time"],
                "settle_time": batch["settle_time"],
                "total_duration": total_duration,
                "jobs": jobs_snapshots,
                "stats": stats
            }
            # Return deep-copy of snapshot to ensure read-only safety
            return copy.deepcopy(snapshot)


def scan_video_folder(folder_path: str) -> dict:
    """
    Scan direct children files of the resolved absolute local directory.
    Rejects missing or non-directory paths. Ignore symlinks and folders.
    Sorted case-insensitively by filename.
    """
    path = os.path.abspath(folder_path)
    if not os.path.exists(path):
        raise ValueError(f"Thư mục không tồn tại: {folder_path}")
    if not os.path.isdir(path):
        raise ValueError(f"Đường dẫn không phải là thư mục: {folder_path}")

    allowed_extensions = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}
    files = []
    
    try:
        entries = os.listdir(path)
    except PermissionError:
        raise PermissionError(f"Không có quyền truy cập thư mục: {folder_path}")
    except Exception as e:
        raise ValueError(f"Lỗi đọc thư mục: {str(e)}")

    for entry in entries:
        entry_path = os.path.join(path, entry)
        if os.path.islink(entry_path):
            continue
        if not os.path.isfile(entry_path):
            continue
            
        _, ext = os.path.splitext(entry)
        if ext.lower() in allowed_extensions:
            try:
                stat = os.stat(entry_path)
                files.append({
                    "name": entry,
                    "path": os.path.abspath(entry_path),
                    "size": stat.st_size
                })
            except Exception:
                continue

    # Case-insensitive deterministic alphabetical sort
    files.sort(key=lambda x: x["name"].lower())

    return {
        "folder_path": path,
        "total": len(files),
        "files": files
    }


def save_imported_srt(source_path: str, content: str) -> dict:
    """
    Save the edited SRT text as a sibling file named <stem>_edit.srt.
    Guarantees no modification of the original source file.
    Gives overwrite functionality and writes atomically.
    """
    src_abs = os.path.abspath(source_path)
    if not os.path.exists(src_abs):
        raise ValueError(f"Tệp nguồn không tồn tại: {source_path}")
    if not os.path.isfile(src_abs):
        raise ValueError(f"Đường dẫn không phải là tệp thường: {source_path}")
    if not src_abs.lower().endswith(".srt"):
        raise ValueError(f"Đường dẫn không phải tệp .srt: {source_path}")
        
    parent = os.path.dirname(src_abs)
    filename = os.path.basename(src_abs)
    stem, _ = os.path.splitext(filename)
    target_path = os.path.join(parent, f"{stem}_edit.srt")
    
    # Atomic write to temporary file beside target
    temp_fd, temp_path = tempfile.mkstemp(dir=parent, prefix=".tmp_srt_", suffix=".srt")
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            f.write(content)
        # atomic replace
        os.replace(temp_path, target_path)
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        raise e

    return {
        "status": "success",
        "source_path": src_abs,
        "saved_path": target_path
    }
