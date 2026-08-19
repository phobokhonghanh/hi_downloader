import json
import time
import threading
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from modules.subtitle.schemas import SubtitleSegment
from modules.translate.providers.base import BaseTranslateProvider
from modules.translate.providers.models import resolve_profile_to_model
from modules.translate.schemas import TranslationConfig, TranslationContext, TranslationAnalysis


# Pydantic schema for structured output definition
class TranslatedLine(BaseModel):
    index: int = Field(description="Chỉ số index của dòng phụ đề gốc")
    translated_text: str = Field(description="Nội dung văn bản đã được dịch sang ngôn ngữ đích")
    asr_corrected: Optional[bool] = Field(default=False, description="Đánh dấu True nếu phát hiện và sửa lỗi nghe nhầm/chính tả ASR")
    corrected_source: Optional[str] = Field(default=None, description="Từ/câu gốc sau khi đã được khôi phục đúng")
    correction_note: Optional[str] = Field(default=None, description="Ghi chú giải thích ngắn lý do sửa lỗi ASR (ví dụ: 吃饭 -> 痴缠)")
    original_translation: Optional[str] = Field(default=None, description="Bản dịch thô theo câu gốc ban đầu nếu bị nghe nhầm")


# 1. Định nghĩa template tĩnh cố định (tối ưu hiệu quả cache token của LLM)
SYSTEM_PROMPT_TEMPLATE = """# VAI TRÒ
Bạn là chuyên gia biên dịch và biên tập phụ đề đa ngôn ngữ cao cấp.
Tự động nhận diện ngôn ngữ nguồn và dịch chuẩn xác sang ngôn ngữ: '{target_language}'.

---

# CẤU TRÚC ĐẦU RA (JSON CONTRACT)
BẮT BUỘC trả về duy nhất một mảng JSON thuần túy (Raw JSON array). Không bao bọc trong lời dẫn hay markdown giải thích bên ngoài.
Mỗi phần tử phải gồm đúng 5 trường sau:
- "index": (number) Giữ nguyên index từ danh sách đầu vào.
- "translated_text": (string) Bản dịch hoàn chỉnh ở ngôn ngữ đích.
- "asr_corrected": (boolean) `true` nếu có sửa lỗi nhận dạng giọng nói (ASR), ngược lại `false`.
- "corrected_source": (string | null) Câu gốc sau khi sửa lỗi ASR (hoặc null nếu asr_corrected = false).
- "original_translation": (string | null) Bản dịch theo câu sai ban đầu (hoặc null nếu asr_corrected = false).

---

# NGUYÊN TẮC BIÊN DỊCH BẮT BUỘC

1. VĂN PHONG & ĐÚNG THỂ LOẠI: Dịch tự nhiên, nhịp nhàng theo đúng ngữ điệu thoại phim/show thực tế. Thể hiện chính xác sắc thái, cá tính nhân vật và tông giọng tổng thể.
2. TÊN RIÊNG & THUẬT NGỮ: Giữ nguyên hoặc chuẩn hóa tên riêng, danh hiệu, chiêu thức/kỹ năng, thuật ngữ chuyên ngành theo đúng quy ước thể loại. Không tự ý diễn giải dài dòng.
3. MẠCH VĂN & NGỮ CẢNH: Phân tích mạch logic từ các câu đã dịch trước đó để chọn đại từ nhân xưng và sắc thái phù hợp. Duy trì cách xưng hô nhất quán xuyên suốt.
4. ÁNH XẠ 1-1 & BẢO TOÀN ĐỊNH DẠNG: Bảo toàn 1-1 theo `index`. Giữ nguyên mọi thẻ HTML (<b>, <i>...) hoặc ASS style tags ({{...}}).
5. RÚT GỌN KHI TRÀN TIMELINE: Mặc định dịch bám sát 100% ngữ nghĩa tự nhiên. Chỉ khi câu có `is_overtime: true` và có `max_words`, tinh gọn vế câu sao cho số từ <= `max_words` để đọc kịp timeline, nhưng vẫn phải giữ đúng đại từ xưng hô và ý nghĩa cốt lõi.
6. BẢO TỒN GỐC & SỬA LỖI ASR: Mặc định coi câu gốc là ĐÚNG (asr_corrected: false). Chỉ sửa khi câu gốc phi lý rõ rệt do lỗi nhận diện đồng âm/gần âm (homophone) gây xung đột ngữ cảnh (ví dụ: 掉 -> 钓, 吃饭 -> 痴缠/来犯), khi đó bật asr_corrected: true và điền đầy đủ corrected_source, original_translation.
7. XỬ LÝ CÂU NGẮT LỬNG ĐA DÒNG (CROSS-LINE CONTINUITY): Khi một câu bị tách đôi giữa Dòng N (vế đầu/giới từ) và Dòng N+1 (vị ngữ/bổ ngữ chính), phải kết hợp hai dòng để hiểu trọn ý trước khi dịch. Phân bổ câu dịch mượt mà giữa các dòng, tránh tình trạng Dòng N bị cụt vô nghĩa và Dòng N+1 bị trơ trọi. BẮT BUỘC giữ nguyên 2 phần tử JSON riêng biệt cho Dòng N và Dòng N+1, tuyệt đối không gộp thành 1 phần tử."""


# 2. Hàm xây dựng system prompt linh hoạt
def build_system_instruction(config, context) -> str:
    target_lang = getattr(config, "target_language", "vi")
    sys_inst_parts = [SYSTEM_PROMPT_TEMPLATE.format(target_language=target_lang)]

    # Dynamic Context Blocks
    if getattr(context, "global_summary", None):
        sys_inst_parts.append(f"# BỐI CẢNH TỔNG QUÁT CỦA VIDEO\n{context.global_summary}")

    if getattr(context, "style_guide", None):
        sys_inst_parts.append(f"# YÊU CẦU VĂN PHONG\n{context.style_guide}")

    if getattr(context, "glossary", None):
        # Format JSON dạng thụt lề nhẹ hoặc dump sạch
        glossary_str = json.dumps(context.glossary, ensure_ascii=False, indent=2)
        sys_inst_parts.append(f"# DANH MỤC THUẬT NGỮ BẮT BUỘC\n```json\n{glossary_str}\n```")

    if getattr(context, "rolling_history", None):
        history_lines = [
            f"- Gốc: \"{h.get('original', '')}\" -> Dịch: \"{h.get('translated', '')}\""
            for h in context.rolling_history
            if h.get('original')
        ]
        if history_lines:
            sys_inst_parts.append(
                "# CÁC CÂU THOẠI ĐÃ DỊCH TRƯỚC ĐÓ (DÙNG ĐỂ GIỮ MẠCH NGỮ CẢNH & XƯNG HÔ)\n"
                + "\n".join(history_lines)
            )

    return "\n\n---\n\n".join(sys_inst_parts)


class GeminiTranslateProvider(BaseTranslateProvider):

    def __init__(self, client=None, api_key: Optional[str] = None, sleeper=None):
        """
        Initializes the Gemini provider adapter.
        client: Pre-injected fake or real client (enables offline testing without google-genai dependency).
        api_key: Optional default API Key.
        sleeper: Injected sleep callback for testing retries.
        """
        self.client = client
        self.api_key = api_key
        self.sleeper = sleeper or time.sleep
        self.last_token_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0
        }

    def _get_client(self, config_api_key: Optional[str] = None):
        """Lazy-loads and initializes the Google GenAI SDK client."""
        if self.client is not None:
            return self.client

        # Safe lazy import so that unit tests can load without google-genai package
        from google import genai
        import os
        key = config_api_key or self.api_key or os.environ.get("GEMINI_API_KEY")
        if not key or not key.strip():
            raise ValueError("API Key cho Google Gemini không được để trống.")
        return genai.Client(api_key=key)

    def _update_token_usage(self, response: Any):
        """Parses usage metadata tokens safely from API response."""
        if not response or not hasattr(response, "usage_metadata") or not response.usage_metadata:
            return
        meta = response.usage_metadata
        self.last_token_usage["input_tokens"] += getattr(meta, "prompt_token_count", 0)
        self.last_token_usage["output_tokens"] += getattr(meta, "candidates_token_count", 0)
        self.last_token_usage["total_tokens"] += getattr(meta, "total_token_count", 0)

    def _call_with_retry(self, client: Any, model: str, contents: str, system_instruction: Optional[str], response_schema: Any = None) -> Any:
        """Helper to invoke generate_content with transient retry logic."""
        max_retries = 3
        backoff = 2

        # Configure request options using official SDK attributes
        # For structured outputs: response_mime_type and response_schema are set inside config
        from pydantic import BaseModel
        config_params = {}
        if system_instruction:
            config_params["system_instruction"] = system_instruction
        if response_schema:
            config_params["response_mime_type"] = "application/json"
            from pydantic import BaseModel, TypeAdapter
            raw_schema = {}
            if isinstance(response_schema, type) and issubclass(response_schema, BaseModel):
                raw_schema = response_schema.model_json_schema()
            else:
                try:
                    raw_schema = TypeAdapter(response_schema).json_schema()
                except Exception:
                    raw_schema = response_schema

            def clean_schema(schema: Any) -> Any:
                if isinstance(schema, dict):
                    cleaned = {}
                    for k, v in schema.items():
                        if k == "additionalProperties":
                            continue
                        cleaned[k] = clean_schema(v)
                    return cleaned
                elif isinstance(schema, list):
                    return [clean_schema(item) for item in schema]
                return schema

            config_params["response_schema"] = clean_schema(raw_schema)

        # Safe construction of config object inside google-genai SDK
        # In python google-genai SDK, genai.types.GenerateContentConfig is used
        # We can dynamically pass parameters if client is fake
        for attempt in range(max_retries + 1):
            try:
                # Lazy-import of config types when client is real
                if self.client is None:
                    from google.genai import types
                    config = types.GenerateContentConfig(**config_params)
                else:
                    config = config_params

                response = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config
                )
                self._update_token_usage(response)
                return response
            except Exception as e:
                err_str = str(e)
                # Parse transient status codes (429 rate limits, 5xx server issues)
                status_code = getattr(e, "code", getattr(e, "status_code", None))
                is_transient = False

                if status_code in (429, 500, 502, 503, 504):
                    is_transient = True
                elif any(x in err_str for x in ["429", "500", "502", "503", "504", "ResourceExhausted", "Resource exhausted"]):
                    # Never retry authentication or validation errors
                    if not any(x in err_str for x in ["401", "403", "API_KEY_INVALID", "Invalid API Key", "unauthorized"]):
                        is_transient = True

                if is_transient and attempt < max_retries:
                    sleep_dur = backoff ** attempt
                    self.sleeper(sleep_dur)
                    continue
                else:
                    raise e

    def analyze_context(
        self,
        sampled_segments: List[SubtitleSegment],
        config: TranslationConfig,
        cancel_event: threading.Event
    ) -> TranslationAnalysis:
        """Analyzes global context from sampled segments to capture video themes and styles."""
        if cancel_event.is_set():
            raise RuntimeError("Dịch vụ bị hủy trước khi phân tích ngữ cảnh.")

        client = self._get_client()
        model = resolve_profile_to_model(config.model)

        # Build prompt containing sample data
        sample_rows = [f"{s.index}: {s.text}" for s in sampled_segments]
        prompt = (
            "Dưới đây là một số dòng phụ đề mẫu được trích xuất từ file video gốc:\n"
            f"{chr(10).join(sample_rows)}\n\n"
            "Hãy phân tích và điền vào schema định dạng JSON. Yêu cầu:\n"
            "1. Nhận diện ngôn ngữ nguồn và trả về mã code (ví dụ: 'en', 'ja', 'ko', 'zh', 'und' nếu không rõ) và tên hiển thị tiếng Việt tương ứng (ví dụ: 'Tiếng Anh', 'Tiếng Nhật', 'Không xác định').\n"
            "2. Viết một tóm tắt bối cảnh và chủ đề chính rất ngắn gọn (tối đa 2-3 câu).\n"
            "3. Xác định tông giọng, cách xưng hô phù hợp của các nhân vật và thể loại nội dung."
        )

        system_instruction = (
            "Bạn là một chuyên gia nhận dạng ngôn ngữ và dịch thuật phim chuyên nghiệp. "
            "Hãy đưa ra phân tích bối cảnh và định hướng dịch để hỗ trợ định dạng phân tích có cấu trúc."
        )

        from modules.translate.schemas import TranslationAnalysis
        response = self._call_with_retry(
            client=client,
            model=model,
            contents=prompt,
            system_instruction=system_instruction,
            response_schema=TranslationAnalysis
        )

        response_text = response.text if hasattr(response, "text") else str(response)
        try:
            data = json.loads(response_text)
        except Exception:
            clean_text = response_text.strip()
            if clean_text.startswith("```"):
                lines = clean_text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1] == "```":
                    lines = lines[:-1]
                clean_text = "\n".join(lines).strip()
            try:
                data = json.loads(clean_text)
            except Exception:
                data = {}

        # Helper function to safely stringify and strip inputs
        def safe_str(val, default="") -> str:
            if val is None:
                return default
            if not isinstance(val, str):
                val = str(val)
            return val.strip()

        # Normalization
        code = safe_str(data.get("source_language_code"), "und").lower()
        name = safe_str(data.get("source_language_name"), "Không xác định")
        
        raw_summary = data.get("summary")
        if raw_summary is None or str(raw_summary).strip() == "":
            summary = safe_str(response_text, "Không xác định")
        else:
            summary = safe_str(raw_summary)

        tone = safe_str(data.get("tone"), "Không xác định")
        addr = safe_str(data.get("addressing_style"), "Không xác định")
        ctype = safe_str(data.get("content_type"), "Không xác định")

        if code in ("", "unknown", "und"):
            code = "und"
        if name.lower() in ("", "unknown", "không xác định"):
            name = "Không xác định"

        return TranslationAnalysis(
            source_language_code=code,
            source_language_name=name,
            summary=summary,
            tone=tone,
            addressing_style=addr,
            content_type=ctype
        )

    def translate_chunk(
        self,
        segments: List[SubtitleSegment],
        config: TranslationConfig,
        context: TranslationContext,
        cancel_event: threading.Event
    ) -> List[SubtitleSegment]:
        """Translates a single chunk of segments keeping timestamps intact."""
        if cancel_event.is_set():
            raise RuntimeError("Dịch vụ bị hủy trước khi dịch phân đoạn.")

        client = self._get_client()
        model = resolve_profile_to_model(config.model)

        # Prepare source payload with duration & word budget constraint
        enable_time_constraint = getattr(config, "enable_time_constraint", True)
        target_wps = getattr(config, "target_wps", 4.2)

        source_data = []
        from modules.translate.condenser import format_segment_for_prompt
        for s in segments:
            source_data.append(
                format_segment_for_prompt(
                    s,
                    target_wps=target_wps,
                    include_duration=enable_time_constraint
                )
            )
        source_json = json.dumps(source_data, ensure_ascii=False)

        # Construct translation prompt instructions
        prompt = f"Hãy dịch dữ liệu phụ đề JSON dưới đây sang ngôn ngữ đích: '{config.target_language}'.\n"
        prompt += f"Dữ liệu gốc:\n{source_json}\n"

        # System prompt with guidelines
        sys_inst = build_system_instruction(config, context)

        # Request structured JSON array response
        response = self._call_with_retry(
            client=client,
            model=model,
            contents=prompt,
            system_instruction=sys_inst,
            response_schema=List[TranslatedLine]
        )

        # Parse output and map back to source
        response_text = response.text if hasattr(response, "text") else str(response)
        
        # Defensive parse
        try:
            translated_lines = json.loads(response_text)
        except Exception:
            # Strip markdown formatting backticks if present
            clean_text = response_text.strip()
            if clean_text.startswith("```"):
                lines = clean_text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1] == "```":
                    lines = lines[:-1]
                clean_text = "\n".join(lines).strip()
            translated_lines = json.loads(clean_text)

        # Map back to SubtitleSegment preserving timestamps
        translated_segments = []
        source_map = {s.index: s for s in segments}

        for line in translated_lines:
            if not isinstance(line, dict):
                continue
            raw_idx = line.get("index")
            if raw_idx is None:
                continue
            try:
                idx = int(raw_idx)
            except (ValueError, TypeError):
                continue

            text = line.get("translated_text")
            if text is None:
                text = line.get("text") or line.get("translation") or line.get("translated") or ""

            if not isinstance(text, str):
                text = str(text)

            if idx in source_map:
                src_seg = source_map[idx]
                asr_corr = bool(line.get("asr_corrected", False))
                corr_src = line.get("corrected_source")
                corr_note = line.get("correction_note")
                orig_trans = line.get("original_translation")

                translated_segments.append(
                    SubtitleSegment(
                        index=src_seg.index,
                        start_ms=src_seg.start_ms,
                        end_ms=src_seg.end_ms,
                        text=text.strip(),
                        source="gemini_translate",
                        asr_corrected=asr_corr,
                        corrected_source=str(corr_src) if corr_src else None,
                        correction_note=str(corr_note) if corr_note else None,
                        original_translation=str(orig_trans) if orig_trans else None,
                    )
                )

        return translated_segments
