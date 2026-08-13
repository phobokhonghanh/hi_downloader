from typing import List
import threading
from modules.subtitle.schemas import SubtitleSegment
from modules.translate.providers.base import BaseTranslateProvider
from modules.translate.schemas import TranslationConfig, TranslationContext, TranslationAnalysis


class MockTranslateProvider(BaseTranslateProvider):

    def __init__(self, error_trigger: str = "__ERROR__", behavior_prefix: str = ""):
        self.error_trigger = error_trigger
        self.behavior_prefix = behavior_prefix

    def analyze_context(
        self,
        sampled_segments: List[SubtitleSegment],
        config: TranslationConfig,
        cancel_event: threading.Event
    ) -> TranslationAnalysis:
        if cancel_event.is_set():
            raise RuntimeError("Operation canceled cooperatively / bị hủy trong analyze_context.")
        return TranslationAnalysis(
            source_language_code="en",
            source_language_name="Tiếng Anh",
            summary=f"Mock global context: target_language={config.target_language}, sampled={len(sampled_segments)}",
            tone="trang trọng",
            addressing_style="tôi - bạn",
            content_type="phim ảnh"
        )

    def translate_chunk(
        self,
        segments: List[SubtitleSegment],
        config: TranslationConfig,
        context: TranslationContext,
        cancel_event: threading.Event
    ) -> List[SubtitleSegment]:
        if cancel_event.is_set():
            raise RuntimeError("Operation canceled cooperatively / bị hủy trong translate_chunk.")

        translated = []
        for seg in segments:
            if self.error_trigger in seg.text:
                raise ValueError(f"Mock translation failed at segment #{seg.index} due to trigger: {self.error_trigger}")

            # Translate text logic
            translated_text = f"{self.behavior_prefix}[{config.target_language}] {seg.text}"
            
            # Apply glossary translations
            for key, val in config.glossary.items():
                translated_text = translated_text.replace(key, val)

            translated.append(
                SubtitleSegment(
                    index=seg.index,
                    start_ms=seg.start_ms,
                    end_ms=seg.end_ms,
                    text=translated_text,
                    source="mock_translate"
                )
            )

        return translated
