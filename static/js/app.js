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

function updateProxyDisplay(fullPath) {
    if (!fullPath) {
        customProxyFile.value = "Mặc định hệ thống...";
        customProxyFile.title = "";
        return;
    }
    customProxyFile.value = truncatePath(fullPath, 3);
    customProxyFile.title = fullPath;
}

async function checkSystem() {
    try {
        const res = await fetch('/api/system');
        const data = await res.json();
        updateDirDisplay(data.download_dir);
        updateProxyDisplay(data.proxy_file);
    } catch (err) {
        console.error("Lỗi quét hệ thống:", err);
    }
}

// OS directory selection click handler
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
            updateTasks();
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
        updateTasks();
        updateLogs();
    } catch (e) {
        console.error("Lỗi xóa hàng chờ:", e);
    }
}

async function cancelTask(taskId) {
    if (!confirm("Hủy tiến trình tải này?")) return;
    try {
        await fetch(`/api/tasks/${taskId}/cancel`, { method: 'POST' });
        updateTasks();
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
                    updateProxyDisplay(data.path);
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
checkSystem();
loadHistory();
setInterval(updateTasks, 1500);
setInterval(updateLogs, 2000);
