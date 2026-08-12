import importlib
from modules.subtitle.providers.base import SubtitleGenerationConfig, SubtitleProviderResult
from modules.subtitle.schemas import SubtitleSegment


class OpenAIWhisperRunner:
    def __call__(self, video_path: str, config: SubtitleGenerationConfig) -> SubtitleProviderResult:
        """Dynamically imports the 'whisper' library, loads the requested model,
        runs transcription, and converts the raw outputs to SubtitleProviderResult.
        """
        try:
            whisper = importlib.import_module("whisper")
        except ImportError:
            raise RuntimeError(
                "OpenAI Whisper package is not installed. Please install 'openai-whisper' to use this provider."
            )

        model = whisper.load_model(config.model)

        # Call transcribe on the model
        result = model.transcribe(video_path, language=config.language, task=config.task)

        raw_segments = result.get("segments", [])
        converted_segments = []
        index = 1

        for seg_dict in raw_segments:
            if "start" not in seg_dict or "end" not in seg_dict:
                raise ValueError("Segment missing required 'start' or 'end' key")

            start_sec = seg_dict["start"]
            end_sec = seg_dict["end"]

            if start_sec is None or end_sec is None:
                raise ValueError("Segment 'start' or 'end' cannot be None")

            # Convert start and end to rounded ms integers
            start_ms = int(round(start_sec * 1000))
            end_ms = int(round(end_sec * 1000))

            if start_ms < 0:
                raise ValueError(f"Segment start time must be non-negative, got {start_ms}ms")
            if end_ms <= start_ms:
                raise ValueError(f"Segment end time ({end_ms}ms) must be strictly greater than start_ms ({start_ms}ms)")

            text = seg_dict.get("text", "")
            if not text or not text.strip():
                # Skip empty text
                continue

            confidence = seg_dict.get("confidence")
            if confidence is not None:
                try:
                    confidence = float(confidence)
                except (ValueError, TypeError):
                    confidence = None

            converted_segments.append(
                SubtitleSegment(
                    index=index,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    text=text.strip(),
                    source="whisper",
                    confidence=confidence,
                )
            )
            index += 1

        metadata = {
            "provider": "openai-whisper",
            "model": config.model,
            "language": config.language,
            "task": config.task,
        }
        if "language" in result:
            metadata["raw_language"] = result["language"]

        return SubtitleProviderResult(segments=converted_segments, metadata=metadata)
