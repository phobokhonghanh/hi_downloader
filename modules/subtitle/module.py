from typing import Dict, Any
from core.base_module import BaseModule, ModuleContext, ModuleResult, ModuleMetadata
from modules.subtitle.schemas import SubtitleSegment
from modules.subtitle.srt import parse_srt, export_srt
from modules.subtitle.editor import SubtitleEditor
from modules.subtitle.providers import WhisperSubtitleProvider, SubtitleGenerationConfig
from modules.subtitle.providers.openai_whisper import OpenAIWhisperRunner


class SubtitleModule(BaseModule):
    def __init__(self, whisper_provider=None):
        """Initializes the SubtitleModule. Accepts an optional whisper_provider adapter."""
        if whisper_provider is None:
            whisper_provider = WhisperSubtitleProvider(runner=OpenAIWhisperRunner())
        self.whisper_provider = whisper_provider

    @property
    def module_id(self) -> str:
        return "subtitle"

    @property
    def metadata(self) -> ModuleMetadata:
        return ModuleMetadata(
            module_id=self.module_id,
            name="Subtitle Module",
            description="Subtitle editing core module providing parsing, exporting, merging, splitting, and text replacing operations.",
            input_schema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["parse_srt", "export_srt", "merge", "split", "replace_text", "generate_whisper"],
                        "description": "The subtitle action to perform",
                    },
                    "srt_text": {"type": "string", "description": "Raw SRT content for parsing"},
                    "segments": {"type": "array", "description": "List of subtitle segments as dictionaries"},
                    "start_index": {"type": "integer", "description": "Starting index for merging"},
                    "end_index": {"type": "integer", "description": "Ending index for merging"},
                    "index": {"type": "integer", "description": "Segment index for splitting or replacing text"},
                    "split_at_ms": {"type": "integer", "description": "Split time point in milliseconds"},
                    "first_text": {"type": "string", "description": "Text of the first segment after splitting"},
                    "second_text": {"type": "string", "description": "Text of the second segment after splitting"},
                    "text": {"type": "string", "description": "New text for replacing segment content"},
                    "video_path": {"type": "string", "description": "Path to the video file for Whisper generation"},
                    "model": {"type": "string", "default": "base", "description": "Whisper model to use"},
                    "language": {"type": "string", "description": "Optional Whisper transcription language"},
                    "task": {
                        "type": "string",
                        "enum": ["transcribe", "translate"],
                        "default": "transcribe",
                        "description": "Whisper task to perform",
                    },
                    "max_gap_ms": {"type": "integer", "default": 300},
                    "max_duration_ms": {"type": "integer", "default": 6000},
                    "max_chars": {"type": "integer", "default": 120},
                    "allow_large_gap": {"type": "boolean", "default": False},
                },
                "required": ["action"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "canceled": {"type": "boolean"},
                    "metrics": {"type": "object"},
                    "error": {"type": "string"},
                },
            },
            supports_standalone=True,
            supports_workflow=True,
        )

    def validate_params(self, params: Dict[str, Any]) -> bool:
        if not params or not isinstance(params, dict):
            return False
        action = params.get("action")
        if action not in ("parse_srt", "export_srt", "merge", "split", "replace_text", "generate_whisper"):
            return False

        if action == "parse_srt":
            srt_text = params.get("srt_text")
            if srt_text is None or not isinstance(srt_text, str):
                return False

        elif action == "export_srt":
            segments = params.get("segments")
            if segments is None or not isinstance(segments, list):
                return False

        elif action == "merge":
            segments = params.get("segments")
            if segments is None or not isinstance(segments, list):
                return False
            start_index = params.get("start_index")
            end_index = params.get("end_index")
            if start_index is None or not isinstance(start_index, int):
                return False
            if end_index is None or not isinstance(end_index, int):
                return False

            for k in ("max_gap_ms", "max_duration_ms", "max_chars"):
                if k in params and params[k] is not None and not isinstance(params[k], int):
                    return False
            if "allow_large_gap" in params and params["allow_large_gap"] is not None and not isinstance(
                params["allow_large_gap"], bool
            ):
                return False

        elif action == "split":
            segments = params.get("segments")
            if segments is None or not isinstance(segments, list):
                return False
            index = params.get("index")
            split_at_ms = params.get("split_at_ms")
            first_text = params.get("first_text")
            second_text = params.get("second_text")

            if index is None or not isinstance(index, int):
                return False
            if split_at_ms is None or not isinstance(split_at_ms, int):
                return False
            if first_text is None or not isinstance(first_text, str):
                return False
            if second_text is None or not isinstance(second_text, str):
                return False

        elif action == "replace_text":
            segments = params.get("segments")
            if segments is None or not isinstance(segments, list):
                return False
            index = params.get("index")
            text = params.get("text")
            if index is None or not isinstance(index, int):
                return False
            if text is None or not isinstance(text, str):
                return False

        elif action == "generate_whisper":
            video_path = params.get("video_path")
            if video_path is None or not isinstance(video_path, str) or not video_path.strip():
                return False

            model = params.get("model")
            if model is not None and not isinstance(model, str):
                return False

            language = params.get("language")
            if language is not None and not isinstance(language, str):
                return False

            task = params.get("task")
            if task is not None and task not in ("transcribe", "translate"):
                return False

        return True

    def run(self, context: ModuleContext) -> ModuleResult:
        if context.cancel_event.is_set():
            return ModuleResult(success=False, canceled=True, error="Canceled before run")

        params = context.params
        if not self.validate_params(params):
            return ModuleResult(success=False, error="Invalid parameters")

        action = params["action"]

        try:
            if action == "parse_srt":
                srt_text = params["srt_text"]
                segments = parse_srt(srt_text)
                return ModuleResult(success=True, metrics={"segments": [s.to_dict() for s in segments]})

            elif action == "export_srt":
                segments_data = params["segments"]
                segs = [SubtitleSegment.from_dict(d) for d in segments_data]
                srt_text = export_srt(segs)
                return ModuleResult(success=True, metrics={"srt_text": srt_text})

            elif action == "generate_whisper":
                video_path = params["video_path"]
                model_val = params.get("model", "base")
                task_val = params.get("task", "transcribe")
                language_val = params.get("language")

                config = SubtitleGenerationConfig(model=model_val, task=task_val, language=language_val)

                if context.cancel_event.is_set():
                    return ModuleResult(success=False, canceled=True, error="Canceled before run")

                result = self.whisper_provider.generate(video_path, config)
                return ModuleResult(
                    success=True,
                    metrics={
                        "segments": [s.to_dict() for s in result.segments],
                        "metadata": result.metadata,
                        "srt_text": export_srt(result.segments),
                    },
                )

            # For editor actions, deserialize list of dicts first
            segments_data = params["segments"]
            segs = [SubtitleSegment.from_dict(d) for d in segments_data]
            editor = SubtitleEditor(segs)

            if action == "merge":
                kwargs = {}
                for key in ("max_gap_ms", "max_duration_ms", "max_chars", "allow_large_gap"):
                    if key in params and params[key] is not None:
                        kwargs[key] = params[key]

                merged_seg = editor.merge_segments(params["start_index"], params["end_index"], **kwargs)
                return ModuleResult(
                    success=True,
                    metrics={
                        "segments": [s.to_dict() for s in editor.list_segments()],
                        "merged_segment": merged_seg.to_dict(),
                    },
                )

            elif action == "split":
                first, second = editor.split_segment(
                    params["index"], params["split_at_ms"], params["first_text"], params["second_text"]
                )
                return ModuleResult(
                    success=True,
                    metrics={
                        "segments": [s.to_dict() for s in editor.list_segments()],
                        "split_segments": [first.to_dict(), second.to_dict()],
                    },
                )

            elif action == "replace_text":
                editor.replace_text(params["index"], params["text"])
                return ModuleResult(success=True, metrics={"segments": [s.to_dict() for s in editor.list_segments()]})

        except Exception as e:
            return ModuleResult(success=False, error=str(e))

        return ModuleResult(success=False, error="Unsupported action")
