from typing import Callable, Optional, List, Dict, Any
from modules.subtitle.providers.base import BaseSubtitleProvider, SubtitleGenerationConfig, SubtitleProviderResult
from modules.subtitle.schemas import SubtitleSegment


class WhisperSubtitleProvider(BaseSubtitleProvider):
    def __init__(self, runner: Optional[Callable] = None):
        """Initializes WhisperSubtitleProvider with an optional runner callable."""
        self.runner = runner

    @property
    def provider_id(self) -> str:
        return "whisper"

    def generate(self, video_path: str, config: SubtitleGenerationConfig) -> SubtitleProviderResult:
        """Validates parameters, calls the runner if configured, and normalizes output to SubtitleProviderResult."""
        if self.runner is None:
            raise RuntimeError("Whisper runner is not configured")

        if not video_path or not video_path.strip():
            raise ValueError("video_path cannot be empty or whitespace")

        if config.task not in ("transcribe", "translate"):
            raise ValueError(f"Invalid task: '{config.task}'. Expected 'transcribe' or 'translate'")

        res = self.runner(video_path, config)

        if isinstance(res, SubtitleProviderResult):
            return res
        elif isinstance(res, list):
            if not res:
                return SubtitleProviderResult(segments=[], metadata={})
            # Check type of first element
            first = res[0]
            if isinstance(first, SubtitleSegment):
                return SubtitleProviderResult(segments=res, metadata={})
            elif isinstance(first, dict):
                segments = [SubtitleSegment.from_dict(d) for d in res]
                return SubtitleProviderResult(segments=segments, metadata={})
            else:
                raise TypeError(f"Unsupported runner list element type: {type(first)}")
        else:
            raise TypeError(f"Unsupported runner return type: {type(res)}")
