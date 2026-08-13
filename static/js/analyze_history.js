import { state } from './state.js';
import * as api from './api.js';
import { triggerLogPolling, setIsAnalyzing } from './polling.js';
import { truncatePath } from './helpers.js?v=2';

const btnAnalyze = document.getElementById('btn-analyze');
const analysisBox = document.getElementById('analysis-box');
const analysisTitle = document.getElementById('analysis-title');
const analysisSummary = document.getElementById('analysis-summary');
const qualitySelectorGroup = document.getElementById('quality-selector-group');
const qualitySelect = document.getElementById('quality-select');
const spacePagesGroup = document.getElementById('space-pages-group');
const pageStart = document.getElementById('page-start');
const pageEnd = document.getElementById('page-end');
const historyList = document.getElementById('history-list');
const btnClearHistory = document.getElementById('btn-clear-history');

// Callback to trigger final logs UI update in analyze finally block without circular import
let finalLogsUpdateCallback = null;

export function registerFinalLogsUpdate(cb) {
    finalLogsUpdateCallback = cb;
}

export function getHistoryItems() {
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

export function loadHistory() {
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
            
            const tagSpan = document.createElement('span');
            tagSpan.className = `history-tag ${tagClass}`;
            tagSpan.textContent = tagText;

            const urlSpan = document.createElement('span');
            urlSpan.className = 'display-url';
            urlSpan.title = item.url;
            urlSpan.textContent = item.url;

            const removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'btn-remove-history';
            removeBtn.dataset.url = item.url;
            removeBtn.textContent = '×';
            
            div.appendChild(tagSpan);
            div.appendChild(urlSpan);
            div.appendChild(removeBtn);
            historyList.appendChild(div);
        });
    }
}

export function saveToHistory(url, data) {
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

export function clearAllHistory() {
    if (confirm("Xóa toàn bộ lịch sử tìm kiếm?")) {
        localStorage.removeItem('bilibili_downloader_history');
        loadHistory();
    }
}

export function removeFromHistory(url) {
    let items = getHistoryItems();
    items = items.filter(item => item.url !== url);
    localStorage.setItem('bilibili_downloader_history', JSON.stringify(items));
    loadHistory();
}

export function displayAnalysisResult(data) {
    analysisBox.style.display = 'block';
    analysisSummary.innerHTML = '';
    
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

export function restoreFromHistory(url) {
    const items = getHistoryItems();
    const item = items.find(i => i.url === url);
    if (!item) return;
    
    document.getElementById('url').value = url;
    state.currentAnalyzedUrl = url;
    state.currentAnalyzedType = item.analysis.type;
    state.currentWorkingBrowser = item.analysis.working_browser;
    displayAnalysisResult(item.analysis);
}

export function initAnalyzeHistory() {
    if (btnAnalyze) {
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
                setIsAnalyzing(true);
                triggerLogPolling();
                const res = await api.analyzeUrl(url);

                if (res.ok) {
                    const data = await res.json();
                    state.currentAnalyzedUrl = url;
                    state.currentAnalyzedType = data.type;
                    state.currentWorkingBrowser = data.working_browser;

                    displayAnalysisResult(data);
                    saveToHistory(url, data);
                } else {
                    const err = await res.json();
                    alert("Lỗi: " + err.detail);
                }
            } catch (e) {
                alert("Lỗi kết nối server.");
            } finally {
                setIsAnalyzing(false);
                if (finalLogsUpdateCallback) {
                    await finalLogsUpdateCallback();
                }
                btnAnalyze.textContent = "Tìm kiếm";
                btnAnalyze.disabled = false;
            }
        });
    }

    if (btnClearHistory) {
        btnClearHistory.addEventListener('click', clearAllHistory);
    }

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
}
