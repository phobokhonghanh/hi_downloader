import os
import time
import tempfile
from typing import Dict, Any, List

from core.base_module import BaseModule, ModuleContext, ModuleResult, ModuleMetadata
from modules.translate.batch_service import clean_target_language_slug
from modules.translate.providers.models import resolve_profile_to_model


class TranslateModule(BaseModule):
    def __init__(self, provider_factory, credential_store, cache):
        """Initializes the TranslateModule with translation backend dependencies."""
        self.provider_factory = provider_factory
        self.credential_store = credential_store
        self.cache = cache

    @property
    def module_id(self) -> str:
        return "translate"

    @property
    def metadata(self) -> ModuleMetadata:
        return ModuleMetadata(
            module_id=self.module_id,
            name="Translate Module",
            description="Dịch thuật phụ đề tự động sử dụng mô hình Google Gemini.",
            input_schema={
                "type": "object",
                "properties": {
                    "target_language": {
                        "type": "string",
                        "description": "Mã ngôn ngữ đích cần dịch (ví dụ: vi, en)."
                    },
                    "profile": {
                        "type": "string",
                        "description": "Cấu hình mô hình dịch (economy, balanced, quality)."
                    },
                    "prompt_version": {
                        "type": "string",
                        "description": "Phiên bản prompt tùy chọn để tùy chỉnh dịch thuật."
                    }
                },
                "required": ["target_language", "profile"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "output_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Danh sách các tệp phụ đề SRT đã dịch hoàn tất."
                    }
                }
            },
            supports_standalone=True,
            supports_workflow=True
        )

    def validate_params(self, params: Dict[str, Any]) -> bool:
        if not params or not isinstance(params, dict):
            return False
        
        target_lang = params.get("target_language")
        if not target_lang or not isinstance(target_lang, str) or not target_lang.strip():
            return False

        profile = params.get("profile")
        if not profile or not isinstance(profile, str) or not profile.strip():
            return False

        try:
            resolve_profile_to_model(profile)
        except ValueError:
            return False

        if "prompt_version" in params and params["prompt_version"] is not None:
            pv = params["prompt_version"]
            if not isinstance(pv, str) or not pv.strip():
                return False

        return True

    def run(self, context: ModuleContext) -> ModuleResult:
        if context.cancel_event.is_set():
            return ModuleResult(success=False, canceled=True, error="Bị hủy trước khi chạy.")

        params = context.params
        if not self.validate_params(params):
            return ModuleResult(success=False, error="Tham số cấu hình không hợp lệ.")

        target_lang = params["target_language"].strip()
        profile = params["profile"].strip()

        # Validate input files
        if not context.input_files:
            return ModuleResult(success=False, error="Không có tệp phụ đề nguồn đầu vào.")

        # Resolve credentials safely without leaks
        api_key = self.credential_store.resolve()
        if not api_key:
            return ModuleResult(success=False, error="API Key cho Google Gemini chưa được cấu hình.")

        output_files = []
        metrics = {
            "files_processed": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "translated_chunks": 0,
            "restored_chunks": 0,
            "elapsed_time": 0.0
        }

        start_time = time.time()
        num_files = len(context.input_files)

        try:
            from modules.translate.service import TranslationService
            from modules.translate.schemas import TranslationConfig
            from modules.subtitle.srt import parse_srt, export_srt

            for idx, source_path in enumerate(context.input_files):
                if not source_path or not isinstance(source_path, str):
                    raise ValueError("Đường dẫn tệp không hợp lệ.")
                if not os.path.exists(source_path):
                    raise ValueError(f"Tệp không tồn tại: {source_path}")
                if not os.path.isfile(source_path) or os.path.islink(source_path):
                    raise ValueError(f"Không hỗ trợ liên kết động hoặc thư mục: {source_path}")
                if not source_path.lower().endswith(".srt"):
                    raise ValueError(f"Chỉ hỗ trợ tệp định dạng .srt: {source_path}")

                if context.cancel_event.is_set():
                    return ModuleResult(
                        success=False,
                        canceled=True,
                        output_files=output_files,
                        metrics=metrics,
                        error="Tiến trình đã bị hủy."
                    )

                # Update progress for preparing phase of current file
                if context.progress_callback:
                    base_progress = (idx * 100.0) / num_files
                    context.progress_callback(base_progress + (5.0 / num_files), f"Chuẩn bị tệp {idx + 1}/{num_files}")

                provider = self.provider_factory(api_key)
                service = TranslationService(provider)

                prompt_version = params.get("prompt_version")
                kwargs = {}
                if prompt_version:
                    kwargs["prompt_version"] = prompt_version

                # Read SRT content
                with open(source_path, "r", encoding="utf-8") as f:
                    srt_text = f.read()

                segments = parse_srt(srt_text)
                enable_time_constraint = params.get("enable_time_constraint", True)
                target_wps = float(params.get("target_wps", 3.8))
                config = TranslationConfig(
                    target_language=target_lang,
                    model=profile,
                    enable_time_constraint=enable_time_constraint,
                    target_wps=target_wps
                )


                # Local progress tracker
                def file_progress_cb(pct, status_msg):
                    if context.progress_callback:
                        file_share = pct / num_files
                        current_total_pct = base_progress + file_share
                        context.progress_callback(
                            min(current_total_pct, 100.0),
                            f"Tệp {idx + 1}/{num_files}: {status_msg}"
                        )

                # Execute translation
                res = service.translate(
                    segments=segments,
                    config=config,
                    cancel_event=context.cancel_event,
                    progress_callback=file_progress_cb,
                    cache=self.cache,
                    **kwargs
                )

                if not res.success:
                    raise RuntimeError(f"Lỗi dịch tệp {source_path}: {res.error}")

                translated_srt = export_srt(res.translated_segments)

                # Determine out name
                parent_dir = os.path.dirname(source_path)
                stem, _ = os.path.splitext(os.path.basename(source_path))
                slug = clean_target_language_slug(target_lang)
                out_path = os.path.join(parent_dir, f"{stem}_{slug}.srt")

                # Never overwrite original source file
                if os.path.abspath(out_path) == os.path.abspath(source_path):
                    out_path = os.path.join(parent_dir, f"{stem}_{slug}_translated.srt")

                # Atomic temp file write
                fd, tmp_path = tempfile.mkstemp(dir=parent_dir, prefix="tmp_mod_trans_")
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f_out:
                        f_out.write(translated_srt)
                    os.replace(tmp_path, out_path)
                except Exception as e:
                    if os.path.exists(tmp_path):
                        try:
                            os.remove(tmp_path)
                        except Exception:
                            pass
                    raise e

                # Collect metrics and file
                output_files.append(os.path.abspath(out_path))
                metrics["files_processed"] += 1
                metrics["translated_chunks"] += res.metrics.get("translated_chunks", 0)
                metrics["restored_chunks"] += res.metrics.get("restored_chunks", 0)
                
                # Fetch tokens usage safely
                inp_tok = provider.last_token_usage.get("input_tokens", 0) or 0
                out_tok = provider.last_token_usage.get("output_tokens", 0) or 0
                tot_tok = provider.last_token_usage.get("total_tokens", 0) or 0
                metrics["input_tokens"] += inp_tok
                metrics["output_tokens"] += out_tok
                metrics["total_tokens"] += tot_tok

        except Exception as e:
            metrics["elapsed_time"] = round(time.time() - start_time, 2)
            if context.cancel_event.is_set():
                return ModuleResult(
                    success=False,
                    canceled=True,
                    output_files=output_files,
                    metrics=metrics,
                    error=f"Đã hủy: {str(e)}"
                )
            return ModuleResult(
                success=False,
                output_files=output_files,
                metrics=metrics,
                error=str(e)
            )

        metrics["elapsed_time"] = round(time.time() - start_time, 2)
        return ModuleResult(
            success=True,
            output_files=output_files,
            metrics=metrics
        )
