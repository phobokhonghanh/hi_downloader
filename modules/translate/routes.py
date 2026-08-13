import os
import threading
from typing import List, Dict, Optional, Any, Callable
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from modules.translate.batch_service import TranslateBatchService
from modules.translate.credentials import GeminiCredentialStore, SecretServiceUnavailableError
from modules.translate.providers.models import TRANSLATION_PROVIDERS


# Pydantic models for translation API
class CredentialsPutRequest(BaseModel):
    api_key: str = Field(..., description="API Key to set")
    persist: bool = Field(False, description="Persist key in OS Secret Service")
    provider: Optional[str] = Field(None, description="Target provider name")


class TestCredentialsRequest(BaseModel):
    pass


class ScanFolderRequest(BaseModel):
    path: str = Field(..., description="Absolute directory path to scan")


class CreateBatchRequest(BaseModel):
    files: List[str] = Field(..., description="SRT source files list")
    target_language: str = Field(..., description="Target translation language")
    profile: str = Field("balanced", description="Quality profile mapping")
    concurrency: int = Field(2, description="Parallel processing limit")


class BatchActionRequest(BaseModel):
    action: str = Field(..., description="Action: cancel | retry")
    job_ids: Optional[List[str]] = Field(None, description="Optional target jobs limit list")


class SaveEditsRequest(BaseModel):
    edits: Dict[int, str] = Field(..., description="Exact mapped segments index to text edits")


def create_translate_router(
    batch_service: TranslateBatchService,
    credential_store: GeminiCredentialStore,
    provider_factory: Callable[[str], Any],
    open_location_cb: Callable[[str], None]
) -> APIRouter:
    router = APIRouter(prefix="/api/translate", tags=["translate"])

    @router.get("/profiles")
    def get_profiles():
        """Returns quality profile catalog options."""
        from modules.translate.providers.models import TRANSLATION_PROFILES
        return [
            {
                "profile": p["id"],
                "label": p["name"],
                "model": p["model"],
                "provider": p.get("provider", "gemini")
            }
            for p in TRANSLATION_PROFILES
        ]

    @router.get("/providers")
    def get_providers():
        """Returns safe provider catalog options containing only public metadata needed by UI."""
        from modules.translate.providers.models import TRANSLATION_PROVIDERS
        return [
            {
                "id": p["id"],
                "name": p["name"],
                "env_var": p.get("env_var", "")
            }
            for p in TRANSLATION_PROVIDERS
        ]

    @router.get("/credentials")
    @router.get("/credentials/{provider}")
    def get_credentials_status(provider: str = "gemini"):
        """Get API credentials status only without exposing key."""
        supported = [p["id"] for p in TRANSLATION_PROVIDERS]
        if provider not in supported:
            raise HTTPException(status_code=400, detail=f"Provider '{provider}' không được hỗ trợ.")
        return credential_store.status(provider)

    @router.get("/credentials/{provider}/reveal")
    def reveal_credentials(provider: str):
        """Reveal user-stored raw credentials for a specific provider. Never expose env keys."""
        supported = [p["id"] for p in TRANSLATION_PROVIDERS]
        if provider not in supported:
            raise HTTPException(status_code=400, detail=f"Provider '{provider}' không được hỗ trợ.")
        
        raw_key = credential_store.reveal(provider)
        if not raw_key:
            raise HTTPException(status_code=404, detail="Không tìm thấy khoá API được lưu bởi người dùng.")
        return {"provider": provider, "api_key": raw_key}

    @router.put("/credentials")
    @router.put("/credentials/{provider}")
    def set_credentials(req: CredentialsPutRequest, provider: Optional[str] = None):
        """Set credentials with optional persistence."""
        target_provider = provider or req.provider or "gemini"
        supported = [p["id"] for p in TRANSLATION_PROVIDERS]
        if target_provider not in supported:
            raise HTTPException(status_code=400, detail=f"Provider '{target_provider}' không được hỗ trợ.")

        if not req.api_key or not req.api_key.strip():
            raise HTTPException(status_code=400, detail="Khoá API không được để trống.")
        
        try:
            credential_store.set(req.api_key, persist=req.persist, provider=target_provider)
            return {"status": "success", "message": f"Đã lưu khoá API thành công cho {target_provider}."}
        except SecretServiceUnavailableError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.delete("/credentials")
    @router.delete("/credentials/{provider}")
    def clear_credentials(provider: str = "gemini"):
        """Clear all active and persisted keys for a specific provider."""
        supported = [p["id"] for p in TRANSLATION_PROVIDERS]
        if provider not in supported:
            raise HTTPException(status_code=400, detail=f"Provider '{provider}' không được hỗ trợ.")

        try:
            credential_store.clear(provider)
            return {"status": "success", "message": f"Đã xoá khoá API cho {provider}."}
        except SecretServiceUnavailableError as e:
            raise HTTPException(status_code=503, detail=str(e))

    @router.post("/credentials/test")
    @router.post("/credentials/test/{provider}")
    def test_credentials(provider: str = "gemini"):
        """Verify key by resolving and executing a minimal mocked context request."""
        supported = [p["id"] for p in TRANSLATION_PROVIDERS]
        if provider not in supported:
            raise HTTPException(status_code=400, detail=f"Provider '{provider}' không được hỗ trợ.")

        api_key = credential_store.resolve(provider)
        if not api_key:
            raise HTTPException(status_code=400, detail="Không tìm thấy khoá API được cấu hình.")

        from modules.subtitle.schemas import SubtitleSegment
        from modules.translate.schemas import TranslationConfig

        segments = [SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="Test API connection")]
        config = TranslationConfig(target_language="vi", model="economy")

        try:
            if provider == "gemini":
                prov_inst = provider_factory(api_key)
                prov_inst.analyze_context(segments, config, threading.Event())
            return {"status": "success", "message": "Khóa API hợp lệ, kết nối thử thành công."}
        except Exception as e:
            err_msg = str(e)
            if api_key in err_msg:
                err_msg = err_msg.replace(api_key, "[REDACTED]")
            raise HTTPException(status_code=400, detail=f"Kết nối thử thất bại: {err_msg}")

    @router.post("/scan-folder")
    def scan_folder(req: ScanFolderRequest):
        """Scan target folder and return direct child srt files (excluding symlinks)."""
        path = req.path.strip()
        if not path:
            raise HTTPException(status_code=400, detail="Đường dẫn không được để trống.")
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="Thư mục không tồn tại.")
        if not os.path.isdir(path):
            raise HTTPException(status_code=400, detail="Đường dẫn không phải là thư mục.")

        try:
            files = []
            for entry in os.scandir(path):
                if entry.is_file(follow_symlinks=False) and entry.name.lower().endswith(".srt"):
                    files.append(os.path.abspath(entry.path))
            files.sort()
            return {"files": files}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Lỗi quét thư mục: {str(e)}")

    @router.post("/batches")
    def create_and_start_batch(req: CreateBatchRequest):
        """Create and immediately dispatch a translation batch queue."""
        try:
            batch_id = batch_service.create_batch(
                files=req.files,
                target_language=req.target_language,
                profile=req.profile,
                concurrency=req.concurrency
            )
            batch_service.start_batch(batch_id)
            return {"batch_id": batch_id, "status": "running"}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/batches/{batch_id}")
    def get_batch(batch_id: str):
        """Retrieve defensive snapshot properties for a translation batch."""
        snapshot = batch_service.get_batch(batch_id)
        if not snapshot:
            raise HTTPException(status_code=404, detail="Không tìm thấy lô dịch phụ đề.")
        return snapshot

    @router.post("/batches/{batch_id}/action")
    def trigger_batch_action(batch_id: str, req: BatchActionRequest):
        """Perform cancel or retry actions on specific jobs or whole batch queues."""
        snapshot = batch_service.get_batch(batch_id)
        if not snapshot:
            raise HTTPException(status_code=404, detail="Không tìm thấy lô dịch phụ đề.")

        action = req.action.strip().lower()
        if action not in ("cancel", "retry", "save"):
            raise HTTPException(status_code=400, detail="Hành động không hợp lệ. Chỉ chấp nhận cancel, retry hoặc save.")

        job_ids = req.job_ids
        jobs_in_batch = {j["job_id"]: j for j in snapshot["jobs"]}
        outcomes = {}

        explicit_ids = job_ids is not None and len(job_ids) > 0
        target_ids = job_ids if explicit_ids else list(jobs_in_batch.keys())

        applied_count = 0
        has_missing = False

        for j_id in target_ids:
            if j_id not in jobs_in_batch:
                outcomes[j_id] = {"outcome": "missing"}
                has_missing = True
                continue

            job = jobs_in_batch[j_id]
            status = job["status"]

            if action == "cancel":
                if status in ("waiting", "running"):
                    batch_service.cancel_job(batch_id, j_id)
                    outcomes[j_id] = {"outcome": "applied"}
                    applied_count += 1
                else:
                    outcomes[j_id] = {"outcome": "skipped"}
            elif action == "retry":
                if status in ("error", "canceled"):
                    batch_service.retry_job(batch_id, j_id)
                    outcomes[j_id] = {"outcome": "applied"}
                    applied_count += 1
                else:
                    outcomes[j_id] = {"outcome": "skipped"}
            elif action == "save":
                if status == "done" and job.get("saved_path"):
                    outcomes[j_id] = {"outcome": "applied"}
                    applied_count += 1
                else:
                    outcomes[j_id] = {"outcome": "skipped"}

        if (explicit_ids and has_missing) or applied_count == 0:
            return JSONResponse(
                status_code=409,
                content={
                    "status": "error",
                    "message": "Không có tác vụ nào được xử lý hoặc có tác vụ không tồn tại.",
                    "results": outcomes
                }
            )

        return {
            "status": "success",
            "message": "Đã thực hiện hành động thành công.",
            "results": outcomes
        }

    @router.get("/batches/{batch_id}/jobs/{job_id}/compare")
    def get_compare(batch_id: str, job_id: str):
        """Retrieve side-by-side original and translated parallel rows aligned by index."""
        try:
            return batch_service.get_job_compare(batch_id, job_id)
        except ValueError as e:
            err_msg = str(e)
            if "Không tìm thấy" in err_msg:
                raise HTTPException(status_code=404, detail=err_msg)
            raise HTTPException(status_code=400, detail=err_msg)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.put("/batches/{batch_id}/jobs/{job_id}/edits")
    def save_edits(batch_id: str, job_id: str, req: SaveEditsRequest):
        """Persist user edited translations atomically back to output SRT."""
        try:
            batch_service.save_job_edits(batch_id, job_id, req.edits)
            return {"status": "success", "message": "Lưu các chỉnh sửa thành công."}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/batches/{batch_id}/jobs/{job_id}/open-location")
    def open_job_location(batch_id: str, job_id: str):
        """Mở thư mục chứa tệp dịch đầu ra của job."""
        try:
            out_path = batch_service.get_job_output_path(batch_id, job_id)
            open_location_cb(out_path)
            return {"status": "success", "message": "Đã mở vị trí tệp."}
        except ValueError as e:
            err_msg = str(e)
            if "Không tìm thấy" in err_msg:
                raise HTTPException(status_code=404, detail=err_msg)
            raise HTTPException(status_code=400, detail=err_msg)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return router
