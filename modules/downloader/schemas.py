from dataclasses import dataclass
from typing import Optional


@dataclass
class AnalyzeRequestData:
    url: str
    cookies_browser: Optional[str] = None


@dataclass
class DownloadRequestData:
    url: str
    cookies_browser: Optional[str] = None
    quality: str = "best"
    page_start: int = 1
    page_end: int = 1
    max_videos: Optional[int] = None
    output_dir: Optional[str] = None


@dataclass
class DownloadTaskResult:
    task_id: str
    status: str = "pending"
    error: Optional[str] = None
