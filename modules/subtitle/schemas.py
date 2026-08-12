from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class SubtitleSegment:
    index: int
    start_ms: int
    end_ms: int
    text: str
    source: str = "manual"
    confidence: Optional[float] = None

    @property
    def duration_ms(self) -> int:
        """Returns the duration of the segment in milliseconds."""
        return self.end_ms - self.start_ms

    def gap_to_next(self, next_segment: "SubtitleSegment") -> int:
        """Returns the gap in milliseconds between this segment and the next segment."""
        return next_segment.start_ms - self.end_ms

    def overlaps(self, other: "SubtitleSegment") -> bool:
        """Returns True if this segment overlaps with the other segment, False otherwise."""
        return max(self.start_ms, other.start_ms) < min(self.end_ms, other.end_ms)

    def to_dict(self) -> dict:
        """Serializes the segment to a dictionary."""
        return {
            "index": self.index,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "text": self.text,
            "source": self.source,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SubtitleSegment":
        """Deserializes a dictionary into a SubtitleSegment instance."""
        return cls(
            index=data["index"],
            start_ms=data["start_ms"],
            end_ms=data["end_ms"],
            text=data["text"],
            source=data.get("source", "manual"),
            confidence=data.get("confidence"),
        )

    def validate(self) -> List[str]:
        """Validates individual segment fields and returns a list of error strings."""
        errors = []
        if self.index < 1:
            errors.append(f"Index must be >= 1, got {self.index}")
        if self.start_ms < 0:
            errors.append(f"start_ms must be >= 0, got {self.start_ms}")
        if self.end_ms <= self.start_ms:
            errors.append(f"end_ms ({self.end_ms}) must be strictly greater than start_ms ({self.start_ms})")
        if not self.text or not self.text.strip():
            errors.append("text cannot be empty or only whitespace")
        if self.confidence is not None:
            if not (0.0 <= self.confidence <= 1.0):
                errors.append(f"confidence must be in range 0..1, got {self.confidence}")
        return errors


@dataclass
class SubtitleProject:
    project_id: str
    video_path: str
    raw_segments: List[SubtitleSegment] = field(default_factory=list)
    edited_segments: List[SubtitleSegment] = field(default_factory=list)
    settings: Dict[str, Any] = field(default_factory=dict)

    def get_active_segments(self, use_edited: bool = True) -> List[SubtitleSegment]:
        """Returns the active segments. Defaults to edited_segments if use_edited is True."""
        return self.edited_segments if use_edited else self.raw_segments

    def to_dict(self) -> dict:
        """Serializes the project to a dictionary."""
        return {
            "project_id": self.project_id,
            "video_path": self.video_path,
            "raw_segments": [s.to_dict() for s in self.raw_segments],
            "edited_segments": [s.to_dict() for s in self.edited_segments],
            "settings": self.settings,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SubtitleProject":
        """Deserializes a dictionary into a SubtitleProject instance."""
        raw_segs = [SubtitleSegment.from_dict(s) for s in data.get("raw_segments", [])]
        edited_segs = [SubtitleSegment.from_dict(s) for s in data.get("edited_segments", [])]
        return cls(
            project_id=data["project_id"],
            video_path=data["video_path"],
            raw_segments=raw_segs,
            edited_segments=edited_segs,
            settings=data.get("settings", {}),
        )

    def validate(self) -> List[str]:
        """Aggregates all segment validation errors and validates chronological ordering/no overlaps for edited segments."""
        errors = []

        # Aggregate raw segment validation errors
        for i, segment in enumerate(self.raw_segments):
            seg_errors = segment.validate()
            for err in seg_errors:
                errors.append(f"Raw segment at index {i} (segment index {segment.index}): {err}")

        # Aggregate edited segment validation errors
        for i, segment in enumerate(self.edited_segments):
            seg_errors = segment.validate()
            for err in seg_errors:
                errors.append(f"Edited segment at index {i} (segment index {segment.index}): {err}")

        # Chronological ordering for edited segments
        for i in range(len(self.edited_segments) - 1):
            curr_seg = self.edited_segments[i]
            next_seg = self.edited_segments[i + 1]
            if curr_seg.start_ms > next_seg.start_ms:
                errors.append(
                    f"Edited segments are not in chronological order: segment at index {i} (start: {curr_seg.start_ms}ms) "
                    f"is after segment at index {i + 1} (start: {next_seg.start_ms}ms)"
                )

        # Overlap check for edited segments
        for i in range(len(self.edited_segments)):
            for j in range(i + 1, len(self.edited_segments)):
                seg_i = self.edited_segments[i]
                seg_j = self.edited_segments[j]
                if seg_i.overlaps(seg_j):
                    errors.append(
                        f"Edited segment at index {i} (segment index {seg_i.index}, [{seg_i.start_ms}-{seg_i.end_ms}]ms) "
                        f"overlaps with segment at index {j} (segment index {seg_j.index}, [{seg_j.start_ms}-{seg_j.end_ms}]ms)"
                    )

        return errors
