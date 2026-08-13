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

        # Prepare source payload
        source_data = []
        for s in segments:
            source_data.append({"index": s.index, "text": s.text})
        source_json = json.dumps(source_data, ensure_ascii=False)

        # Construct translation prompt instructions
        prompt = f"Hãy dịch dữ liệu phụ đề JSON dưới đây sang ngôn ngữ đích: '{config.target_language}'.\n"
        prompt += f"Dữ liệu gốc:\n{source_json}\n"

        # System prompt with guidelines
        sys_inst = (
            "Bạn là một biên dịch viên phụ đề chuyên nghiệp. "
            f"Hãy tự động nhận diện ngôn ngữ nguồn và dịch sang ngôn ngữ: '{config.target_language}'.\n"
            "Yêu cầu:\n"
            "1. Bảo toàn ý nghĩa gốc, ánh xạ 1-1 theo dòng phụ đề.\n"
            "2. Giữ nguyên tất cả các thẻ định dạng HTML (ví dụ <b>, <i>) hoặc ASS style blocks (ví dụ {\\an8}, {\\pos(x,y)}).\n"
            "3. Không tự tiện viết thêm lời bình luận, lời giải thích hay bất cứ nội dung thừa nào ngoài JSON bản dịch.\n"
        )

        if context.global_summary:
            sys_inst += f"\nBối cảnh tổng quát của video:\n{context.global_summary}\n"
        if context.style_guide:
            sys_inst += f"\nYêu cầu văn phong: {context.style_guide}\n"
        if context.glossary:
            sys_inst += f"\nDanh mục thuật ngữ bắt buộc dịch theo:\n{json.dumps(context.glossary, ensure_ascii=False)}\n"
        
        if context.rolling_history:
            sys_inst += "\nMột số câu thoại trước đó để tham khảo bối cảnh xưng hô liền mạch:\n"
            for h in context.rolling_history:
                sys_inst += f"Gốc: '{h.get('original')}' -> Dịch: '{h.get('translated')}'\n"

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
            idx = int(line["index"])
            text = line["translated_text"]
            if idx in source_map:
                src_seg = source_map[idx]
                translated_segments.append(
                    SubtitleSegment(
                        index=src_seg.index,
                        start_ms=src_seg.start_ms,
                        end_ms=src_seg.end_ms,
                        text=text,
                        source="gemini_translate"
                    )
                )

        return translated_segments
