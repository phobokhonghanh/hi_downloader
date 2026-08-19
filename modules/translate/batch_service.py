import os
import re
import time
import uuid
import copy
import threading
import tempfile
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List, Dict, Any, Callable


def clean_target_language_slug(target_lang: str) -> str:
    """Creates a clean filename slug containing only Unicode letters, numbers, hyphens, and underscores."""
    if not target_lang or not target_lang.strip():
        raise ValueError("Ngôn ngữ đích không được để trống.")
        
    # Keep Unicode alphanumeric characters, hyphens, and underscores
    cleaned = re.sub(r'[^\w\-]', '_', target_lang.strip())
    # Collapse sequential underscores
    cleaned = re.sub(r'_+', '_', cleaned).strip('_')

    reserved = {"con", "prn", "aux", "nul"}
    if not cleaned:
        raise ValueError("Ngôn ngữ đích sau khi chuẩn hóa không được để trống.")
        
    cleaned_lower = cleaned.lower()
    if cleaned_lower in reserved or cleaned_lower.startswith("com") or cleaned_lower.startswith("lpt"):
        raise ValueError(f"Tên ngôn ngữ đích '{target_lang}' là từ khóa hệ thống được bảo vệ.")
        
    return cleaned


def sanitize_translation_error(e: Exception) -> str:
    err_str = str(e)
    # Masking out potential Gemini API Keys (AIzaSy...)
    err_str = re.sub(r"AIzaSy[A-Za-z0-9_-]{33}", "[API_KEY_MASKED]", err_str)
    
    # Classify errors and map to short concise Vietnamese messages
    err_lower = err_str.lower()
    if "api key" in err_lower or "apikey" in err_lower or "credentials" in err_lower or "chưa được cấu hình" in err_lower:
        return "Lỗi cấu hình API key. Vui lòng kiểm tra lại thiết lập khóa API."
    elif "quota" in err_lower or "rate limit" in err_lower or "429" in err_str:
        return "Vượt quá giới hạn lượt yêu cầu (Rate Limit). Vui lòng thử lại sau."
    elif "blocked" in err_lower or "safety" in err_lower:
        return "Nội dung bị chặn bởi bộ lọc an toàn của AI."
    elif "unsupported schema" in err_lower or "additional_properties" in err_lower:
        return "Cấu trúc phản hồi không được hỗ trợ bởi model hiện tại."
    elif "connection" in err_lower or "timeout" in err_lower or "network" in err_lower:
        return "Lỗi kết nối mạng. Vui lòng kiểm tra lại đường truyền internet hoặc proxy."
    elif "bad request" in err_lower or "400" in err_str:
        return "Yêu cầu dịch không hợp lệ (400 Bad Request)."
    elif "unauthorized" in err_lower or "401" in err_str:
        return "Khóa API không hợp lệ hoặc đã hết hạn."
    
    return "Quá trình dịch thuật thất bại do lỗi hệ thống AI."



class TranslateBatchService:

    def __init__(
        self,
        provider_factory: Callable[[str], Any],
        credential_store: Any,
        cache: Any,
        max_workers_limit: int = 10,
        clock: Optional[Any] = None
    ):
        """
        Initialize the isolated Translate Batch Service.
        provider_factory: Callable API key -> provider instance
        credential_store: Credentials store for key lookup
        cache: Optional TranslationCache instance
        """
        self.provider_factory = provider_factory
        self.credential_store = credential_store
        self.cache = cache
        self.max_workers_limit = max_workers_limit
        self.clock = clock or time
        self.batches: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()
        
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers_limit)
        self.dispatcher_threads: List[threading.Thread] = []
        self.is_shutdown = False

    def shutdown(self) -> None:
        """Idempotent clean shutdown of the underlying executor and dispatcher threads."""
        with self.lock:
            if self.is_shutdown:
                return
            self.is_shutdown = True

            # Set cancel event for all active batches and jobs
            for batch in self.batches.values():
                batch["cancel_event"].set()
                for job in batch["jobs"]:
                    job["cancel_event"].set()
                    if job["status"] == "waiting":
                        job["status"] = "canceled"
                        job["phase"] = "Đã hủy"

        # Shutdown job executor, waiting for active threads to wrap up
        self.executor.shutdown(wait=True)

        # Wait for all dispatcher daemon threads to settle (bounded join)
        with self.lock:
            threads_to_join = list(self.dispatcher_threads)
        for t in threads_to_join:
            if t.is_alive():
                t.join(timeout=1.0)
        
        with self.lock:
            self.dispatcher_threads.clear()

    def create_batch(
        self,
        files: List[str],
        target_language: str,
        profile: str,
        concurrency: int = 2,
        enable_time_constraint: bool = True,
        target_wps: float = 3.8
    ) -> str:
        """
        Create a new translation batch after validating the paths.
        """
        with self.lock:
            if self.is_shutdown:
                raise RuntimeError("Dịch vụ đã dừng hoạt động.")

        if not (1 <= concurrency <= 10):
            raise ValueError("Độ song song (concurrency) phải nằm trong khoảng 1 đến 10.")

        slug = clean_target_language_slug(target_language)

        # Deduplicate files preserving order
        deduped = []
        seen = set()
        for f in files:
            abs_f = os.path.abspath(f)
            if abs_f not in seen:
                seen.add(abs_f)
                deduped.append(abs_f)

        if not deduped:
            raise ValueError("Danh sách tệp tin không được để trống.")

        jobs = []
        for f in deduped:
            if not os.path.exists(f):
                raise ValueError(f"Tệp tin không tồn tại: {f}")
            if not os.path.isfile(f):
                raise ValueError(f"Đường dẫn không phải là tệp: {f}")
            if os.path.islink(f):
                raise ValueError(f"Không chấp nhận liên kết symlink: {f}")
            if not f.lower().endswith(".srt"):
                raise ValueError(f"Tệp không có phần mở rộng .srt: {f}")

            # Overwrite check using the clean target language slug
            filename = os.path.basename(f)
            stem, _ = os.path.splitext(filename)
            if stem.endswith(f"_{slug}"):
                raise ValueError(f"Tệp nguồn '{filename}' trùng tên với định dạng đầu ra '{slug}'.")

            job_id = f"t_job_{uuid.uuid4().hex[:8]}"
            job = {
                "job_id": job_id,
                "source_path": f,
                "display_name": filename,
                "status": "waiting",
                "progress": 0.0,
                "phase": "Chờ dịch",
                "elapsed_time": 0.0,
                "error": None,
                "saved_path": None,
                "restored_chunks": 0,
                "translated_chunks": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "context_metadata": None,
                "cancel_event": threading.Event()
            }
            jobs.append(job)

        batch_id = f"t_batch_{uuid.uuid4().hex[:8]}"
        batch = {
            "batch_id": batch_id,
            "status": "waiting",
            "concurrency": concurrency,
            "target_language": target_language,
            "profile": profile,
            "enable_time_constraint": enable_time_constraint,
            "target_wps": target_wps,
            "created_at": self.clock.time(),
            "start_time": None,
            "settle_time": None,
            "jobs": jobs,
            "cancel_event": threading.Event()
        }


        with self.lock:
            self.batches[batch_id] = batch

        return batch_id

    def start_batch(self, batch_id: str) -> None:
        """Starts batch daemon execution thread."""
        with self.lock:
            if self.is_shutdown:
                raise RuntimeError("Dịch vụ đã dừng hoạt động.")
            batch = self.batches.get(batch_id)
            if not batch or batch["status"] != "waiting":
                return
            batch["status"] = "running"
            batch["start_time"] = self.clock.time()

        t = threading.Thread(target=self._dispatch_batch, args=(batch_id,), daemon=True)
        with self.lock:
            self.dispatcher_threads.append(t)
        t.start()

    def _dispatch_batch(self, batch_id: str) -> None:
        with self.lock:
            batch = self.batches.get(batch_id)
            if not batch:
                return
            concurrency = batch["concurrency"]
            jobs_list = list(batch["jobs"])

        cond = threading.Condition(self.lock)
        running_count = 0

        def job_done_callback():
            nonlocal running_count
            with self.lock:
                running_count -= 1
                cond.notify_all()

        for job in jobs_list:
            with self.lock:
                # Wait on condition until slots are free
                while running_count >= concurrency and not self.is_shutdown and not batch["cancel_event"].is_set():
                    cond.wait(timeout=0.1)

                if self.is_shutdown or batch["cancel_event"].is_set() or job["cancel_event"].is_set():
                    if job["status"] == "waiting":
                        job["status"] = "canceled"
                        job["phase"] = "Đã hủy"
                    continue

                if job["status"] != "waiting":
                    continue

                job["status"] = "running"
                job["phase"] = "Khởi chạy"
                running_count += 1
                job_id = job["job_id"]

            self.executor.submit(self._execute_job, batch_id, job_id, job_done_callback)

        # Wait for all running threads in this dispatcher to wrap up
        with self.lock:
            while running_count > 0:
                cond.wait(timeout=0.1)
            self._check_batch_completion_locked(batch_id)

        # Remove self thread reference upon completion
        current_thread = threading.current_thread()
        with self.lock:
            if current_thread in self.dispatcher_threads:
                self.dispatcher_threads.remove(current_thread)

    def _execute_job(self, batch_id: str, job_id: str, job_done_callback: Callable[[], None]) -> None:
        job_found_and_running = False
        with self.lock:
            batch = self.batches.get(batch_id)
            if batch:
                job = next((j for j in batch["jobs"] if j["job_id"] == job_id), None)
                if job and job["status"] == "running":
                    job_found_and_running = True
                    cancel_event = job["cancel_event"]
                    target_language = batch["target_language"]
                    profile = batch["profile"]
                    source_path = job["source_path"]
                    enable_time_constraint = batch.get("enable_time_constraint", True)
                    target_wps = batch.get("target_wps", 3.8)

        if not job_found_and_running:
            job_done_callback()
            return

        start_time = self.clock.time()

        try:
            if cancel_event.is_set():
                raise RuntimeError("Tiến trình dịch đã bị hủy.")

            # Resolve credentials once per job dynamically
            api_key = self.credential_store.resolve()
            if not api_key:
                raise ValueError("API Key cho Google Gemini chưa được cấu hình.")

            # Construct provider and service instance
            provider = self.provider_factory(api_key)
            from modules.translate.service import TranslationService
            from modules.translate.schemas import TranslationConfig
            
            service = TranslationService(provider)

            # Read SRT file content
            with open(source_path, "r", encoding="utf-8") as f:
                srt_text = f.read()

            from modules.subtitle.srt import parse_srt, export_srt
            segments = parse_srt(srt_text)

            config = TranslationConfig(
                target_language=target_language,
                model=profile,
                enable_time_constraint=enable_time_constraint,
                target_wps=target_wps
            )


            # Thread-safe updates callback
            def progress_cb(pct, status_msg):
                with self.lock:
                    job["progress"] = pct
                    job["phase"] = status_msg

            res = service.translate(
                segments=segments,
                config=config,
                cancel_event=cancel_event,
                progress_callback=progress_cb,
                cache=self.cache
            )

            if not res.success:
                raise RuntimeError(res.error)

            # Atomic save beside source
            translated_srt = export_srt(res.translated_segments)
            parent_dir = os.path.dirname(source_path)
            stem, _ = os.path.splitext(os.path.basename(source_path))
            slug = clean_target_language_slug(target_language)
            out_path = os.path.join(parent_dir, f"{stem}_{slug}.srt")

            # Ensure resolved output parent equals source parent
            if os.path.dirname(os.path.abspath(out_path)) != os.path.abspath(parent_dir):
                raise ValueError("Đường dẫn lưu tệp dịch không an toàn.")

            # Temp atomic replace
            fd, tmp_path = tempfile.mkstemp(dir=parent_dir, prefix="tmp_trans_")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(translated_srt)
                os.replace(tmp_path, out_path)
            except Exception as e:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass
                raise e

            with self.lock:
                job["status"] = "done"
                job["phase"] = "Hoàn tất"
                job["progress"] = 100.0
                job["saved_path"] = os.path.abspath(out_path)
                job["result_segments"] = [seg.to_dict() for seg in res.translated_segments]
                job["restored_chunks"] = res.metrics.get("restored_chunks", 0)
                job["translated_chunks"] = res.metrics.get("translated_chunks", 0)
                job["input_tokens"] = provider.last_token_usage.get("input_tokens", 0)
                job["output_tokens"] = provider.last_token_usage.get("output_tokens", 0)
                job["total_tokens"] = provider.last_token_usage.get("total_tokens", 0)
                job["context_metadata"] = res.metrics.get("context_metadata")

        except Exception as e:
            import logging
            logger = logging.getLogger("hi_downloader")
            logger.error(f"Chi tiết lỗi translation job {job_id}: {str(e)}", exc_info=True)
            with self.lock:
                if cancel_event.is_set() or "hủy" in str(e).lower() or "canceled" in str(e).lower():
                    job["status"] = "canceled"
                    job["phase"] = "Đã hủy"
                else:
                    job["status"] = "error"
                    job["phase"] = "Thất bại"
                    job["error"] = sanitize_translation_error(e)
                if not job.get("context_metadata"):
                    job["context_metadata"] = {
                        "source_language_code": "und",
                        "source_language_name": "Không xác định",
                        "summary": "Không xác định",
                        "tone": "Không xác định",
                        "addressing_style": "Không xác định",
                        "content_type": "Không xác định"
                    }
        finally:
            end_time = self.clock.time()
            with self.lock:
                job["elapsed_time"] = round(end_time - start_time, 2)
            
            job_done_callback()
            self._check_batch_completion(batch_id)

    def _check_batch_completion_locked(self, batch_id: str) -> None:
        """Core completion check logic. Assumes self.lock is already held by calling context."""
        batch = self.batches.get(batch_id)
        if not batch:
            return

        all_done = True
        has_failed = False
        has_canceled = False

        for j in batch["jobs"]:
            if j["status"] in ("waiting", "running"):
                all_done = False
                break
            if j["status"] == "error":
                has_failed = True
            elif j["status"] == "canceled":
                has_canceled = True

        if all_done:
            if has_failed:
                batch["status"] = "error"
            elif has_canceled:
                batch["status"] = "canceled"
            else:
                batch["status"] = "done"
            batch["settle_time"] = self.clock.time()

    def _check_batch_completion(self, batch_id: str) -> None:
        """Thread-safe public completion checker wrapper."""
        with self.lock:
            self._check_batch_completion_locked(batch_id)

    def get_batch(self, batch_id: str) -> Optional[Dict[str, Any]]:
        """Returns a deep defensive snapshot copy of the requested batch."""
        with self.lock:
            batch = self.batches.get(batch_id)
            if not batch:
                return None

            stats = {"waiting": 0, "running": 0, "done": 0, "error": 0, "canceled": 0, "total": 0}
            total_duration = 0.0
            input_tokens = 0
            output_tokens = 0
            total_tokens = 0

            for j in batch["jobs"]:
                status = j["status"]
                if status in stats:
                    stats[status] += 1
                stats["total"] += 1
                
                total_duration += j.get("elapsed_time", 0.0) or 0.0
                input_tokens += j.get("input_tokens", 0) or 0
                output_tokens += j.get("output_tokens", 0) or 0
                total_tokens += j.get("total_tokens", 0) or 0

            snapshot = {
                "batch_id": batch["batch_id"],
                "status": batch["status"],
                "concurrency": batch["concurrency"],
                "target_language": batch["target_language"],
                "profile": batch["profile"],
                "created_at": batch["created_at"],
                "start_time": batch["start_time"],
                "settle_time": batch["settle_time"],
                "stats": stats,
                "total_duration": round(total_duration, 2),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "jobs": []
            }

            for j in batch["jobs"]:
                j_snap = {
                    "job_id": j["job_id"],
                    "source_path": j["source_path"],
                    "display_name": j["display_name"],
                    "status": j["status"],
                    "progress": j["progress"],
                    "phase": j["phase"],
                    "elapsed_time": j["elapsed_time"],
                    "error": j["error"],
                    "saved_path": j["saved_path"],
                    "restored_chunks": j["restored_chunks"],
                    "translated_chunks": j["translated_chunks"],
                    "input_tokens": j["input_tokens"],
                    "output_tokens": j["output_tokens"],
                    "total_tokens": j["total_tokens"],
                    "context_metadata": j.get("context_metadata") or {
                        "source_language_code": "und",
                        "source_language_name": "Không xác định",
                        "summary": "Không xác định",
                        "tone": "Không xác định",
                        "addressing_style": "Không xác định",
                        "content_type": "Không xác định"
                    }
                }
                snapshot["jobs"].append(j_snap)

            return copy.deepcopy(snapshot)

    def cancel_job(self, batch_id: str, job_id: str) -> bool:
        """Cancels a single job in the batch if waiting or running."""
        with self.lock:
            batch = self.batches.get(batch_id)
            if not batch:
                return False
            job = next((j for j in batch["jobs"] if j["job_id"] == job_id), None)
            if not job:
                return False

            if job["status"] == "waiting":
                job["status"] = "canceled"
                job["phase"] = "Đã hủy"
                job["cancel_event"].set()
                self._check_batch_completion_locked(batch_id)
                return True
            elif job["status"] == "running":
                job["cancel_event"].set()
                return True
            return False

    def cancel_all(self, batch_id: str) -> bool:
        """Cancels all active jobs in the batch."""
        with self.lock:
            batch = self.batches.get(batch_id)
            if not batch:
                return False
            batch["cancel_event"].set()
            for job in batch["jobs"]:
                if job["status"] in ("waiting", "running"):
                    job["cancel_event"].set()
                    if job["status"] == "waiting":
                        job["status"] = "canceled"
                        job["phase"] = "Đã hủy"
            self._check_batch_completion_locked(batch_id)
            return True

    def retry_job(self, batch_id: str, job_id: str) -> bool:
        """Retries a failed or canceled job in the batch."""
        with self.lock:
            batch = self.batches.get(batch_id)
            if not batch:
                return False
            job = next((j for j in batch["jobs"] if j["job_id"] == job_id), None)
            if not job:
                return False

            if job["status"] not in ("error", "canceled"):
                return False

            job["status"] = "waiting"
            job["progress"] = 0.0
            job["phase"] = "Chờ dịch lại"
            job["error"] = None
            job["saved_path"] = None
            job["restored_chunks"] = 0
            job["translated_chunks"] = 0
            job["input_tokens"] = 0
            job["output_tokens"] = 0
            job["total_tokens"] = 0
            job["cancel_event"] = threading.Event()

            if batch["status"] in ("done", "error", "canceled"):
                batch["status"] = "running"
                batch["settle_time"] = None

        t = threading.Thread(target=self._dispatch_batch, args=(batch_id,), daemon=True)
        with self.lock:
            self.dispatcher_threads.append(t)
        t.start()
        return True

    def retry_all(self, batch_id: str) -> bool:
        """Retries all failed or canceled jobs in the batch."""
        retried_any = False
        with self.lock:
            batch = self.batches.get(batch_id)
            if not batch:
                return False

            for job in batch["jobs"]:
                if job["status"] in ("error", "canceled"):
                    job["status"] = "waiting"
                    job["progress"] = 0.0
                    job["phase"] = "Chờ dịch lại"
                    job["error"] = None
                    job["saved_path"] = None
                    job["restored_chunks"] = 0
                    job["translated_chunks"] = 0
                    job["input_tokens"] = 0
                    job["output_tokens"] = 0
                    job["total_tokens"] = 0
                    job["cancel_event"] = threading.Event()
                    retried_any = True

            if retried_any:
                if batch["status"] in ("done", "error", "canceled"):
                    batch["status"] = "running"
                    batch["settle_time"] = None

        if retried_any:
            t = threading.Thread(target=self._dispatch_batch, args=(batch_id,), daemon=True)
            with self.lock:
                self.dispatcher_threads.append(t)
            t.start()
            return True
        return False

    def get_job_compare(self, batch_id: str, job_id: str) -> Dict[str, Any]:
        """
        Returns source and translated rows aligned by index with timestamps/text,
        only when output exists and validates.
        """
        with self.lock:
            batch = self.batches.get(batch_id)
            if not batch:
                raise ValueError("Không tìm thấy batch.")
            job = next((j for j in batch["jobs"] if j["job_id"] == job_id), None)
            if not job:
                raise ValueError("Không tìm thấy job.")
            
            if job["status"] != "done" or not job["saved_path"]:
                raise ValueError("Job chưa hoàn thành hoặc chưa có tệp dịch.")
            
            source_path = job["source_path"]
            saved_path = job["saved_path"]

        if not os.path.exists(saved_path):
            raise ValueError("Không tìm thấy tệp dịch đầu ra.")

        from modules.subtitle.srt import parse_srt
        with open(source_path, "r", encoding="utf-8") as f:
            src_text = f.read()
        with open(saved_path, "r", encoding="utf-8") as f:
            trans_text = f.read()

        src_segs = parse_srt(src_text)
        trans_segs = parse_srt(trans_text)

        trans_map = {t.index: t for t in trans_segs}
        res_map = {}
        if "result_segments" in job and job["result_segments"]:
            res_map = {r["index"]: r for r in job["result_segments"]}

        from modules.translate.condenser import calculate_segment_word_budget, count_words

        aligned = []
        for s in src_segs:
            t = trans_map.get(s.index)
            if not t:
                raise ValueError(f"Không tìm thấy phân đoạn dịch cho chỉ mục {s.index}.")
            if s.start_ms != t.start_ms or s.end_ms != t.end_ms:
                raise ValueError(f"Timestamps không khớp ở chỉ mục {s.index}.")
            
            res_item = res_map.get(s.index, {})
            duration_s = max(0.1, (s.end_ms - s.start_ms) / 1000.0)
            budget = calculate_segment_word_budget(s.start_ms, s.end_ms, target_wps=4.2)
            src_words = count_words(s.text)
            is_overtime = (src_words > budget) or (src_words / duration_s > 3.5)

            aligned.append({
                "index": s.index,
                "start_ms": s.start_ms,
                "end_ms": s.end_ms,
                "source_text": s.text,
                "translated_text": t.text,
                "asr_corrected": res_item.get("asr_corrected", False),
                "corrected_source": res_item.get("corrected_source"),
                "correction_note": res_item.get("correction_note"),
                "original_translation": res_item.get("original_translation"),
                "is_overtime": is_overtime,
                "max_words": budget
            })

        return {
            "source_path": source_path,
            "saved_path": saved_path,
            "target_language": batch["target_language"],
            "elapsed_time": job["elapsed_time"],
            "segments": aligned,
            "context_metadata": job.get("context_metadata") or {
                "source_language_code": "und",
                "source_language_name": "Không xác định",
                "summary": "Không xác định",
                "tone": "Không xác định",
                "addressing_style": "Không xác định",
                "content_type": "Không xác định"
            }
        }

    def save_job_edits(self, batch_id: str, job_id: str, edits: Dict[int, str]) -> bool:
        """
        Atomically saves edited translations for a completed job.
        edits: Dict[int, str] mapped index to new translated text.
        """
        with self.lock:
            batch = self.batches.get(batch_id)
            if not batch:
                raise ValueError("Không tìm thấy batch.")
            job = next((j for j in batch["jobs"] if j["job_id"] == job_id), None)
            if not job:
                raise ValueError("Không tìm thấy job.")
            
            if job["status"] != "done" or not job["saved_path"]:
                raise ValueError("Chỉ có thể chỉnh sửa job đã hoàn thành.")

            source_path = job["source_path"]
            saved_path = job["saved_path"]

        from modules.subtitle.srt import parse_srt, export_srt
        from modules.translate.formatting import validate_formatting_markers

        with open(source_path, "r", encoding="utf-8") as f:
            src_text = f.read()
        src_segs = parse_srt(src_text)

        src_indexes = {s.index for s in src_segs}
        
        try:
            edit_map = {int(k): v for k, v in edits.items()}
        except (ValueError, TypeError):
            raise ValueError("Chỉ mục chỉnh sửa phải là số nguyên hợp lệ.")

        edit_indexes = set(edit_map.keys())
        if edit_indexes != src_indexes:
            raise ValueError("Danh sách chỉ mục (index) chỉnh sửa không khớp chính xác với phụ đề gốc.")

        for s in src_segs:
            new_text = edit_map[s.index]
            if not new_text or not new_text.strip():
                raise ValueError(f"Văn bản chỉnh sửa cho chỉ mục {s.index} không được để trống.")
            if not validate_formatting_markers(s.text, new_text):
                raise ValueError(f"Thẻ HTML/ASS của chỉ mục {s.index} không khớp với phụ đề gốc.")

            s.text = new_text

        edited_srt = export_srt(src_segs)

        parent_dir = os.path.dirname(saved_path)
        fd, tmp_path = tempfile.mkstemp(dir=parent_dir, prefix="tmp_edit_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(edited_srt)
            os.replace(tmp_path, saved_path)
        except Exception as e:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            raise e

        return True

    def get_job_output_path(self, batch_id: str, job_id: str) -> str:
        """Returns output path for completed/done jobs."""
        with self.lock:
            batch = self.batches.get(batch_id)
            if not batch:
                raise ValueError("Không tìm thấy batch.")
            job = next((j for j in batch["jobs"] if j["job_id"] == job_id), None)
            if not job:
                raise ValueError("Không tìm thấy job.")
            
            if job["status"] != "done" or not job["saved_path"]:
                raise ValueError("Job chưa hoàn thành hoặc chưa có tệp dịch đầu ra.")
            
            return job["saved_path"]
