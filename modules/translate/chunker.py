from typing import List, Optional
from modules.subtitle.schemas import SubtitleSegment
from modules.translate.schemas import ChunkConfig, ChunkMetadata, SubtitleChunk


def chunk_segments(segments: List[SubtitleSegment], config: ChunkConfig) -> List[SubtitleChunk]:
    """
    Splits a list of SubtitleSegments into SubtitleChunks based on scene-aware gaps
    and character/segment constraints.
    
    Boundary priority:
      - Tier 1: gap >= 8000ms (Strong gap)
      - Tier 2: gap >= 3000ms (Normal gap)
      - Tier 3: gap >= 1000ms (Fallback gap)
      - Falls back to hard limits (hard_max_segments or hard_max_chars) if no soft gap is found.
      - Overlong segments (> hard_max_chars) are isolated into single-segment chunks.
    """
    if not segments:
        return []

    # 1. Validate configuration parameters first
    config.validate()

    chunks = []
    n = len(segments)
    start_idx = 0
    ordinal = 1

    while start_idx < n:
        # Check if the single segment at start_idx is already overlong
        first_seg = segments[start_idx]
        first_seg_chars = len(first_seg.text)

        if first_seg_chars > config.hard_max_chars:
            preceding_gap = None
            if start_idx > 0:
                preceding_gap = first_seg.start_ms - segments[start_idx - 1].end_ms

            metadata = ChunkMetadata(
                ordinal=ordinal,
                start_index=first_seg.index,
                end_index=first_seg.index,
                start_ms=first_seg.start_ms,
                end_ms=first_seg.end_ms,
                char_count=first_seg_chars,
                preceding_gap_ms=preceding_gap,
                boundary_reason="overlong_segment",
                warnings=[
                    f"Segment #{first_seg.index} length ({first_seg_chars} chars) "
                    f"exceeds hard limit of {config.hard_max_chars}."
                ]
            )
            chunks.append(SubtitleChunk(metadata=metadata, segments=[first_seg]))
            start_idx += 1
            ordinal += 1
            continue

        # Find the hard limits (max_split_idx)
        accum_chars = 0
        limit_idx = start_idx
        while limit_idx < n:
            seg = segments[limit_idx]
            # Check hard limits
            if (limit_idx - start_idx + 1) > config.hard_max_segments:
                break
            if (accum_chars + len(seg.text)) > config.hard_max_chars:
                break
            accum_chars += len(seg.text)
            limit_idx += 1

        max_split_idx = limit_idx  # Exclusive index of next chunk start (i.e. we cut at max_split_idx)
        
        # Calculate target_char_idx based on target character limit threshold
        target_char_idx = n
        temp_chars = 0
        for i in range(start_idx, n):
            temp_chars += len(segments[i].text)
            if temp_chars >= config.target_chars:
                target_char_idx = i + 1  # Split cut index after this segment
                break

        # Sizing target index (whichever target constraint threshold is reached first)
        target_idx = min(start_idx + config.target_segments, target_char_idx)

        # Soft boundaries search window
        min_split_idx = max(start_idx + 1, target_idx - config.boundary_search_window)

        best_split_idx = None
        best_tier = 0  # 3: Strong, 2: Normal, 1: Fallback, 0: None
        best_gap = -1
        best_distance = 999999

        # Scan for the best soft boundary in the search window
        for split_idx in range(min_split_idx, min(max_split_idx + 1, n)):
            curr_seg = segments[split_idx]
            prev_seg = segments[split_idx - 1]
            gap = curr_seg.start_ms - prev_seg.end_ms

            tier = 0
            if gap >= 8000:
                tier = 3
            elif gap >= 3000:
                tier = 2
            elif gap >= 1000:
                tier = 1

            if tier > 0:
                if tier > best_tier:
                    best_tier = tier
                    best_gap = gap
                    best_split_idx = split_idx
                    best_distance = abs(split_idx - target_idx)
                elif tier == best_tier:
                    if gap > best_gap:
                        best_gap = gap
                        best_split_idx = split_idx
                        best_distance = abs(split_idx - target_idx)
                    elif gap == best_gap:
                        dist = abs(split_idx - target_idx)
                        if dist < best_distance:
                            best_distance = dist
                            best_split_idx = split_idx

        # Determine the final split index
        if best_split_idx is not None:
            reason = "strong_gap" if best_tier == 3 else "normal_gap" if best_tier == 2 else "fallback_gap"
            final_split_idx = best_split_idx
        else:
            if max_split_idx < n:
                final_split_idx = max_split_idx
                reason = "hard_limit"
            else:
                final_split_idx = n
                reason = "end_of_file"

        chunk_segs = segments[start_idx:final_split_idx]
        char_count = sum(len(s.text) for s in chunk_segs)

        preceding_gap = None
        if start_idx > 0:
            preceding_gap = segments[start_idx].start_ms - segments[start_idx - 1].end_ms

        metadata = ChunkMetadata(
            ordinal=ordinal,
            start_index=chunk_segs[0].index,
            end_index=chunk_segs[-1].index,
            start_ms=chunk_segs[0].start_ms,
            end_ms=chunk_segs[-1].end_ms,
            char_count=char_count,
            preceding_gap_ms=preceding_gap,
            boundary_reason=reason,
            warnings=[]
        )
        chunks.append(SubtitleChunk(metadata=metadata, segments=chunk_segs))
        start_idx = final_split_idx
        ordinal += 1

    return chunks


def sample_context_segments(segments: List[SubtitleSegment], max_sample_segs: int = 15) -> List[SubtitleSegment]:
    """
    Selects a deterministic sample of segments distributed across the beginning,
    middle, and end of the list for global translation context extraction.
    """
    if not segments:
        return []

    n = len(segments)
    if n <= max_sample_segs:
        return list(segments)

    if max_sample_segs <= 6:
        indices = [int(i * (n - 1) / (max_sample_segs - 1)) for i in range(max_sample_segs)]
    else:
        beg_count = 3
        end_count = 3
        mid_count = max_sample_segs - beg_count - end_count

        beg_indices = list(range(beg_count))
        end_indices = list(range(n - end_count, n))

        mid_start = beg_count
        mid_end = n - end_count - 1

        mid_indices = []
        if mid_count > 0 and mid_end >= mid_start:
            if mid_count == 1:
                mid_indices = [mid_start + (mid_end - mid_start) // 2]
            else:
                for i in range(mid_count):
                    mid_indices.append(mid_start + int(i * (mid_end - mid_start) / (mid_count - 1)))

        indices = sorted(list(set(beg_indices + mid_indices + end_indices)))

    return [segments[i] for i in indices if i < n]
