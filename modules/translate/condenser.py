import math
from typing import Dict, Any, List, Optional
from modules.subtitle.schemas import SubtitleSegment


def calculate_segment_word_budget(
    start_ms: int,
    end_ms: int,
    target_wps: float = 4.2,
    min_words: int = 4,
    margin: float = 0.15
) -> int:
    """
    Calculates the maximum recommended word count for a subtitle segment given its duration,
    target words per second (WPS), and soft flexibility margin (+15%).

    :param start_ms: Start timestamp in milliseconds.
    :param end_ms: End timestamp in milliseconds.
    :param target_wps: Target speaking rate in words per second (default 4.2 wps for Vietnamese).
    :param min_words: Minimum word limit fallback for extremely short segments.
    :param margin: Soft flexibility margin (default 0.15 = +15% words).
    :return: Maximum allowed words.
    """
    duration_s = max(0.0, (end_ms - start_ms) / 1000.0)
    budget = math.floor(duration_s * target_wps * (1.0 + margin))
    return max(min_words, budget)


def calculate_segment_char_budget(
    start_ms: int,
    end_ms: int,
    target_cps: float = 16.0,
    min_chars: int = 12
) -> int:
    """
    Calculates the maximum recommended character count for a subtitle segment given its duration
    and target characters per second (CPS).

    :param start_ms: Start timestamp in milliseconds.
    :param end_ms: End timestamp in milliseconds.
    :param target_cps: Target speaking rate in characters per second.
    :param min_chars: Minimum character limit fallback.
    :return: Maximum allowed characters.
    """
    duration_s = max(0.0, (end_ms - start_ms) / 1000.0)
    budget = math.floor(duration_s * target_cps)
    return max(min_chars, budget)


import re

def count_words(text: str) -> int:
    """Utility to count non-empty words in a string, correctly treating CJK characters as words."""
    if not text:
        return 0
    # Count CJK characters (Chinese, Japanese, Korean)
    cjk_chars = len(re.findall(r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]', text))
    # Strip CJK characters to count remaining space-separated words
    non_cjk_text = re.sub(r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]', ' ', text)
    space_words = len(non_cjk_text.strip().split())
    return cjk_chars + space_words



def check_segment_duration_overflow(
    segment: SubtitleSegment,
    target_wps: float = 4.2
) -> Dict[str, Any]:
    """
    Checks if a segment's text word count exceeds its duration budget.

    :param segment: SubtitleSegment instance.
    :param target_wps: Target speaking rate in words per second.
    :return: Dict with overflow metrics and warning flag.
    """
    duration_s = round(max(0.0, (segment.end_ms - segment.start_ms) / 1000.0), 2)
    max_words = calculate_segment_word_budget(segment.start_ms, segment.end_ms, target_wps=target_wps)
    actual_words = count_words(segment.text)
    actual_wps = round(actual_words / duration_s, 2) if duration_s > 0 else 0.0
    is_overflow = actual_words > max_words

    overflow_ratio = round((actual_words - max_words) / max_words, 2) if is_overflow and max_words > 0 else 0.0

    return {
        "index": segment.index,
        "duration_s": duration_s,
        "max_words": max_words,
        "actual_words": actual_words,
        "actual_wps": actual_wps,
        "target_wps": target_wps,
        "is_overflow": is_overflow,
        "overflow_ratio": overflow_ratio,
        "text": segment.text
    }


def format_segment_for_prompt(
    segment: SubtitleSegment,
    target_wps: float = 4.2,
    include_duration: bool = True
) -> Dict[str, Any]:
    """
    Formats a subtitle segment into a JSON-serializable dictionary for LLM prompts.
    Selectively includes duration and max_words constraints ONLY when the segment's
    text length actually exceeds its timeline duration budget (is_overflow).
    """
    payload: Dict[str, Any] = {
        "index": segment.index,
        "text": segment.text
    }
    if include_duration:
        duration_s = round(max(0.0, (segment.end_ms - segment.start_ms) / 1000.0), 2)
        budget = calculate_segment_word_budget(segment.start_ms, segment.end_ms, target_wps=target_wps)
        words = count_words(segment.text)
        # Check if source text is tight/overflowing relative to timeline duration
        if words > budget or (duration_s > 0 and words / duration_s > 3.5):
            payload["duration_s"] = duration_s
            payload["max_words"] = budget
            payload["is_overtime"] = True
    return payload


