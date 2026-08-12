import copy
from typing import List, Tuple
from modules.subtitle.schemas import SubtitleSegment


class SubtitleEditor:
    def __init__(self, segments: List[SubtitleSegment]):
        """Initializes the SubtitleEditor with a list of SubtitleSegment instances.
        Keeps a deep copy internally to prevent external mutation.
        """
        self.segments = copy.deepcopy(segments)
        # Ensure all segments are indexed sequentially starting at 1
        for idx, seg in enumerate(self.segments, start=1):
            seg.index = idx

    def list_segments(self) -> List[SubtitleSegment]:
        """Returns defensive deep copies of the current segments."""
        return copy.deepcopy(self.segments)

    def merge_segments(
        self,
        start_index: int,
        end_index: int,
        max_gap_ms: int = 300,
        max_duration_ms: int = 6000,
        max_chars: int = 120,
        allow_large_gap: bool = False,
    ) -> SubtitleSegment:
        """Merges consecutive subtitle segments from start_index to end_index inclusive.
        Reindexes all segments after a successful merge and returns the new merged segment.
        """
        # Find position in self.segments list
        start_pos = -1
        end_pos = -1
        for pos, seg in enumerate(self.segments):
            if seg.index == start_index:
                start_pos = pos
            if seg.index == end_index:
                end_pos = pos

        if start_pos == -1 or end_pos == -1:
            raise ValueError(f"Segment indices {start_index} and/or {end_index} not found")

        if start_pos > end_pos:
            start_pos, end_pos = end_pos, start_pos

        if start_pos == end_pos:
            raise ValueError("Merging a segment with itself is not allowed")

        segs_to_merge = self.segments[start_pos : end_pos + 1]

        # 1. Check adjacent gaps
        for k in range(len(segs_to_merge) - 1):
            gap = segs_to_merge[k].gap_to_next(segs_to_merge[k + 1])
            if gap > max_gap_ms and not allow_large_gap:
                raise ValueError(
                    f"Adjacent gap ({gap}ms) exceeds max_gap_ms ({max_gap_ms}ms) "
                    f"between segment index {segs_to_merge[k].index} and {segs_to_merge[k + 1].index}"
                )

        # 2. Check merged duration
        merged_start_ms = segs_to_merge[0].start_ms
        merged_end_ms = segs_to_merge[-1].end_ms
        duration = merged_end_ms - merged_start_ms
        if duration > max_duration_ms:
            raise ValueError(f"Merged duration ({duration}ms) exceeds max_duration_ms ({max_duration_ms}ms)")

        # 3. Check merged text length
        merged_text = " ".join(s.text.strip() for s in segs_to_merge)
        if len(merged_text) > max_chars:
            raise ValueError(f"Merged text length ({len(merged_text)}) exceeds max_chars ({max_chars})")

        # Create merged segment
        merged_segment = SubtitleSegment(
            index=start_index,  # Will be updated during reindexing
            start_ms=merged_start_ms,
            end_ms=merged_end_ms,
            text=merged_text,
            source="manual",
        )

        # Replace in-place
        self.segments[start_pos : end_pos + 1] = [merged_segment]

        # Reindex
        for idx, seg in enumerate(self.segments, start=1):
            seg.index = idx

        # Find the merged segment inside the reindexed list to return the one with the correct index
        return copy.deepcopy(self.segments[start_pos])

    def split_segment(
        self, index: int, split_at_ms: int, first_text: str, second_text: str
    ) -> Tuple[SubtitleSegment, SubtitleSegment]:
        """Splits a single segment into two at split_at_ms.
        Validates that split_at_ms is strictly inside the segment and that both texts are non-empty.
        Reindexes all segments and returns the two new segments.
        """
        pos = -1
        for i, seg in enumerate(self.segments):
            if seg.index == index:
                pos = i
                break

        if pos == -1:
            raise ValueError(f"Segment with index {index} not found")

        seg = self.segments[pos]

        # Validate split time is strictly inside the segment
        if not (seg.start_ms < split_at_ms < seg.end_ms):
            raise ValueError(
                f"Split time {split_at_ms}ms is not strictly inside segment index {index} [{seg.start_ms}-{seg.end_ms}]ms"
            )

        # Validate non-empty texts
        if not first_text.strip():
            raise ValueError("First text cannot be empty or only whitespace")
        if not second_text.strip():
            raise ValueError("Second text cannot be empty or only whitespace")

        first_seg = SubtitleSegment(
            index=index, start_ms=seg.start_ms, end_ms=split_at_ms, text=first_text.strip(), source="manual"
        )
        second_seg = SubtitleSegment(
            index=index + 1, start_ms=split_at_ms, end_ms=seg.end_ms, text=second_text.strip(), source="manual"
        )

        # Insert new segments
        self.segments[pos : pos + 1] = [first_seg, second_seg]

        # Reindex
        for idx, s in enumerate(self.segments, start=1):
            s.index = idx

        return copy.deepcopy(self.segments[pos]), copy.deepcopy(self.segments[pos + 1])

    def replace_text(self, index: int, text: str) -> None:
        """Replaces the text of a segment at index. Validates that the new text is non-empty."""
        if not text.strip():
            raise ValueError("Text cannot be empty or only whitespace")

        for seg in self.segments:
            if seg.index == index:
                seg.text = text.strip()
                return

        raise ValueError(f"Segment with index {index} not found")
