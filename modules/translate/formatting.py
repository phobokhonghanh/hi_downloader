import re
from typing import List

# Matches HTML tags like <b>, </font> and ASS style blocks like {\an8}, {\pos(10,20)}
MARKER_RE = re.compile(r"(<[^>]+>|{[^}]+})")


def extract_formatting_markers(text: str) -> List[str]:
    """
    Extracts formatting tokens (HTML tags and ASS style blocks) in sequential order.
    """
    if not text:
        return []
    return MARKER_RE.findall(text)


def validate_formatting_markers(original: str, translated: str) -> bool:
    """
    Ensures that the sequence and content of formatting tags are strictly 
    preserved between original and translated strings. Returns True if valid.
    """
    orig_markers = extract_formatting_markers(original)
    trans_markers = extract_formatting_markers(translated)
    return orig_markers == trans_markers
