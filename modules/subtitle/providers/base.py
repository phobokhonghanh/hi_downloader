from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from modules.subtitle.schemas import SubtitleSegment


@dataclass
class SubtitleGenerationConfig:
    model: str = "base"
    language: Optional[str] = None
    task: str = "transcribe"
    source: str = "whisper"


@dataclass
class SubtitleProviderResult:
    segments: List[SubtitleSegment]
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseSubtitleProvider(ABC):
    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Returns the unique identifier for this provider."""
        pass

    @abstractmethod
    def generate(self, video_path: str, config: SubtitleGenerationConfig) -> SubtitleProviderResult:
        """Generates subtitles for the given video path using the provided configuration."""
        pass
