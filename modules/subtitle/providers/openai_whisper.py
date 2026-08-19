import importlib
import os
import sys
import shutil
import subprocess
import json
import tempfile
from typing import Callable, Optional
from modules.subtitle.providers.base import SubtitleGenerationConfig, SubtitleProviderResult
from modules.subtitle.schemas import SubtitleSegment


def find_whisper_binary() -> Optional[str]:
    if getattr(sys, 'frozen', False):
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        for exe in ["whisper.exe", "whisper", "main.exe", "main"]:
            path = os.path.join(base_dir, exe)
            if os.path.exists(path) and os.path.isfile(path):
                return path

    app_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.abspath(os.path.join(app_dir, "..", "..", ".."))
    for exe in ["whisper.exe", "whisper", "main.exe", "main"]:
        for d in [root_dir, os.getcwd()]:
            path = os.path.join(d, exe)
            if os.path.exists(path) and os.path.isfile(path):
                return path

    return shutil.which("whisper.exe") or shutil.which("whisper") or shutil.which("main.exe") or shutil.which("main")


class OpenAIWhisperRunner:
    def __call__(
        self,
        video_path: str,
        config: SubtitleGenerationConfig,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> SubtitleProviderResult:
        """Runs transcription using bundled Whisper binary or Python module dynamically."""
        whisper_bin = find_whisper_binary()
        result = None

        if whisper_bin:
            if progress_callback:
                progress_callback(20.0, "Khởi chạy hệ thống Whisper Binary...")

            with tempfile.TemporaryDirectory() as tmpdir:
                cmd = [
                    whisper_bin,
                    video_path,
                    "--model", config.model or "base",
                    "--output_dir", tmpdir,
                    "--output_format", "json"
                ]
                if config.language:
                    cmd.extend(["--language", config.language])
                if config.task:
                    cmd.extend(["--task", config.task])

                if progress_callback:
                    progress_callback(40.0, "Đang nhận diện giọng nói...")

                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if res.returncode != 0:
                    raise RuntimeError(f"Lỗi Whisper Binary: {res.stderr or res.stdout}")

                base_name = os.path.splitext(os.path.basename(video_path))[0]
                json_path = os.path.join(tmpdir, f"{base_name}.json")
                if not os.path.exists(json_path):
                    files = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir) if f.endswith(".json")]
                    if files:
                        json_path = files[0]
                    else:
                        raise RuntimeError("Không tìm thấy kết quả phụ đề JSON từ Whisper.")

                with open(json_path, "r", encoding="utf-8") as f:
                    result = json.load(f)
        else:
            try:
                whisper_module = importlib.import_module("whisper")
            except ImportError:
                raise RuntimeError(
                    "Gói OpenAI Whisper chưa được cài đặt. Vui lòng đảm bảo file whisper.exe được đóng gói kèm ứng dụng."
                )

            if progress_callback:
                progress_callback(20.0, "loading model")
            model = whisper_module.load_model(config.model or "base")

            if progress_callback:
                progress_callback(40.0, "transcribing")
            result = model.transcribe(video_path, language=config.language, task=config.task)

        if progress_callback:
            progress_callback(90.0, "formatting")

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
