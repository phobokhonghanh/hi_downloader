from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from modules.subtitle.schemas import SubtitleSegment


@dataclass(frozen=True)
class ChunkConfig:
    target_segments: int = 40
    hard_max_segments: int = 80
    target_chars: int = 2000
    hard_max_chars: int = 4000
    target_duration_ms: Optional[int] = None
    boundary_search_window: int = 10

    def validate(self) -> None:
        """Validates configuration parameters and raises ValueError on invalid configuration."""
        if self.target_segments <= 0:
            raise ValueError("target_segments phải lớn hơn 0.")
        if self.hard_max_segments <= 0:
            raise ValueError("hard_max_segments phải lớn hơn 0.")
        if self.target_segments > self.hard_max_segments:
            raise ValueError("target_segments không được vượt quá hard_max_segments.")

        if self.target_chars <= 0:
            raise ValueError("target_chars phải lớn hơn 0.")
        if self.hard_max_chars <= 0:
            raise ValueError("hard_max_chars phải lớn hơn 0.")
        if self.target_chars > self.hard_max_chars:
            raise ValueError("target_chars không được vượt quá hard_max_chars.")

        if self.boundary_search_window < 0:
            raise ValueError("boundary_search_window không được là số âm.")
        if self.target_duration_ms is not None and self.target_duration_ms <= 0:
            raise ValueError("target_duration_ms phải lớn hơn 0.")


@dataclass(frozen=True)
class ChunkMetadata:
    ordinal: int
    start_index: int
    end_index: int
    start_ms: int
    end_ms: int
    char_count: int
    preceding_gap_ms: Optional[int]
    boundary_reason: str
    warnings: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class SubtitleChunk:
    metadata: ChunkMetadata
    segments: List[SubtitleSegment]


@dataclass(frozen=True)
class TranslationConfig:
    target_language: str
    provider: Optional[str] = None
    model: Optional[str] = None
    glossary: Dict[str, str] = field(default_factory=dict)
    style_guide: Optional[str] = None
    context: Optional[str] = None
    chunk_config: ChunkConfig = field(default_factory=ChunkConfig)
    enable_time_constraint: bool = True
    target_wps: float = 4.2
    target_cps: float = 16.0



@dataclass(frozen=True)
class TranslationContext:
    global_summary: Optional[str] = None
    style_guide: Optional[str] = None
    glossary: Dict[str, str] = field(default_factory=dict)
    rolling_history: List[Dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class TranslationResult:
    success: bool
    translated_segments: List[SubtitleSegment] = field(default_factory=list)
    error: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)


class TranslationAnalysis(BaseModel):
    source_language_code: str = Field(default="und", description="Mã ngôn ngữ nguồn")
    source_language_name: str = Field(default="Không xác định", description="Tên hiển thị tiếng Việt")
    summary: str = Field(default="Không xác định", description="Tóm tắt bối cảnh")
    tone: str = Field(default="Không xác định", description="Tông giọng chính")
    addressing_style: str = Field(default="Không xác định", description="Cách xưng hô")
    content_type: str = Field(default="Không xác định", description="Thể loại nội dung")

    model_config = ConfigDict(frozen=True)
