import { state } from './state.js';
import * as api from './api.js';
import { triggerTaskPolling, triggerLogPolling } from './polling.js';

const btnDownload = document.getElementById('btn-download');
const customOutputDir = document.getElementById('custom-output-dir');
const qualitySelect = document.getElementById('quality-select');
const pageStart = document.getElementById('page-start');
const pageEnd = document.getElementById('page-end');

export function initDownload() {
    if (btnDownload) {
        btnDownload.addEventListener('click', async () => {
            const targetPath = customOutputDir.dataset.fullPath || null;
            const reqBody = {
                url: state.currentAnalyzedUrl,
                cookies_browser: state.currentWorkingBrowser,
                output_dir: targetPath
            };

            if (state.currentAnalyzedType === 'video') {
                reqBody.quality = qualitySelect.value;
            } else if (state.currentAnalyzedType === 'space') {
                reqBody.page_start = parseInt(pageStart.value);
                reqBody.page_end = parseInt(pageEnd.value);
                const maxVideosEl = document.getElementById('max-videos');
                const maxV = maxVideosEl ? parseInt(maxVideosEl.value) : 0;
                if (maxV && maxV > 0) {
                    reqBody.max_videos = maxV;
                }
            }

            try {
                const res = await api.downloadVideo(reqBody);
                if (res.ok) {
                    triggerTaskPolling();
                    triggerLogPolling();
                } else {
                    alert("Lỗi tạo tiến trình.");
                }
            } catch (e) {
                alert("Không thể gửi lệnh tải.");
            }
        });
    }
}
