from typing import Dict, Any
from core.base_module import BaseModule, ModuleContext, ModuleResult, ModuleMetadata
from modules.downloader.service import DownloaderService
from modules.downloader.schemas import AnalyzeRequestData, DownloadRequestData


class DownloaderModule(BaseModule):
    def __init__(self, service: DownloaderService):
        self.service = service

    @property
    def module_id(self) -> str:
        return "downloader"

    @property
    def metadata(self) -> ModuleMetadata:
        return ModuleMetadata(
            module_id=self.module_id,
            name="Downloader Module",
            description="Hi Downloader module for analyzing URLs and downloading video/space media files.",
            input_schema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["analyze", "download"], "description": "The action to perform"},
                    "url": {"type": "string", "description": "Bilibili URL"},
                    "quality": {"type": "string", "default": "best"},
                    "page_start": {"type": "integer", "default": 1},
                    "page_end": {"type": "integer", "default": 1},
                    "max_videos": {"type": "integer"}
                },
                "required": ["action", "url"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "metrics": {"type": "object"}
                }
            },
            supports_standalone=True,
            supports_workflow=True,
            requires_output_dir=True
        )

    def validate_params(self, params: Dict[str, Any]) -> bool:
        if not params:
            return False
        action = params.get("action")
        if action not in ("analyze", "download"):
            return False
        url = params.get("url")
        if not url or not isinstance(url, str) or not url.strip():
            return False
        return True

    def run(self, context: ModuleContext) -> ModuleResult:
        if context.cancel_event.is_set():
            return ModuleResult(success=False, canceled=True, error="Canceled before run")

        params = context.params
        if not self.validate_params(params):
            return ModuleResult(success=False, error="Invalid parameters")

        action = params["action"]
        url = params["url"]

        try:
            if action == "analyze":
                req_data = AnalyzeRequestData(
                    url=url,
                    cookies_browser=params.get("cookies_browser")
                )
                res = self.service.analyze(req_data)
                return ModuleResult(
                    success=True,
                    metrics={"analysis": res}
                )
            elif action == "download":
                req_data = DownloadRequestData(
                    url=url,
                    cookies_browser=params.get("cookies_browser"),
                    quality=params.get("quality", "best"),
                    page_start=int(params.get("page_start", 1)),
                    page_end=int(params.get("page_end", 1)),
                    max_videos=params.get("max_videos"),
                    output_dir=context.output_dir
                )
                res = self.service.start_download(req_data)
                return ModuleResult(
                    success=True,
                    metrics={"download": {
                        "task_id": res.task_id,
                        "status": res.status
                    }}
                )
        except Exception as e:
            return ModuleResult(success=False, error=str(e))

        return ModuleResult(success=False, error="Unsupported action")
