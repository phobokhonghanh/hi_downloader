import os
import time
import json
import hashlib
import tempfile
import threading
from typing import Optional, List, Dict, Any
from modules.subtitle.schemas import SubtitleSegment


def generate_chunk_cache_key(
    segments: List[SubtitleSegment],
    target_language: str,
    resolved_model: str,
    chunk_ordinal: int,
    global_context: Optional[str] = None,
    style_guide: Optional[str] = None,
    glossary: Optional[Dict[str, str]] = None,
    prompt_version: str = "v1"
) -> str:
    """
    Deterministically generates a SHA-256 hash string for a chunk, serving as a cache key.
    Includes only non-secret segment contents, metadata, and options.
    """
    seg_data = []
    for s in segments:
        seg_data.append({
            "index": s.index,
            "start_ms": s.start_ms,
            "end_ms": s.end_ms,
            "text": s.text
        })

    payload = {
        "segments": seg_data,
        "target_language": target_language,
        "resolved_model": resolved_model,
        "chunk_ordinal": chunk_ordinal,
        "global_context": global_context or "",
        "style_guide": style_guide or "",
        "glossary": glossary or {},
        "prompt_version": prompt_version
    }

    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class TranslationCache:

    def __init__(self, cache_root: str):
        self.cache_root = os.path.abspath(cache_root)
        os.makedirs(self.cache_root, exist_ok=True)
        self._lock = threading.RLock()

    def _validate_key(self, key: str) -> None:
        if not isinstance(key, str) or len(key) != 64 or not all(c in "0123456789abcdef" for c in key):
            raise ValueError("Mã key cache không hợp lệ (yêu cầu chuỗi SHA-256 hex thường 64 ký tự).")

    def get(self, key: str) -> Optional[List[SubtitleSegment]]:
        """
        Retrieves cached segments for the given key.
        Returns a list of SubtitleSegments if found and valid.
        Returns None if cache misses, is corrupted, or schema mismatch occurs.
        """
        self._validate_key(key)
        cache_path = os.path.join(self.cache_root, f"{key}.json")
        with self._lock:
            if not os.path.exists(cache_path):
                return None

            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Schema structural validation
                if not isinstance(data, dict) or "key" not in data or "segments" not in data:
                    return None
                if data["key"] != key:
                    return None

                segments = []
                for s in data["segments"]:
                    segments.append(
                        SubtitleSegment(
                            index=s["index"],
                            start_ms=s["start_ms"],
                            end_ms=s["end_ms"],
                            text=s["text"],
                            source="cache"
                        )
                    )
                return segments
            except Exception:
                # Treat corruption as a soft cache miss to prevent app crash
                return None

    def put(self, key: str, translated_segments: List[SubtitleSegment], metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Atomically saves translated segments to the cache directory under the given key.
        """
        self._validate_key(key)
        cache_path = os.path.join(self.cache_root, f"{key}.json")

        seg_data = []
        for s in translated_segments:
            seg_data.append({
                "index": s.index,
                "start_ms": s.start_ms,
                "end_ms": s.end_ms,
                "text": s.text
            })

        # Sanitize metadata to exclude any key containing sensitive patterns
        clean_metadata = {}
        if metadata:
            for k, v in metadata.items():
                if any(x in k.lower() for x in ["key", "token", "secret", "password"]):
                    continue
                clean_metadata[k] = v

        payload = {
            "key": key,
            "segments": seg_data,
            "metadata": clean_metadata,
            "timestamp": time.time()
        }

        serialized = json.dumps(payload, ensure_ascii=False, indent=2)

        with self._lock:
            # Atomic swap via temp file in the same directory path
            fd, tmp_path = tempfile.mkstemp(dir=self.cache_root, prefix="tmp_cache_")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(serialized)
                os.replace(tmp_path, cache_path)
            except Exception as e:
                # Cleanup temp leaks
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass
                raise e

    def invalidate(self, key: str) -> None:
        """Removes the cache file matching the given key."""
        self._validate_key(key)
        cache_path = os.path.join(self.cache_root, f"{key}.json")
        with self._lock:
            if os.path.exists(cache_path):
                try:
                    os.remove(cache_path)
                except Exception:
                    pass

    def cleanup(self, max_age_seconds: int) -> None:
        """Removes cache entries older than the specified age limit in seconds."""
        now = time.time()
        with self._lock:
            try:
                for filename in os.listdir(self.cache_root):
                    if not filename.endswith(".json"):
                        continue
                    file_path = os.path.join(self.cache_root, filename)
                    try:
                        mtime = os.path.getmtime(file_path)
                        if now - mtime > max_age_seconds:
                            os.remove(file_path)
                    except Exception:
                        pass
            except Exception:
                pass
