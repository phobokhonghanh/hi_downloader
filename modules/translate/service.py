import threading
from typing import List, Callable, Optional, Any
from modules.subtitle.schemas import SubtitleSegment
from modules.translate.schemas import (
    TranslationConfig,
    TranslationContext,
    TranslationResult,
    TranslationAnalysis,
)
from modules.translate.validator import validate_segments
from modules.translate.chunker import chunk_segments
from modules.translate.analysis import analyze_translation_context
from modules.translate.formatting import validate_formatting_markers
from modules.translate.providers.base import BaseTranslateProvider
from modules.translate.providers.models import resolve_profile_to_model
from modules.translate.cache import generate_chunk_cache_key


class TranslationService:

    def __init__(self, provider: BaseTranslateProvider):
        self.provider = provider

    def _validate_translated_chunk(self, orig_segments: List[SubtitleSegment], trans_segments: List[SubtitleSegment]) -> None:
        """
        Validates that the translated segments strictly match source segments index,
        timestamps, non-emptiness, and HTML/ASS style tags.
        """
        if len(trans_segments) != len(orig_segments):
            raise ValueError(
                f"Sai lệch kết quả dịch: nhận {len(trans_segments)} dòng, "
                f"mong đợi {len(orig_segments)} dòng."
            )

        for orig, trans in zip(orig_segments, trans_segments):
            if trans.index != orig.index:
                raise ValueError(
                    f"Lỗi khớp dòng dịch: Sai số chỉ mục. Mong đợi {orig.index}, nhận {trans.index}."
                )
            if trans.start_ms != orig.start_ms or trans.end_ms != orig.end_ms:
                raise ValueError(
                    f"Lỗi bảo toàn thời gian tại Segment #{orig.index}: Timestamps bị thay đổi."
                )
            if not trans.text or not trans.text.strip():
                raise ValueError(
                    f"Lỗi dịch: Dòng dịch tại Segment #{orig.index} trống."
                )
            if not validate_formatting_markers(orig.text, trans.text):
                raise ValueError(
                    f"Lỗi bảo toàn thẻ định dạng tại Segment #{orig.index}: "
                    f"Thẻ HTML/ASS không khớp giữa gốc và dịch."
                )

    def translate(
        self,
        segments: List[SubtitleSegment],
        config: TranslationConfig,
        cancel_event: Optional[threading.Event] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        cache: Optional[Any] = None,
        precomputed_global_summary: Optional[Any] = None,
        prompt_version: str = "v1",
        resolved_model_id: Optional[str] = None
    ) -> TranslationResult:
        """
        Orchestrates the entire translation pipeline:
          1. Validates input segments.
          2. Conducts deterministic sampling global context analysis (or reuses precomputed).
          3. Splits segments into chunks using scene boundaries.
          4. Sequentially translates chunks (checking cache, calling provider, and updating cache).
          5. Assures exact index/time preservation and format marker protection.
        """
        if cancel_event is None:
            cancel_event = threading.Event()

        if progress_callback:
            progress_callback(0.0, "Đang kiểm tra định dạng phụ đề gốc...")

        # 1. Validate target language is non-empty
        if not config.target_language or not config.target_language.strip():
            return TranslationResult(
                success=False,
                error="Ngôn ngữ đích (target_language) không được để trống."
            )

        # 2. Validate input segments structure
        val_errors = validate_segments(segments)
        if val_errors:
            return TranslationResult(
                success=False,
                error=f"Dữ liệu phụ đề gốc không hợp lệ: {'; '.join(val_errors)}"
            )

        restored_chunks = 0
        translated_chunks = 0
        context_metadata = {
            "source_language_code": "und",
            "source_language_name": "Không xác định",
            "summary": "Không xác định",
            "tone": "Không xác định",
            "addressing_style": "Không xác định",
            "content_type": "Không xác định"
        }

        try:
            if cancel_event.is_set():
                metrics = {"restored_chunks": restored_chunks, "translated_chunks": translated_chunks, "canceled": True, "context_metadata": context_metadata}
                return TranslationResult(success=False, error="Tiến trình đã bị hủy.", metrics=metrics)

            # Resolve model ID strictly without fallback to ensure deterministic cache lookup
            if resolved_model_id:
                if not resolved_model_id.strip():
                    raise ValueError("Model ID không được để trống.")
                model_id = resolved_model_id.strip()
            else:
                model_id = resolve_profile_to_model(config.model)

            # 2. Extract global context summary
            analysis = None
            if precomputed_global_summary:
                if isinstance(precomputed_global_summary, TranslationAnalysis):
                    analysis = precomputed_global_summary
                elif isinstance(precomputed_global_summary, dict):
                    try:
                        analysis = TranslationAnalysis(**precomputed_global_summary)
                    except Exception:
                        pass
                elif isinstance(precomputed_global_summary, str):
                    pre_str = precomputed_global_summary.strip()
                    if pre_str:
                        # Try parsing as JSON first
                        try:
                            import json
                            parsed = json.loads(pre_str)
                            if isinstance(parsed, dict):
                                analysis = TranslationAnalysis(**parsed)
                        except Exception:
                            pass
                        
                        if not analysis:
                            # String fallback
                            analysis = TranslationAnalysis(
                                summary=pre_str,
                                source_language_code="und",
                                source_language_name="Không xác định",
                                tone="Không xác định",
                                addressing_style="Không xác định",
                                content_type="Không xác định"
                            )
            
            if not analysis:
                if progress_callback:
                    progress_callback(5.0, "Đang trích xuất ngữ cảnh chung...")
                res_analysis = analyze_translation_context(segments, config, self.provider, cancel_event)
                if isinstance(res_analysis, str):
                    analysis = TranslationAnalysis(
                        summary=res_analysis,
                        source_language_code="und",
                        source_language_name="Không xác định",
                        tone="Không xác định",
                        addressing_style="Không xác định",
                        content_type="Không xác định"
                    )
                else:
                    analysis = res_analysis

            # Build stable global context string and dict metadata
            stable_global_context_string = (
                f"Chủ đề chính: {analysis.summary}\n"
                f"Tông giọng: {analysis.tone}\n"
                f"Cách xưng hô: {analysis.addressing_style}\n"
                f"Thể loại: {analysis.content_type}"
            )
            
            context_metadata = {
                "source_language_code": analysis.source_language_code,
                "source_language_name": analysis.source_language_name,
                "summary": analysis.summary,
                "tone": analysis.tone,
                "addressing_style": analysis.addressing_style,
                "content_type": analysis.content_type
            }
            
            global_summary = stable_global_context_string

            if cancel_event.is_set():
                metrics = {"restored_chunks": restored_chunks, "translated_chunks": translated_chunks, "canceled": True, "context_metadata": context_metadata}
                return TranslationResult(success=False, error="Tiến trình đã bị hủy.", metrics=metrics)

            # 3. Create boundaries chunks
            if progress_callback:
                progress_callback(10.0, "Đang phân bổ các phân đoạn phụ đề...")

            chunks = chunk_segments(segments, config.chunk_config)
            total_chunks = len(chunks)
            if total_chunks == 0:
                metrics = {"restored_chunks": restored_chunks, "translated_chunks": translated_chunks, "canceled": False, "context_metadata": context_metadata}
                return TranslationResult(success=True, translated_segments=[], metrics=metrics)

            # 4. Sequentially translate chunks
            translated_all = []
            rolling_history = []

            for idx, chunk in enumerate(chunks):
                if cancel_event.is_set():
                    metrics = {"restored_chunks": restored_chunks, "translated_chunks": translated_chunks, "canceled": True, "context_metadata": context_metadata}
                    return TranslationResult(success=False, error="Tiến trình đã bị hủy.", metrics=metrics)

                chunk_num = idx + 1

                # 4a. Check Cache before querying LLM Provider
                key = generate_chunk_cache_key(
                    segments=chunk.segments,
                    target_language=config.target_language,
                    resolved_model=model_id,
                    chunk_ordinal=chunk_num,
                    global_context=analysis.summary,
                    style_guide=config.style_guide,
                    glossary=config.glossary,
                    prompt_version=prompt_version
                )

                chunk_translated = None
                used_cache = False

                if cache is not None:
                    cached_data = cache.get(key)
                    if cached_data is not None:
                        # Strictly validate cache hit properties using shared helper
                        try:
                            self._validate_translated_chunk(chunk.segments, cached_data)
                            chunk_translated = cached_data
                            used_cache = True
                        except Exception:
                            # Invalidate mismatched/corrupted cache hit
                            cache.invalidate(key)
                            chunk_translated = None

                # 4b. Cache miss: invoke LLM provider to translate chunk
                if chunk_translated is None:
                    if cancel_event.is_set():
                        metrics = {"restored_chunks": restored_chunks, "translated_chunks": translated_chunks, "canceled": True, "context_metadata": context_metadata}
                        return TranslationResult(success=False, error="Tiến trình đã bị hủy.", metrics=metrics)

                    # Construct rolling context of last 3 translated segments
                    context = TranslationContext(
                        global_summary=global_summary,
                        style_guide=config.style_guide,
                        glossary=config.glossary,
                        rolling_history=list(rolling_history[-3:])
                    )

                    chunk_translated = self.provider.translate_chunk(chunk.segments, config, context, cancel_event)

                    # Verify provider output compatibility using shared helper
                    self._validate_translated_chunk(chunk.segments, chunk_translated)

                    # Cache successful verified output chunk
                    if cache is not None:
                        cache.put(key, chunk_translated)

                # Update count metrics & generate progress message
                if used_cache:
                    restored_chunks += 1
                    status_msg = "Khôi phục từ cache"
                else:
                    translated_chunks += 1
                    status_msg = "Dịch trực tiếp"

                if progress_callback:
                    pct = round(10.0 + (chunk_num / total_chunks) * 90.0, 1)
                    progress_callback(pct, f"Đang dịch phân đoạn {chunk_num}/{total_chunks} ({status_msg})...")

                # Accumulate
                translated_all.extend(chunk_translated)

                # Append to rolling history
                for orig, trans in zip(chunk.segments, chunk_translated):
                    rolling_history.append({
                        "original": orig.text,
                        "translated": trans.text
                    })

            if progress_callback:
                progress_callback(100.0, "Hoàn tất dịch phụ đề!")

            metrics = {
                "restored_chunks": restored_chunks,
                "translated_chunks": translated_chunks,
                "canceled": False,
                "context_metadata": context_metadata
            }
            return TranslationResult(success=True, translated_segments=translated_all, metrics=metrics)

        except Exception as e:
            metrics = {
                "restored_chunks": restored_chunks,
                "translated_chunks": translated_chunks,
                "canceled": cancel_event.is_set(),
                "context_metadata": context_metadata
            }
            return TranslationResult(success=False, error=str(e), metrics=metrics)
