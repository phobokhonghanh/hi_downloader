import json
import unittest
import threading
from modules.subtitle.schemas import SubtitleSegment
from modules.translate.providers.models import TRANSLATION_PROFILES, resolve_profile_to_model
from modules.translate.providers.gemini import GeminiTranslateProvider
from modules.translate.schemas import TranslationConfig, TranslationContext, ChunkConfig


class FakeGenerateContentResponse:

    def __init__(self, text: str, prompt_tokens: int = 15, candidates_tokens: int = 20):
        self.text = text
        class UsageMetadata:
            def __init__(self):
                self.prompt_token_count = prompt_tokens
                self.candidates_token_count = candidates_tokens
                self.total_token_count = prompt_tokens + candidates_tokens
        self.usage_metadata = UsageMetadata()


class FakeModels:

    def __init__(self, response_callback=None):
        self.calls = []
        self.response_callback = response_callback or (lambda model, contents, config: FakeGenerateContentResponse("[]"))

    def generate_content(self, model, contents, config):
        self.calls.append({
            "model": model,
            "contents": contents,
            "config": config
        })
        return self.response_callback(model, contents, config)


class FakeClient:

    def __init__(self, response_callback=None):
        self.models = FakeModels(response_callback)


class TestTranslateGemini(unittest.TestCase):

    def test_catalog_profiles_labels_and_ids(self):
        """Test that the catalog has exactly three profiles with correct Vietnamese descriptions."""
        self.assertEqual(len(TRANSLATION_PROFILES), 3)
        
        profiles_map = {p["id"]: p for p in TRANSLATION_PROFILES}
        self.assertIn("economy", profiles_map)
        self.assertIn("balanced", profiles_map)
        self.assertIn("quality", profiles_map)

        # Labels should contain profile levels and correct model names
        self.assertIn("Gemini 3.5 Flash Lite", profiles_map["economy"]["name"])
        self.assertIn("Gemini 3.5 Flash", profiles_map["balanced"]["name"])
        self.assertIn("Gemini 3.6 Flash", profiles_map["quality"]["name"])

        self.assertEqual(resolve_profile_to_model("economy"), "gemini-3.5-flash-lite")
        self.assertEqual(resolve_profile_to_model("balanced"), "gemini-3.5-flash")
        self.assertEqual(resolve_profile_to_model("quality"), "gemini-3.6-flash")

        # Invalid profile resolution checks
        with self.assertRaises(ValueError):
            resolve_profile_to_model("")
        with self.assertRaises(ValueError):
            resolve_profile_to_model("   ")
        with self.assertRaises(ValueError):
            resolve_profile_to_model("invalid_profile_model")

    def test_context_analysis_prompt_structure(self):
        """Test global context prompt construction and token metrics tracking."""
        def mock_behavior(model, contents, config):
            self.assertEqual(model, "gemini-3.5-flash-lite")
            self.assertIn("định hướng dịch", config.get("system_instruction", ""))
            self.assertIn("1: S1", contents)
            return FakeGenerateContentResponse("Mock video analysis summary.", prompt_tokens=100, candidates_tokens=50)

        fake_client = FakeClient(response_callback=mock_behavior)
        provider = GeminiTranslateProvider(client=fake_client)

        segments = [SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="S1")]
        config = TranslationConfig(target_language="vi", model="economy")
        
        summary = provider.analyze_context(segments, config, threading.Event())
        self.assertEqual(summary.summary, "Mock video analysis summary.")
        self.assertEqual(provider.last_token_usage["input_tokens"], 100)
        self.assertEqual(provider.last_token_usage["output_tokens"], 50)
        self.assertEqual(provider.last_token_usage["total_tokens"], 150)

    def test_translate_chunk_mapping_and_reconstruction(self):
        """Test correct segment index translation mapping and timestamps preservation."""
        raw_json_response = '[{"index": 1, "translated_text": "[vi] S1"}, {"index": 2, "translated_text": "[vi] S2"}]'
        
        fake_client = FakeClient(response_callback=lambda m, c, cfg: FakeGenerateContentResponse(raw_json_response))
        provider = GeminiTranslateProvider(client=fake_client)

        segments = [
            SubtitleSegment(index=1, start_ms=100, end_ms=900, text="S1"),
            SubtitleSegment(index=2, start_ms=1000, end_ms=1900, text="S2"),
        ]

        config = TranslationConfig(target_language="vi", model="balanced")
        context = TranslationContext(global_summary="Bối cảnh mẫu")

        results = provider.translate_chunk(segments, config, context, threading.Event())
        self.assertEqual(len(results), 2)

        # Check texts translation
        self.assertEqual(results[0].text, "[vi] S1")
        self.assertEqual(results[1].text, "[vi] S2")

        # Verify timestamps are successfully reconstructed from source mapping
        self.assertEqual(results[0].index, 1)
        self.assertEqual(results[0].start_ms, 100)
        self.assertEqual(results[0].end_ms, 900)

        self.assertEqual(results[1].index, 2)
        self.assertEqual(results[1].start_ms, 1000)
        self.assertEqual(results[1].end_ms, 1900)

    def test_transient_retries_logic(self):
        """Test retry loop activates and sleeps on transient rate limits / 5xx codes."""
        calls_count = 0
        slept_intervals = []

        def mock_flaky_behavior(model, contents, config):
            nonlocal calls_count
            calls_count += 1
            if calls_count < 3:
                # Raise transient error status
                raise Exception("ResourceExhausted: Rate limit exceeded (429)")
            return FakeGenerateContentResponse('[{"index": 1, "translated_text": "OK"}]')

        fake_client = FakeClient(response_callback=mock_flaky_behavior)
        
        def mock_sleeper(duration):
            slept_intervals.append(duration)

        provider = GeminiTranslateProvider(client=fake_client, sleeper=mock_sleeper)

        segments = [SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="S1")]
        config = TranslationConfig(target_language="vi", model="balanced")
        context = TranslationContext()

        results = provider.translate_chunk(segments, config, context, threading.Event())
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].text, "OK")

        # Assert calls ran 3 times (2 flaky failures + 1 final success)
        self.assertEqual(calls_count, 3)
        # Assert sleeper calls matches exponential backoff (2^0 = 1, 2^1 = 2)
        self.assertEqual(slept_intervals, [1, 2])

    def test_non_retry_errors_abort(self):
        """Test API errors like authorization or invalid request bypass retries."""
        calls_count = 0
        def mock_auth_behavior(model, contents, config):
            nonlocal calls_count
            calls_count += 1
            raise Exception("API_KEY_INVALID: API key is not valid (403/401)")

        fake_client = FakeClient(response_callback=mock_auth_behavior)
        slept_intervals = []
        provider = GeminiTranslateProvider(client=fake_client, sleeper=lambda d: slept_intervals.append(d))

        segments = [SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="S1")]
        config = TranslationConfig(target_language="vi", model="balanced")
        context = TranslationContext()

        with self.assertRaises(Exception):
            provider.translate_chunk(segments, config, context, threading.Event())

        # Authentication failures abort immediately on the 1st attempt
        self.assertEqual(calls_count, 1)
        self.assertEqual(len(slept_intervals), 0)

    def test_malformed_json_markdown_backticks_parsing(self):
        """Test that JSON wrapped in markdown formatting backticks is defensively parsed."""
        raw_markdown = "```json\n[{\n  \"index\": 1,\n  \"translated_text\": \"Dịch mượt\"\n}]\n```"
        fake_client = FakeClient(response_callback=lambda m, c, cfg: FakeGenerateContentResponse(raw_markdown))
        provider = GeminiTranslateProvider(client=fake_client)

        segments = [SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="S1")]
        config = TranslationConfig(target_language="vi", model="balanced")
        context = TranslationContext()

        results = provider.translate_chunk(segments, config, context, threading.Event())
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].text, "Dịch mượt")

    def test_api_key_safety(self):
        """Verify that provider logs, metrics metadata and config do not expose secret API Key."""
        fake_client = FakeClient(response_callback=lambda m, c, cfg: FakeGenerateContentResponse("[]"))
        provider = GeminiTranslateProvider(client=fake_client, api_key="SUPER_SECRET_KEY")

        # Key shouldn't be exposed inside usage metrics or catalogs
        self.assertNotIn("SUPER_SECRET_KEY", str(provider.last_token_usage))
        self.assertNotIn("SUPER_SECRET_KEY", str(TRANSLATION_PROFILES))

    def test_gemini_structured_analysis_success_and_fallback(self):
        """Test structured Gemini context analysis parsing and fallback behaviors."""
        from modules.translate.schemas import TranslationAnalysis
        
        # 1. Structured JSON success case
        structured_json = (
            "{\n"
            "  \"source_language_code\": \"ja\",\n"
            "  \"source_language_name\": \"Tiếng Nhật\",\n"
            "  \"summary\": \"Phim hoạt hình Anime\",\n"
            "  \"tone\": \"hài hước\",\n"
            "  \"addressing_style\": \"cậu - tớ\",\n"
            "  \"content_type\": \"Anime\"\n"
            "}"
        )
        fake_client_ok = FakeClient(response_callback=lambda m, c, cfg: FakeGenerateContentResponse(structured_json))
        provider_ok = GeminiTranslateProvider(client=fake_client_ok)
        
        segments = [SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="S1")]
        config = TranslationConfig(target_language="vi", model="balanced")
        
        analysis = provider_ok.analyze_context(segments, config, threading.Event())
        self.assertEqual(analysis.source_language_code, "ja")
        self.assertEqual(analysis.source_language_name, "Tiếng Nhật")
        self.assertEqual(analysis.summary, "Phim hoạt hình Anime")
        self.assertEqual(analysis.tone, "hài hước")
        self.assertEqual(analysis.addressing_style, "cậu - tớ")
        self.assertEqual(analysis.content_type, "Anime")

        # 2. Defensively fallback on raw text
        fake_client_raw = FakeClient(response_callback=lambda m, c, cfg: FakeGenerateContentResponse("Raw unstructured text explanation"))
        provider_raw = GeminiTranslateProvider(client=fake_client_raw)
        analysis_raw = provider_raw.analyze_context(segments, config, threading.Event())
        
        self.assertEqual(analysis_raw.source_language_code, "und")
        self.assertEqual(analysis_raw.source_language_name, "Không xác định")
        self.assertEqual(analysis_raw.summary, "Raw unstructured text explanation")
        self.assertEqual(analysis_raw.tone, "Không xác định")

    def test_gemini_normalization_hardening_non_string_values(self):
        """Test Gemini normalization handles non-string and null parameters without raising AttributeError."""
        malformed_json = (
            "{\n"
            "  \"source_language_code\": null,\n"
            "  \"source_language_name\": 12345,\n"
            "  \"summary\": \"\",\n"
            "  \"tone\": null,\n"
            "  \"addressing_style\": [\"tớ\", \"cậu\"],\n"
            "  \"content_type\": {}\n"
            "}"
        )
        fake_client = FakeClient(response_callback=lambda m, c, cfg: FakeGenerateContentResponse(malformed_json))
        provider = GeminiTranslateProvider(client=fake_client)
        
        segments = [SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="S1")]
        config = TranslationConfig(target_language="vi", model="balanced")
        
        analysis = provider.analyze_context(segments, config, threading.Event())
        self.assertEqual(analysis.source_language_code, "und")
        self.assertEqual(analysis.source_language_name, "12345")
        self.assertEqual(analysis.tone, "Không xác định")
        self.assertEqual(analysis.addressing_style, "['tớ', 'cậu']")
        self.assertEqual(analysis.content_type, "{}")

    def test_gemini_schema_compatibility(self):
        """Test that additionalProperties is recursively stripped from custom schemas before API call."""
        calls_recorded = []
        def mock_callback(model, contents, config):
            calls_recorded.append(config)
            return FakeGenerateContentResponse("[]")

        fake_client = FakeClient(response_callback=mock_callback)
        provider = GeminiTranslateProvider(client=fake_client)
        
        segments = [SubtitleSegment(index=1, start_ms=0, end_ms=1000, text="S1")]
        config = TranslationConfig(target_language="vi", model="balanced")
        
        # Trigger translation which passes List[TranslatedLine] schema
        try:
            provider.translate_chunk(segments, config, TranslationContext(), threading.Event())
        except Exception:
            pass

        self.assertEqual(len(calls_recorded), 1)
        sent_config = calls_recorded[0]
        schema = sent_config.get("response_schema")
        self.assertIsNotNone(schema)
        
        # Verify schema is a dict and has no additionalProperties keys
        self.assertIsInstance(schema, dict)
        
        def check_no_additional_properties(s):
            if isinstance(s, dict):
                self.assertNotIn("additionalProperties", s)
                for v in s.values():
                    check_no_additional_properties(v)
            elif isinstance(s, list):
                for item in s:
                    check_no_additional_properties(item)
                    
        check_no_additional_properties(schema)

    def test_gemini_error_sanitization(self):
        """Test that translation errors are mapped to concise Vietnamese user messages without API key leaks."""
        from modules.translate.batch_service import sanitize_translation_error
        
        # 1. API key leak check
        leak_err = Exception("Failed call to API Key AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T with error code 403")
        sanitized = sanitize_translation_error(leak_err)
        self.assertNotIn("AIzaSy", sanitized)
        self.assertIn("API key", sanitized)
        
        # 2. Rate limit 429 error
        rate_err = Exception("Resource has exhausted resource quota: Rate limit exceeded (429)")
        sanitized_rate = sanitize_translation_error(rate_err)
        self.assertEqual(sanitized_rate, "Vượt quá giới hạn lượt yêu cầu (Rate Limit). Vui lòng thử lại sau.")

        # 3. Safety block
        safety_err = Exception("Content was blocked due to safety block configurations")
        sanitized_safety = sanitize_translation_error(safety_err)
        self.assertEqual(sanitized_safety, "Nội dung bị chặn bởi bộ lọc an toàn của AI.")

