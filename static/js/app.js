const btnAnalyze = document.getElementById('btn-analyze');
const btnDownload = document.getElementById('btn-download');
const btnSelectDir = document.getElementById('btn-select-dir');

const btnClearQueue = document.getElementById('btn-clear-queue');
const btnClearLogs = document.getElementById('btn-clear-logs');
const btnCopyLogs = document.getElementById('btn-copy-logs');

const analysisBox = document.getElementById('analysis-box');
const analysisTitle = document.getElementById('analysis-title');
const analysisSummary = document.getElementById('analysis-summary');

const qualitySelectorGroup = document.getElementById('quality-selector-group');
const qualitySelect = document.getElementById('quality-select');

const spacePagesGroup = document.getElementById('space-pages-group');
const pageStart = document.getElementById('page-start');
const pageEnd = document.getElementById('page-end');

const tasksContainer = document.getElementById('tasks-container');
const queueEmptyMsg = document.getElementById('queue-empty-msg');
const customOutputDir = document.getElementById('custom-output-dir');
const customProxyFile = document.getElementById('custom-proxy-file');
const btnSelectProxy = document.getElementById('btn-select-proxy');
const btnClearProxy = document.getElementById('btn-clear-proxy');
const btnSelectVideo = document.getElementById('btn-subtitle-select-video');
const terminalBody = document.getElementById('terminal-body');
const btnScrollBottom = document.getElementById('btn-scroll-bottom');

// URL history DOM elements
const historySection = document.getElementById('history-section');
const historyList = document.getElementById('history-list');
const btnClearHistory = document.getElementById('btn-clear-history');

let userIsScrolledUp = false;

terminalBody.addEventListener('scroll', () => {
    const threshold = 30;
    const distanceToBottom = terminalBody.scrollHeight - terminalBody.clientHeight - terminalBody.scrollTop;
    if (distanceToBottom > threshold) {
        userIsScrolledUp = true;
        btnScrollBottom.style.display = 'flex';
    } else {
        userIsScrolledUp = false;
        btnScrollBottom.style.display = 'none';
    }
});

btnScrollBottom.addEventListener('click', () => {
    userIsScrolledUp = false;
    btnScrollBottom.style.display = 'none';
    terminalBody.scrollTo({
        top: terminalBody.scrollHeight,
        behavior: 'smooth'
    });
});

let currentAnalyzedUrl = '';
let currentAnalyzedType = '';
let currentWorkingBrowser = null;
let allTasks = [];
let currentSubtitleSegments = [];

function getFilename(path) {
    return path.split(/[/\\]/).pop() || path;
}

function truncatePath(path, maxDirs = 3) {
    if (!path) return '';
    const parts = path.split(/[/\\]/).filter(Boolean);
    if (parts.length <= maxDirs) return path;
    const prefix = path.startsWith('/') ? '.../' : '...\\';
    return prefix + parts.slice(-maxDirs).join('/');
}

function updateDirDisplay(fullPath) {
    if (!fullPath) return;
    customOutputDir.dataset.fullPath = fullPath;
    customOutputDir.value = truncatePath(fullPath, 3);
    customOutputDir.title = fullPath;
}

function updateProxyDisplay(customPath, systemPath) {
    if (customPath) {
        customProxyFile.value = truncatePath(customPath, 3);
        customProxyFile.title = customPath;
    } else if (systemPath) {
        customProxyFile.value = truncatePath(systemPath, 3);
        customProxyFile.title = systemPath;
    } else {
        customProxyFile.value = "Dùng proxy system mặc định";
        customProxyFile.title = "Không cấu hình proxy";
    }
}

async function checkSystem() {
    try {
        const res = await fetch('/api/system');
        const data = await res.json();
        updateDirDisplay(data.download_dir);
        updateProxyDisplay(data.proxy_file, data.system_proxy_file);
    } catch (err) {
        console.error("Lỗi quét hệ thống:", err);
    }
}

// OS directory selection click handler
if (btnSelectDir) {
    btnSelectDir.addEventListener('click', async () => {
        btnSelectDir.disabled = true;
        try {
            const res = await fetch('/api/select-directory', { method: 'POST' });
            if (res.ok) {
                const data = await res.json();
                if (data.status === 'success' && data.path) {
                    updateDirDisplay(data.path);
                }
            } else {
                let errMsg = "Lỗi không xác định";
                try {
                    const err = await res.json();
                    errMsg = err.message || err.detail || JSON.stringify(err);
                } catch (e) {
                    errMsg = await res.text();
                }
                alert("Không thể chọn thư mục: " + errMsg);
            }
        } catch (e) {
            alert("Lỗi kết nối hộp thoại chọn thư mục.");
        } finally {
            btnSelectDir.disabled = false;
        }
    });
}

// URL history functions
function getHistoryItems() {
    try {
        const raw = localStorage.getItem('bilibili_downloader_history');
        if (!raw) return [];
        const items = JSON.parse(raw);
        if (!Array.isArray(items)) {
            throw new Error("Invalid history structure");
        }
        return items;
    } catch (e) {
        console.error("Corrupted history data, clearing...", e);
        localStorage.removeItem('bilibili_downloader_history');
        return [];
    }
}

function loadHistory() {
    const items = getHistoryItems();
    if (historyList) {
        historyList.innerHTML = '';
        if (items.length === 0) {
            if (btnClearHistory) btnClearHistory.style.display = 'none';
            const emptyDiv = document.createElement('div');
            emptyDiv.className = 'history-empty-state';
            emptyDiv.textContent = 'Chưa có lịch sử tìm kiếm.';
            historyList.appendChild(emptyDiv);
            return;
        }
        if (btnClearHistory) btnClearHistory.style.display = 'inline-block';
        items.forEach(item => {
            const div = document.createElement('div');
            div.className = 'history-item';
            div.dataset.url = item.url;
            
            const isVideo = item.analysis.type === 'video';
            const tagClass = isVideo ? 'tag-video' : 'tag-space';
            const tagText = isVideo ? 'video' : 'space';
            
            const wrapper = document.createElement('div');
            wrapper.style.display = 'flex';
            wrapper.style.alignItems = 'center';
            wrapper.style.overflow = 'hidden';
            wrapper.style.flex = '1';

            const tagSpan = document.createElement('span');
            tagSpan.className = `history-tag ${tagClass}`;
            tagSpan.textContent = tagText;

            const urlSpan = document.createElement('span');
            urlSpan.className = 'url-text';
            urlSpan.title = item.url;
            urlSpan.textContent = item.url;

            wrapper.appendChild(tagSpan);
            wrapper.appendChild(urlSpan);

            const removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'btn-remove-history';
            removeBtn.dataset.url = item.url;
            removeBtn.textContent = '×';
            
            div.appendChild(wrapper);
            div.appendChild(removeBtn);
            historyList.appendChild(div);
        });
    }
}

function saveToHistory(url, data) {
    let items = getHistoryItems();
    items = items.filter(item => item.url !== url);
    items.unshift({
        url: url,
        timestamp: Date.now(),
        analysis: data
    });
    if (items.length > 10) {
        items = items.slice(0, 10);
    }
    localStorage.setItem('bilibili_downloader_history', JSON.stringify(items));
    loadHistory();
}

function clearAllHistory() {
    if (confirm("Xóa toàn bộ lịch sử tìm kiếm?")) {
        localStorage.removeItem('bilibili_downloader_history');
        loadHistory();
    }
}

function removeFromHistory(url) {
    let items = getHistoryItems();
    items = items.filter(item => item.url !== url);
    localStorage.setItem('bilibili_downloader_history', JSON.stringify(items));
    loadHistory();
}

function displayAnalysisResult(data) {
    analysisBox.style.display = 'block';
    analysisSummary.innerHTML = ''; // safe to clear
    
    if (data.type === 'video') {
        analysisTitle.textContent = "KẾT QUẢ PHÂN TÍCH: VIDEO";
        
        const titleDiv = document.createElement('div');
        titleDiv.textContent = `TIÊU ĐỀ: ${data.title}`;
        const uploaderDiv = document.createElement('div');
        uploaderDiv.textContent = `KÊNH: ${data.uploader}`;
        
        analysisSummary.appendChild(titleDiv);
        analysisSummary.appendChild(uploaderDiv);

        qualitySelectorGroup.style.display = 'block';
        spacePagesGroup.style.display = 'none';

        qualitySelect.innerHTML = '';
        data.qualities.forEach(q => {
            const opt = document.createElement('option');
            opt.value = q.value;
            opt.textContent = q.label;
            qualitySelect.appendChild(opt);
        });
    } else if (data.type === 'space') {
        analysisTitle.textContent = "KẾT QUẢ PHÂN TÍCH: SPACE PROFILE";
        
        const titleDiv = document.createElement('div');
        titleDiv.textContent = `KÊNH/PROFILE: ${data.title}`;
        const totalDiv = document.createElement('div');
        totalDiv.textContent = `TỔNG VIDEO: ${data.total_videos} videos (${data.total_pages} trang)`;
        
        analysisSummary.appendChild(titleDiv);
        analysisSummary.appendChild(totalDiv);

        qualitySelectorGroup.style.display = 'none';
        spacePagesGroup.style.display = 'block';
        pageStart.max = data.total_pages;
        pageEnd.max = data.total_pages;
        pageEnd.value = data.total_pages;
    }
}

function restoreFromHistory(url) {
    const items = getHistoryItems();
    const item = items.find(i => i.url === url);
    if (!item) return;
    
    document.getElementById('url').value = url;
    currentAnalyzedUrl = url;
    currentAnalyzedType = item.analysis.type;
    currentWorkingBrowser = item.analysis.working_browser;
    displayAnalysisResult(item.analysis);
}

// Search and analyze URL handler
btnAnalyze.addEventListener('click', async () => {
    const url = document.getElementById('url').value;
    if (!url) {
        alert("Vui lòng nhập đường dẫn video!");
        return;
    }

    btnAnalyze.textContent = "Đang tìm kiếm...";
    btnAnalyze.disabled = true;
    analysisBox.style.display = 'none';

    try {
        const res = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url: url,
                cookies_browser: null
            })
        });

        if (res.ok) {
            const data = await res.json();
            currentAnalyzedUrl = url;
            currentAnalyzedType = data.type;
            currentWorkingBrowser = data.working_browser;

            displayAnalysisResult(data);
            saveToHistory(url, data);
        } else {
            const err = await res.json();
            alert("Lỗi: " + err.detail);
        }
    } catch (e) {
        alert("Lỗi kết nối server.");
    } finally {
        btnAnalyze.textContent = "Tìm kiếm";
        btnAnalyze.disabled = false;
    }
});

// Trigger download handler
btnDownload.addEventListener('click', async () => {
    const targetPath = customOutputDir.dataset.fullPath || customOutputDir.value.trim() || null;
    const reqBody = {
        url: currentAnalyzedUrl,
        cookies_browser: currentWorkingBrowser,
        output_dir: targetPath
    };

    if (currentAnalyzedType === 'video') {
        reqBody.quality = qualitySelect.value;
    } else if (currentAnalyzedType === 'space') {
        reqBody.page_start = parseInt(pageStart.value);
        reqBody.page_end = parseInt(pageEnd.value);
        const maxV = parseInt(document.getElementById('max-videos').value);
        if (maxV && maxV > 0) {
            reqBody.max_videos = maxV;
        }
    }

    try {
        const res = await fetch('/api/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(reqBody)
        });

        if (res.ok) {
            triggerPolling();
        } else {
            alert("Lỗi tạo tiến trình.");
        }
    } catch (e) {
        alert("Không thể gửi lệnh tải.");
    }
});

function copyLogs() {
    const lines = Array.from(document.querySelectorAll('.terminal-line')).map(el => el.textContent);
    if (lines.length === 0) {
        alert("Nhật ký trống.");
        return;
    }
    navigator.clipboard.writeText(lines.join('\n')).then(() => {
        alert("Đã sao chép toàn bộ nhật ký hệ thống!");
    }).catch(err => {
        alert("Lỗi sao chép nhật ký: " + err);
    });
}

async function clearQueue() {
    try {
        await fetch('/api/tasks/clear', { method: 'POST' });
        triggerPolling();
    } catch (e) {
        console.error("Lỗi xóa hàng chờ:", e);
    }
}

async function cancelTask(taskId) {
    if (!confirm("Hủy tiến trình tải này?")) return;
    try {
        await fetch(`/api/tasks/${taskId}/cancel`, { method: 'POST' });
        triggerPolling();
    } catch (e) {
        console.error(e);
    }
}

async function openFolder(taskId) {
    try {
        const res = await fetch(`/api/tasks/${taskId}/open-folder`, { method: 'POST' });
        if (!res.ok) {
            const err = await res.json();
            alert("Không thể mở thư mục: " + (err.detail || err.message));
        }
    } catch (e) {
        alert("Lỗi mở thư mục: " + e);
    }
}

// Copy error message details
function copyErrorText(btn, taskId) {
    const task = allTasks.find(t => t.id === taskId);
    if (task && task.error) {
        const cleanMsg = task.error.replace(/\u001b\[[0-9;]*m/g, "");
        navigator.clipboard.writeText(cleanMsg).then(() => {
            const originalText = btn.textContent;
            btn.textContent = "đã sao chép";
            setTimeout(() => { btn.textContent = originalText; }, 1500);
        }).catch(err => {
            alert("Không thể sao chép: " + err);
        });
    }
}

// Refresh tasks list
async function updateTasks() {
    try {
        const res = await fetch('/api/tasks');
        const tasks = await res.json();
        allTasks = tasks;

        let waitingCount = 0;
        let doneCount = 0;
        let runningCount = 0;
        let errorCount = 0;
        let totalTime = 0;

        tasks.forEach(t => {
            if (t.status === 'pending') waitingCount++;
            else if (t.status === 'completed') doneCount++;
            else if (t.status === 'downloading' || t.status === 'merging') runningCount++;
            else if (t.status === 'failed') errorCount++;

            totalTime += t.elapsed_time || 0;
        });

        document.getElementById('stat-waiting').textContent = waitingCount;
        document.getElementById('stat-done').textContent = doneCount;
        document.getElementById('stat-running').textContent = runningCount;
        document.getElementById('stat-error').textContent = errorCount;
        document.getElementById('queue-total-time').textContent = Math.round(totalTime) + 's';

        if (tasks.length > 0) {
            queueEmptyMsg.style.display = 'none';
        } else {
            queueEmptyMsg.style.display = 'block';
            tasksContainer.innerHTML = '';
            tasksContainer.appendChild(queueEmptyMsg);
            return;
        }

        tasksContainer.innerHTML = '';
        tasksContainer.appendChild(queueEmptyMsg);

        tasks.forEach(task => {
            const card = document.createElement('div');
            card.className = 'task-card';

            const title = task.filename || task.url;

            let statusLabel = task.status;
            if (task.status === 'merging') statusLabel = 'merging';
            else if (task.status === 'downloading') statusLabel = 'downloading';
            else if (task.status === 'completed') statusLabel = 'completed';
            else if (task.status === 'pending') statusLabel = 'pending';
            else if (task.status === 'failed') statusLabel = 'failed';
            else if (task.status === 'canceled') statusLabel = 'canceled';

            let actionsHtml = '';
            if (task.status === 'downloading' || task.status === 'pending') {
                actionsHtml = `<button class="btn-small-cancel" data-action="cancel" data-task-id="${task.id}">hủy</button>`;
            } else if (task.status === 'failed') {
                actionsHtml = `<button class="btn-small-copy" data-action="copy-error" data-task-id="${task.id}">sao chép lỗi</button>`;
            } else if (task.status === 'completed') {
                actionsHtml = `<button class="btn-small-folder" data-action="open-folder" data-task-id="${task.id}">mở thư mục</button>`;
            }

            const cleanError = task.error ? task.error.replace(/\u001b\[[0-9;]*m/g, "") : "";

            let metaInfo = '';
            if (task.status === 'failed') {
                metaInfo = `
                    <div>${statusLabel}, ${task.progress}%, ${task.elapsed_time}s</div>
                    <div style="width: 100%; color: #dc2626; font-size: 0.68rem; margin-top: 6px; word-break: break-all; white-space: normal; line-height: 1.35;">lỗi: ${cleanError}</div>
                `;
            } else {
                metaInfo = `<div>${statusLabel}, ${task.progress}%, ${task.elapsed_time}s</div>`;
            }

            card.innerHTML = `
                <div class="task-card-header">
                    <div class="task-title" title="${title}">${title}</div>
                    <div style="display: flex; gap: 8px; align-items: center;">
                        ${actionsHtml}
                        <span class="status-badge status-${task.status}">${statusLabel}</span>
                    </div>
                </div>
                <div class="progress-track">
                    <div class="progress-bar" style="width: ${task.progress}%"></div>
                </div>
                <div class="task-meta">
                    ${metaInfo}
                </div>
            `;
            tasksContainer.appendChild(card);
        });
    } catch (err) {
        console.error("Lỗi cập nhật hàng chờ:", err);
    }
}

async function clearLogs() {
    try {
        await fetch('/api/logs/clear', { method: 'POST' });
        terminalBody.innerHTML = '<div class="terminal-line" style="color: var(--text-muted);">[LOG] Đã xóa toàn bộ nhật ký.</div>';
    } catch (err) {
        console.error("Lỗi xóa log:", err);
    }
}

// Refresh system logs
async function updateLogs() {
    try {
        const res = await fetch('/api/logs');
        const logs = await res.json();

        const wasAtBottom = !userIsScrolledUp;

        terminalBody.innerHTML = '';
        if (!logs || logs.length === 0) {
            terminalBody.innerHTML = '<div class="terminal-line" style="color: var(--text-muted);">[LOG] Hệ thống đang sẵn sàng...</div>';
            return;
        }

        logs.forEach(item => {
            const div = document.createElement('div');
            div.className = 'terminal-line';

            let color = '#38bdf8';
            if (item.level === 'SUCCESS') color = '#4ade80';
            else if (item.level === 'WARNING') color = '#facc15';
            else if (item.level === 'ERROR') color = '#f87171';

            if (typeof item === 'object' && item.time && item.message) {
                div.innerHTML = `<span style="color: #64748b;">[${item.time}]</span> <span style="color: ${color}; font-weight: 700;">[${item.level}]</span> ${item.message}`;
            } else {
                div.textContent = typeof item === 'string' ? item : JSON.stringify(item);
            }
            terminalBody.appendChild(div);
        });

        if (wasAtBottom) {
            terminalBody.scrollTop = terminalBody.scrollHeight;
        }
    } catch (err) {
        console.error("Lỗi cập nhật log:", err);
    }
}

// Bind static buttons
if (btnClearQueue) btnClearQueue.addEventListener('click', clearQueue);
if (btnClearLogs) btnClearLogs.addEventListener('click', clearLogs);
if (btnCopyLogs) btnCopyLogs.addEventListener('click', copyLogs);
if (btnClearHistory) btnClearHistory.addEventListener('click', clearAllHistory);
if (btnSelectProxy) {
    btnSelectProxy.addEventListener('click', async () => {
        btnSelectProxy.disabled = true;
        try {
            const res = await fetch('/api/select-proxy-file', { method: 'POST' });
            if (res.ok) {
                const data = await res.json();
                if (data.status === 'success' && data.path) {
                    await checkSystem();
                }
            } else {
                let errMsg = "Lỗi không xác định";
                try {
                    const err = await res.json();
                    errMsg = err.message || err.detail || JSON.stringify(err);
                } catch (e) {
                    errMsg = await res.text();
                }
                alert("Không thể chọn file proxy: " + errMsg);
            }
        } catch (e) {
            alert("Lỗi kết nối hộp thoại chọn file proxy.");
        } finally {
            btnSelectProxy.disabled = false;
        }
    });
}

if (btnClearProxy) {
    btnClearProxy.addEventListener('click', async () => {
        btnClearProxy.disabled = true;
        try {
            const res = await fetch('/api/proxy-file/clear', { method: 'POST' });
            if (res.ok) {
                await checkSystem();
            } else {
                alert("Không thể xóa proxy cá nhân.");
            }
        } catch (e) {
            alert("Lỗi kết nối xóa proxy cá nhân.");
        } finally {
            btnClearProxy.disabled = false;
        }
    });
}

if (btnSelectVideo) {
    btnSelectVideo.addEventListener('click', async () => {
        btnSelectVideo.disabled = true;
        try {
            const res = await fetch('/api/select-video-file', { method: 'POST' });
            if (res.ok) {
                const data = await res.json();
                if (data.status === 'success' && data.path) {
                    const videoInput = document.getElementById('subtitle-video-path');
                    if (videoInput) {
                        videoInput.value = data.path;
                        videoInput.title = data.path;
                    }
                    setSubtitleStatus("Đã chọn video thành công", "success");
                }
            } else {
                let errMsg = "Lỗi không xác định";
                try {
                    const err = await res.json();
                    errMsg = err.message || err.detail || JSON.stringify(err);
                } catch (e) {
                    errMsg = await res.text();
                }
                alert("Không thể chọn file video: " + errMsg);
            }
        } catch (e) {
            alert("Lỗi kết nối hộp thoại chọn file video.");
        } finally {
            btnSelectVideo.disabled = false;
        }
    });
}


// Event delegation for history items
if (historyList) {
    historyList.addEventListener('click', (event) => {
        const removeBtn = event.target.closest('.btn-remove-history');
        if (removeBtn) {
            event.stopPropagation();
            const urlToRemove = removeBtn.dataset.url;
            removeFromHistory(urlToRemove);
            return;
        }
        const itemRow = event.target.closest('.history-item');
        if (itemRow) {
            const urlToRestore = itemRow.dataset.url;
            restoreFromHistory(urlToRestore);
        }
    });
}

// Event delegation for dynamic task action buttons
tasksContainer.addEventListener('click', (event) => {
    const actionBtn = event.target.closest('[data-action]');
    if (!actionBtn) return;

    const action = actionBtn.dataset.action;
    const taskId = actionBtn.dataset.taskId;
    if (!taskId) return;

    if (action === 'cancel') {
        cancelTask(taskId);
    } else if (action === 'copy-error') {
        copyErrorText(actionBtn, taskId);
    } else if (action === 'open-folder') {
        openFolder(taskId);
    }
});

// App initiation
let pollingTimeoutId = null;
let lastActionTime = 0;

function triggerPolling() {
    lastActionTime = Date.now();
    if (!pollingTimeoutId) {
        poll();
    }
}

async function poll() {
    let hasActive = false;
    try {
        await updateTasks();
        await updateLogs();
        
        const activeStatuses = ['pending', 'downloading', 'merging', 'processing'];
        hasActive = allTasks.some(t => activeStatuses.includes(t.status));
    } catch (e) {
        console.error("Lỗi trong quá trình adaptive polling:", e);
    }

    const timeSinceLastAction = Date.now() - lastActionTime;
    if (hasActive || timeSinceLastAction < 5000) {
        pollingTimeoutId = setTimeout(poll, 1500);
    } else {
        pollingTimeoutId = null;
    }
}

(async () => {
    try {
        await checkSystem();
        loadHistory();
        await updateTasks();
        await updateLogs();
        
        const activeStatuses = ['pending', 'downloading', 'merging', 'processing'];
        const hasActive = allTasks.some(t => activeStatuses.includes(t.status));
        if (hasActive) {
            triggerPolling();
        }
    } catch (e) {
        console.error("Lỗi khởi tạo ứng dụng:", e);
    }
})();

// Mode Switch logic
const btnModeDownload = document.getElementById('btn-mode-download');
const btnModeSubtitle = document.getElementById('btn-mode-subtitle');
const downloaderView = document.getElementById('downloader-view');
const subtitleView = document.getElementById('subtitle-view');

if (btnModeDownload && btnModeSubtitle && downloaderView && subtitleView) {
    btnModeDownload.addEventListener('click', () => {
        btnModeDownload.classList.add('active');
        btnModeSubtitle.classList.remove('active');
        downloaderView.style.display = 'grid';
        subtitleView.style.display = 'none';
    });

    btnModeSubtitle.addEventListener('click', () => {
        btnModeSubtitle.classList.add('active');
        btnModeDownload.classList.remove('active');
        downloaderView.style.display = 'none';
        subtitleView.style.display = 'grid';
    });
}

// Subtitle Helper Functions
function formatMsForSubtitle(ms) {
    if (ms < 0) ms = 0;
    const hours = Math.floor(ms / 3600000);
    ms %= 3600000;
    const minutes = Math.floor(ms / 60000);
    ms %= 60000;
    const seconds = Math.floor(ms / 1000);
    const milliseconds = ms % 1000;
    return (
        String(hours).padStart(2, '0') + ':' +
        String(minutes).padStart(2, '0') + ':' +
        String(seconds).padStart(2, '0') + ',' +
        String(milliseconds).padStart(3, '0')
    );
}

function computeGapLabel(prev, current) {
    if (!prev) return 'N/A';
    const gap = current.start_ms - prev.end_ms;
    return gap + 'ms';
}

function setSubtitleStatus(text, type = 'info') {
    const statusEl = document.getElementById('subtitle-status');
    if (!statusEl) return;
    statusEl.textContent = `Trạng thái: ${text}`;
    if (type === 'error') {
        statusEl.style.color = '#ef4444';
    } else if (type === 'success') {
        statusEl.style.color = '#16a34a';
    } else if (type === 'loading') {
        statusEl.style.color = '#ca8a04';
    } else {
        statusEl.style.color = 'var(--text-muted)';
    }
}

function updateSubtitleButtons() {
    const mergeBtn = document.getElementById('btn-subtitle-merge');
    const splitBtn = document.getElementById('btn-subtitle-split');
    const exportBtn = document.getElementById('btn-subtitle-export');
    
    const checkedCount = document.querySelectorAll('.subtitle-row-checkbox:checked').length;
    const totalCount = currentSubtitleSegments.length;
    
    if (mergeBtn) {
        mergeBtn.disabled = checkedCount < 2;
    }
    if (splitBtn) {
        splitBtn.disabled = checkedCount !== 1;
    }
    if (exportBtn) {
        exportBtn.disabled = totalCount === 0;
    }
}

function getSelectedSubtitleIndices() {
    const checkboxes = document.querySelectorAll('.subtitle-row-checkbox:checked');
    return Array.from(checkboxes).map(cb => parseInt(cb.dataset.index, 10));
}

async function runSubtitleModule(params, statusText, timeoutMs = 60000) {
    setSubtitleStatus(statusText, 'loading');
    const response = await fetch('/api/modules/subtitle/run', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ params: params })
    });
    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
    }
    const runResult = await response.json();
    const taskId = runResult.task_id;
    
    triggerPolling();
    const task = await pollTask(taskId, 700, timeoutMs);
    return task;
}

function renderSubtitleTable(segments) {
    const tbody = document.getElementById('subtitle-table-body');
    const subtitleTable = document.querySelector('.subtitle-table');
    const subtitleEmptyState = document.getElementById('subtitle-empty-state');
    const selectAll = document.getElementById('subtitle-select-all');

    if (selectAll) {
        selectAll.checked = false;
    }

    if (!tbody) return;
    tbody.innerHTML = '';

    if (!segments || segments.length === 0) {
        if (subtitleTable) subtitleTable.style.display = 'none';
        if (subtitleEmptyState) subtitleEmptyState.style.display = 'block';
        updateSubtitleButtons();
        return;
    }

    if (subtitleTable) subtitleTable.style.display = 'table';
    if (subtitleEmptyState) subtitleEmptyState.style.display = 'none';

    segments.forEach((seg, idx) => {
        const tr = document.createElement('tr');

        // 1. Checkbox cell
        const tdCheck = document.createElement('td');
        tdCheck.style.textAlign = 'center';
        tdCheck.style.padding = '8px';
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'subtitle-row-checkbox';
        checkbox.dataset.index = idx;
        checkbox.style.cursor = 'pointer';
        checkbox.addEventListener('change', () => {
            updateSubtitleButtons();
            const allCheckboxes = document.querySelectorAll('.subtitle-row-checkbox');
            const checkedCheckboxes = document.querySelectorAll('.subtitle-row-checkbox:checked');
            if (selectAll) {
                selectAll.checked = allCheckboxes.length > 0 && allCheckboxes.length === checkedCheckboxes.length;
            }
        });
        tdCheck.appendChild(checkbox);
        tr.appendChild(tdCheck);

        // 2. Index cell
        const tdIndex = document.createElement('td');
        tdIndex.style.padding = '8px';
        tdIndex.textContent = seg.index;
        tr.appendChild(tdIndex);

        // 3. Start time cell
        const tdStart = document.createElement('td');
        tdStart.style.padding = '8px';
        tdStart.textContent = formatMsForSubtitle(seg.start_ms);
        tr.appendChild(tdStart);

        // 4. End time cell
        const tdEnd = document.createElement('td');
        tdEnd.style.padding = '8px';
        tdEnd.textContent = formatMsForSubtitle(seg.end_ms);
        tr.appendChild(tdEnd);

        // 5. Gap cell
        const tdGap = document.createElement('td');
        tdGap.style.padding = '8px';
        tdGap.textContent = computeGapLabel(segments[idx - 1], seg);
        tr.appendChild(tdGap);

        // 6. Text cell
        const tdText = document.createElement('td');
        tdText.style.padding = '8px';
        tdText.textContent = seg.text;
        tr.appendChild(tdText);

        // 7. Actions cell
        const tdActions = document.createElement('td');
        tdActions.style.padding = '8px';
        tdActions.style.textAlign = 'center';
        
        const editBtn = document.createElement('button');
        editBtn.type = 'button';
        editBtn.className = 'btn-row-edit';
        editBtn.textContent = 'Sửa';
        editBtn.addEventListener('click', async () => {
            const newText = prompt("Nhập nội dung phụ đề mới:", seg.text);
            if (newText === null) return;
            const trimmedText = newText.trim();
            if (!trimmedText) {
                alert("Nội dung không được để trống!");
                return;
            }
            
            try {
                const params = {
                    action: 'replace_text',
                    segments: currentSubtitleSegments,
                    index: seg.index,
                    text: trimmedText
                };
                const task = await runSubtitleModule(params, "Đang lưu thay đổi...");
                currentSubtitleSegments = task.metrics.segments;
                renderSubtitleTable(currentSubtitleSegments);
                setSubtitleStatus("Sửa nội dung thành công", "success");
            } catch (err) {
                console.error(err);
                alert("Sửa nội dung thất bại: " + err.message);
                setSubtitleStatus("Sửa nội dung thất bại: " + err.message, "error");
            }
        });
        tdActions.appendChild(editBtn);
        tr.appendChild(tdActions);

        tbody.appendChild(tr);
    });

    updateSubtitleButtons();
}

function exportSegmentsToSrtClient(segments) {
    return segments.map((seg, idx) => {
        const startTs = formatMsForSubtitle(seg.start_ms);
        const endTs = formatMsForSubtitle(seg.end_ms);
        return `${idx + 1}\n${startTs} --> ${endTs}\n${seg.text}`;
    }).join('\n\n') + '\n';
}

function pollTask(taskId, intervalMs = 700, timeoutMs = 60000) {
    const startTime = Date.now();
    return new Promise((resolve, reject) => {
        const timer = setInterval(async () => {
            if (Date.now() - startTime > timeoutMs) {
                clearInterval(timer);
                reject(new Error("Timeout waiting for task execution"));
                return;
            }

            try {
                const res = await fetch('/api/tasks');
                if (!res.ok) {
                    throw new Error(`HTTP error! status: ${res.status}`);
                }
                const tasks = await res.json();
                const task = tasks.find(t => t.task_id === taskId);

                if (!task) return;

                if (task.status === 'completed') {
                    clearInterval(timer);
                    resolve(task);
                } else if (task.status === 'failed') {
                    clearInterval(timer);
                    reject(new Error(task.error || "Task execution failed"));
                } else if (task.status === 'canceled') {
                    clearInterval(timer);
                    reject(new Error("Task execution was canceled"));
                }
            } catch (err) {
                console.error("Error polling task:", err);
            }
        }, intervalMs);
    });
}

// Event Listeners Wire-up
const selectAll = document.getElementById('subtitle-select-all');
if (selectAll) {
    selectAll.addEventListener('change', (e) => {
        const checked = e.target.checked;
        const checkboxes = document.querySelectorAll('.subtitle-row-checkbox');
        checkboxes.forEach(cb => {
            cb.checked = checked;
        });
        updateSubtitleButtons();
    });
}

const btnSubtitleExport = document.getElementById('btn-subtitle-export');
const btnSubtitleOpenSrtLocation = document.getElementById('btn-subtitle-open-srt-location');
let lastSavedSrtPath = "";

if (btnSubtitleExport) {
    btnSubtitleExport.addEventListener('click', async () => {
        if (currentSubtitleSegments.length === 0) return;
        
        const videoInput = document.getElementById('subtitle-video-path');
        const videoPath = videoInput ? videoInput.value.trim() : "";
        if (!videoPath) {
            alert("Vui lòng chọn file video trước khi xuất phụ đề SRT để lưu cùng thư mục.");
            return;
        }

        btnSubtitleExport.disabled = true;
        setSubtitleStatus("Đang xuất file SRT...", "loading");

        try {
            const srtContent = exportSegmentsToSrtClient(currentSubtitleSegments);
            const res = await fetch('/api/subtitle/save-srt', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    video_path: videoPath,
                    content: srtContent
                })
            });

            if (res.ok) {
                const data = await res.json();
                if (data.status === 'success' && data.path) {
                    lastSavedSrtPath = data.path;
                    setSubtitleStatus("Đã xuất file SRT thành công", "success");
                    alert("Đã xuất file phụ đề SRT bên cạnh file video:\n" + data.path);
                    if (btnSubtitleOpenSrtLocation) {
                        btnSubtitleOpenSrtLocation.disabled = false;
                        btnSubtitleOpenSrtLocation.title = "Mở vị trí file SRT";
                    }
                } else {
                    throw new Error(data.message || "Lỗi lưu file");
                }
            } else {
                let errMsg = "Lỗi phản hồi từ server";
                try {
                    const err = await res.json();
                    errMsg = err.message || err.detail || JSON.stringify(err);
                } catch (e) {}
                throw new Error(errMsg);
            }
        } catch (e) {
            alert("Lỗi xuất file SRT: " + e.message);
            setSubtitleStatus("Lỗi xuất file SRT", "error");
        } finally {
            btnSubtitleExport.disabled = false;
        }
    });
}

if (btnSubtitleOpenSrtLocation) {
    btnSubtitleOpenSrtLocation.addEventListener('click', async () => {
        if (!lastSavedSrtPath) {
            alert("Chưa có file SRT đã xuất.");
            return;
        }
        btnSubtitleOpenSrtLocation.disabled = true;
        try {
            const res = await fetch('/api/subtitle/open-file-location', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: lastSavedSrtPath })
            });
            if (!res.ok) {
                let errMsg = "Lỗi phản hồi từ server";
                try {
                    const err = await res.json();
                    errMsg = err.message || err.detail || JSON.stringify(err);
                } catch (e) {}
                alert("Không thể mở vị trí tệp: " + errMsg);
            }
        } catch (e) {
            alert("Lỗi kết nối mở vị trí tệp: " + e.message);
        } finally {
            btnSubtitleOpenSrtLocation.disabled = false;
        }
    });
}

async function parseSubtitleSrtText(srtText, sourceName = "thủ công") {
    if (!srtText.trim()) {
        alert("Nội dung SRT trống!");
        setSubtitleStatus("Nội dung SRT trống", "error");
        return;
    }

    setSubtitleStatus("Đang nạp phụ đề SRT...", "loading");

    const parseBtn = document.getElementById('btn-subtitle-parse-srt');
    const importBtn = document.getElementById('btn-subtitle-import-srt-file');
    if (parseBtn) parseBtn.disabled = true;
    if (importBtn) importBtn.disabled = true;

    try {
        const params = {
            action: 'parse_srt',
            srt_text: srtText
        };
        const task = await runSubtitleModule(params, "Đang nạp phụ đề SRT...");
        const segments = task.metrics.segments || [];

        currentSubtitleSegments = segments;
        renderSubtitleTable(currentSubtitleSegments);
        setSubtitleStatus(`Đã nạp phụ đề từ ${sourceName} thành công (${segments.length} dòng)`, "success");
    } catch (err) {
        console.error(err);
        setSubtitleStatus(err.message || "Có lỗi xảy ra khi nạp phụ đề", "error");
        alert("Lỗi nạp phụ đề: " + err.message);
    } finally {
        if (parseBtn) parseBtn.disabled = false;
        if (importBtn) importBtn.disabled = false;
    }
}

const btnSubtitleParse = document.getElementById('btn-subtitle-parse-srt');
const subtitleSrtInput = document.getElementById('subtitle-srt-input');

if (btnSubtitleParse && subtitleSrtInput) {
    btnSubtitleParse.addEventListener('click', async () => {
        const srtText = subtitleSrtInput.value;
        await parseSubtitleSrtText(srtText, "thủ công");
    });
}

const btnSubtitleImportSrtFile = document.getElementById('btn-subtitle-import-srt-file');

if (btnSubtitleImportSrtFile) {
    btnSubtitleImportSrtFile.addEventListener('click', async () => {
        btnSubtitleImportSrtFile.disabled = true;
        try {
            const res = await fetch('/api/select-srt-file', { method: 'POST' });
            if (res.ok) {
                const data = await res.json();
                if (data.status === 'success' && data.path && data.content !== undefined) {
                    // Update display
                    const displayInput = document.getElementById('subtitle-srt-file-display');
                    if (displayInput) {
                        displayInput.value = data.path;
                        displayInput.title = data.path;
                    }
                    if (subtitleSrtInput) {
                        subtitleSrtInput.value = data.content;
                    }
                    // Parse text content automatically
                    await parseSubtitleSrtText(data.content, data.path);
                }
            } else {
                let errMsg = "Lỗi không xác định";
                try {
                    const err = await res.json();
                    errMsg = err.message || err.detail || JSON.stringify(err);
                } catch (e) {
                    errMsg = await res.text();
                }
                alert("Không thể chọn file SRT: " + errMsg);
            }
        } catch (e) {
            alert("Lỗi kết nối hộp thoại chọn file SRT: " + e.message);
        } finally {
            btnSubtitleImportSrtFile.disabled = false;
        }
    });
}

const btnSubtitleMerge = document.getElementById('btn-subtitle-merge');
if (btnSubtitleMerge) {
    btnSubtitleMerge.addEventListener('click', async () => {
        const indices = getSelectedSubtitleIndices();
        if (indices.length < 2) return;

        // Check if indices are consecutive
        indices.sort((a, b) => a - b);
        for (let i = 1; i < indices.length; i++) {
            if (indices[i] !== indices[i - 1] + 1) {
                alert("Chỉ có thể gộp các dòng phụ đề liên tiếp nhau!");
                return;
            }
        }

        const startIndex = currentSubtitleSegments[indices[0]].index;
        const endIndex = currentSubtitleSegments[indices[indices.length - 1]].index;

        const params = {
            action: 'merge',
            segments: currentSubtitleSegments,
            start_index: startIndex,
            end_index: endIndex,
            max_gap_ms: 300,
            max_duration_ms: 6000,
            max_chars: 120,
            allow_large_gap: false
        };

        try {
            const task = await runSubtitleModule(params, "Đang gộp phụ đề...");
            currentSubtitleSegments = task.metrics.segments;
            renderSubtitleTable(currentSubtitleSegments);
            setSubtitleStatus("Gộp dòng thành công", "success");
        } catch (err) {
            if (err.message.includes('gap') || err.message.includes('max_gap_ms')) {
                const confirmOverride = confirm("Khoảng cách giữa các dòng vượt quá giới hạn (max_gap_ms). Bạn có muốn gộp và bỏ qua giới hạn khoảng cách không?");
                if (confirmOverride) {
                    params.allow_large_gap = true;
                    try {
                        const task = await runSubtitleModule(params, "Đang gộp phụ đề (bỏ qua giới hạn khoảng cách)...");
                        currentSubtitleSegments = task.metrics.segments;
                        renderSubtitleTable(currentSubtitleSegments);
                        setSubtitleStatus("Gộp dòng thành công", "success");
                    } catch (retryErr) {
                        console.error(retryErr);
                        alert("Gộp dòng thất bại: " + retryErr.message);
                        setSubtitleStatus("Gộp dòng thất bại: " + retryErr.message, "error");
                    }
                } else {
                    setSubtitleStatus("Gộp dòng bị hủy bởi người dùng", "info");
                }
            } else {
                console.error(err);
                alert("Gộp dòng thất bại: " + err.message);
                setSubtitleStatus("Gộp dòng thất bại: " + err.message, "error");
            }
        }
    });
}

const btnSubtitleSplit = document.getElementById('btn-subtitle-split');
if (btnSubtitleSplit) {
    btnSubtitleSplit.addEventListener('click', async () => {
        const indices = getSelectedSubtitleIndices();
        if (indices.length !== 1) return;

        const idx = indices[0];
        const seg = currentSubtitleSegments[idx];

        const defaultSplit = Math.floor((seg.start_ms + seg.end_ms) / 2);
        const splitAt = prompt(
            `Nhập thời điểm tách (ms) (phải nằm trong khoảng từ ${seg.start_ms} đến ${seg.end_ms}):`,
            defaultSplit
        );
        if (splitAt === null) return;

        const splitAtMs = parseInt(splitAt, 10);
        if (isNaN(splitAtMs)) {
            alert("Vui lòng nhập một số nguyên hợp lệ!");
            return;
        }

        if (splitAtMs <= seg.start_ms || splitAtMs >= seg.end_ms) {
            alert(`Thời điểm tách phải lớn hơn ${seg.start_ms}ms và nhỏ hơn ${seg.end_ms}ms!`);
            return;
        }

        const firstText = prompt("Nhập nội dung cho phần phụ đề đầu:", seg.text);
        if (firstText === null) return;
        if (!firstText.trim()) {
            alert("Nội dung không được để trống!");
            return;
        }

        const secondText = prompt("Nhập nội dung cho phần phụ đề sau:", "");
        if (secondText === null) return;
        if (!secondText.trim()) {
            alert("Nội dung không được để trống!");
            return;
        }

        const params = {
            action: 'split',
            segments: currentSubtitleSegments,
            index: seg.index,
            split_at_ms: splitAtMs,
            first_text: firstText.trim(),
            second_text: secondText.trim()
        };

        try {
            const task = await runSubtitleModule(params, "Đang tách dòng...");
            currentSubtitleSegments = task.metrics.segments;
            renderSubtitleTable(currentSubtitleSegments);
            setSubtitleStatus("Tách dòng thành công", "success");
        } catch (err) {
            console.error(err);
            alert("Tách dòng thất bại: " + err.message);
            setSubtitleStatus("Tách dòng thất bại: " + err.message, "error");
        }
    });
}

const btnSubtitleGenerate = document.getElementById('btn-subtitle-generate');
const subtitleVideoPath = document.getElementById('subtitle-video-path');
const subtitleModel = document.getElementById('subtitle-model');
const subtitleLanguage = document.getElementById('subtitle-language');

if (btnSubtitleGenerate && subtitleVideoPath) {
    btnSubtitleGenerate.addEventListener('click', async () => {
        const methodSelect = document.getElementById('subtitle-method');
        const methodVal = methodSelect ? methodSelect.value : 'whisper';

        if (methodVal !== 'whisper') {
            alert("Phương thức OCR chưa được hỗ trợ!");
            setSubtitleStatus("Phương thức OCR chưa được hỗ trợ", "error");
            return;
        }

        const videoPath = subtitleVideoPath.value.trim();
        if (!videoPath) {
            alert("Vui lòng chọn file video!");
            setSubtitleStatus("Vui lòng chọn file video", "error");
            return;
        }

        const modelVal = subtitleModel ? subtitleModel.value : 'base';
        const taskVal = 'transcribe';

        const languageVal = subtitleLanguage ? subtitleLanguage.value : '';

        const params = {
            action: 'generate_whisper',
            video_path: videoPath,
            model: modelVal,
            task: taskVal
        };
        if (languageVal) {
            params.language = languageVal;
        }

        btnSubtitleGenerate.disabled = true;

        try {
            // 30 minutes timeout = 1800000ms
            const task = await runSubtitleModule(params, "Đang tạo phụ đề bằng Whisper (có thể mất vài phút)...", 1800000);
            const segments = task.metrics.segments || [];

            currentSubtitleSegments = segments;
            renderSubtitleTable(currentSubtitleSegments);

            const srtInput = document.getElementById('subtitle-srt-input');
            if (srtInput && task.metrics.srt_text) {
                srtInput.value = task.metrics.srt_text;
            }

            setSubtitleStatus(`Tạo phụ đề thành công (${segments.length} dòng)`, "success");
        } catch (err) {
            console.error(err);
            setSubtitleStatus(err.message || "Tạo phụ đề thất bại", "error");
            if (err.message.includes('openai-whisper') || err.message.includes('whisper')) {
                alert("Lỗi: Gói 'openai-whisper' chưa được cài đặt trên hệ thống. Vui lòng cài đặt thông qua requirements-whisper.txt!");
            } else {
                alert("Tạo phụ đề thất bại: " + err.message);
            }
        } finally {
            btnSubtitleGenerate.disabled = false;
        }
    });
}


