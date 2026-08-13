from abc import ABC, abstractmethod
from typing import List, Optional
import threading
from modules.subtitle.schemas import SubtitleSegment
from modules.translate.schemas import TranslationConfig, TranslationContext, TranslationAnalysis


class BaseTranslateProvider(ABC):

    @abstractmethod
    def analyze_context(
        self,
        sampled_segments: List[SubtitleSegment],
        config: TranslationConfig,
        cancel_event: threading.Event
    ) -> TranslationAnalysis:
        """
        Analyzes global context from sampled segments to construct a rolling summary.
        """
        pass

    @abstractmethod
    def translate_chunk(
        self,
        segments: List[SubtitleSegment],
        config: TranslationConfig,
        context: TranslationContext,
        cancel_event: threading.Event
    ) -> List[SubtitleSegment]:
        """
        Translates a list of SubtitleSegments within a chunk using the provided configuration and context.
        Returns translated SubtitleSegments matching source indexes.
        """
        pass
