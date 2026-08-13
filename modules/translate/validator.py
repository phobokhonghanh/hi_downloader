from typing import List
from modules.subtitle.schemas import SubtitleSegment


def validate_segments(segments: List[SubtitleSegment]) -> List[str]:
    """
    Validates a list of SubtitleSegments according to strict structural criteria:
      - Non-empty list
      - Unique contiguous indexes in sequential source order (starting from segments[0].index)
      - Integer non-negative timestamps with end > start
      - Monotonic ordering without invalid overlaps (current start >= previous end)
      - Non-empty text content
    Returns a list of error description strings. If list is empty, validation passed.
    """
    errors = []
    if not segments:
        errors.append("Danh sách segments không được để trống.")
        return errors

    first_index = segments[0].index
    for i, seg in enumerate(segments):
        # 1. Index contiguous validation
        expected_index = first_index + i
        if seg.index != expected_index:
            errors.append(f"Chỉ số index không liên tục tại vị trí {i}: mong đợi {expected_index}, nhận {seg.index}.")

        # 2. Field validation (index >= 1, start_ms >= 0, end_ms > start_ms, text not empty)
        # Check type
        if not isinstance(seg.index, int):
            errors.append(f"Segment vị trí {i}: index phải là số nguyên.")
        if not isinstance(seg.start_ms, int) or not isinstance(seg.end_ms, int):
            errors.append(f"Segment #{seg.index}: start_ms và end_ms phải là số nguyên.")
        
        seg_errors = seg.validate()
        if seg_errors:
            errors.extend([f"Segment #{seg.index}: {err}" for err in seg_errors])

        # 3. Monotonic ordering validation
        if i > 0:
            prev = segments[i - 1]
            if seg.start_ms < prev.start_ms:
                errors.append(
                    f"Thứ tự thời gian không đơn điệu: Segment #{seg.index} start_ms ({seg.start_ms}) "
                    f"nhỏ hơn Segment #{prev.index} start_ms ({prev.start_ms})."
                )

    return errors
