import re
from typing import List
from modules.subtitle.schemas import SubtitleSegment

TIMESTAMP_RE = re.compile(r"^(\d{2,}):(\d{2}):(\d{2}),(\d{3})$")


def parse_timestamp(ts_str: str) -> int:
    """Converts a timestamp string in HH:MM:SS,mmm format to milliseconds."""
    ts_str = ts_str.strip()
    match = TIMESTAMP_RE.match(ts_str)
    if not match:
        raise ValueError(f"Invalid timestamp format: '{ts_str}'. Expected 'HH:MM:SS,mmm'")

    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    milliseconds = int(match.group(4))

    if minutes >= 60:
        raise ValueError(f"Minutes cannot be >= 60: {minutes}")
    if seconds >= 60:
        raise ValueError(f"Seconds cannot be >= 60: {seconds}")

    return (hours * 3600 + minutes * 60 + seconds) * 1000 + milliseconds


def to_timestamp(ms: int) -> str:
    """Converts milliseconds to a timestamp string in HH:MM:SS,mmm format."""
    if ms < 0:
        raise ValueError(f"Milliseconds cannot be negative, got {ms}")
    hours = ms // 3600000
    ms %= 3600000
    minutes = ms // 60000
    ms %= 60000
    seconds = ms // 1000
    milliseconds = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def parse_srt(text: str) -> List[SubtitleSegment]:
    """Parses standard SRT content into a list of SubtitleSegment instances."""
    lines = text.splitlines()
    segments = []
    i = 0
    n = len(lines)

    while i < n:
        # Skip extra blank lines
        if not lines[i].strip():
            i += 1
            continue

        # 1. Parse index
        index_line = lines[i].strip()
        try:
            index = int(index_line)
        except ValueError:
            raise ValueError(f"Expected numeric index, got '{index_line}'")

        expected_index = len(segments) + 1
        if index != expected_index:
            raise ValueError(f"Malformed SRT: index out of order. Expected {expected_index}, got {index}")

        i += 1

        # Ensure we have a timestamp line
        if i >= n:
            raise ValueError("Unexpected end of file while looking for timestamp line")

        # 2. Parse timestamp line
        timestamp_line = lines[i].strip()
        if " --> " not in timestamp_line:
            raise ValueError(f"Expected ' --> ' separator in timestamp line: '{timestamp_line}'")
        parts = timestamp_line.split(" --> ")
        if len(parts) != 2:
            raise ValueError(f"Malformed timestamp line: '{timestamp_line}'")

        try:
            start_ms = parse_timestamp(parts[0])
        except ValueError as e:
            raise ValueError(f"Invalid start timestamp: {e}")
        try:
            end_ms = parse_timestamp(parts[1])
        except ValueError as e:
            raise ValueError(f"Invalid end timestamp: {e}")

        if end_ms <= start_ms:
            raise ValueError(f"End time ({end_ms}ms) must be greater than start time ({start_ms}ms)")

        # Verify chronological order across segments
        if segments:
            prev_seg = segments[-1]
            if start_ms < prev_seg.start_ms:
                raise ValueError(
                    f"Segment start time ({start_ms}ms) is before previous segment start time ({prev_seg.start_ms}ms)"
                )

        i += 1

        # 3. Parse text lines until the next blank line
        text_lines = []
        while i < n and lines[i].strip():
            text_lines.append(lines[i])
            i += 1

        segment_text = "\n".join(text_lines)
        if not segment_text.strip():
            raise ValueError(f"Segment text cannot be empty (index={index})")

        segments.append(
            SubtitleSegment(
                index=index,
                start_ms=start_ms,
                end_ms=end_ms,
                text=segment_text,
                source="manual",
            )
        )

        # Skip any trailing blank lines
        while i < n and not lines[i].strip():
            i += 1

    return segments


def export_srt(segments: List[SubtitleSegment]) -> str:
    """Exports a list of SubtitleSegment instances to a standard SRT string with sequential indices starting at 1."""
    blocks = []
    for idx, seg in enumerate(segments, start=1):
        start_ts = to_timestamp(seg.start_ms)
        end_ts = to_timestamp(seg.end_ms)
        block = f"{idx}\n{start_ts} --> {end_ts}\n{seg.text}"
        blocks.append(block)

    return "\n\n".join(blocks) + "\n" if blocks else ""
