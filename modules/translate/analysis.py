import threading
from typing import List
from modules.subtitle.schemas import SubtitleSegment
from modules.translate.schemas import TranslationConfig, TranslationAnalysis
from modules.translate.providers.base import BaseTranslateProvider
from modules.translate.chunker import sample_context_segments


def analyze_translation_context(
    segments: List[SubtitleSegment],
    config: TranslationConfig,
    provider: BaseTranslateProvider,
    cancel_event: threading.Event
) -> TranslationAnalysis:
    """
    Extracts deterministic samples of segments and queries the provider to analyze
    global context before translating.
    """
    if cancel_event.is_set():
        raise RuntimeError("Operation canceled before context analysis.")

    # Use existing deterministic sampler
    sampled = sample_context_segments(segments, max_sample_segs=15)

    # Request provider context summary
    return provider.analyze_context(sampled, config, cancel_event)
