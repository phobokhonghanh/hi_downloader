import { truncatePath } from './helpers.js';
import * as api from './api.js';
import { JobQueue } from './job_queue.js';
import { openTranslateModal } from './translate_modal.js';

let selectedJobIds = new Set();
let pollingTimer = null;
let isPollingActive = false;
let translateQueueInstance = null;
let currentBatchId = null;

export function initTranslateQueue() {
    const container = document.getElementById('translate-queue-container');
    if (!container) return;

    translateQueueInstance = new JobQueue(container, {
        selectable: true,
        showSummaryInStatsBar: false,
        labels: {
            empty: "Chưa có hàng đợi dịch phụ đề nào hoạt động. Hãy chọn file SRT hoặc thư mục và nhấn \"Tạo bản dịch\".",
            total: "Tổng",
            waiting: "Chờ",
            running: "Đang chạy",
            done: "Hoàn thành",
            error: "Lỗi/Hủy",
            elapsed: "Thời gian chạy"
        },
        getRowId: row => row.job_id,
        normalizeStatus: row => {
            if (row.status === 'waiting') return 'waiting';
            if (row.status === 'running') return 'running';
            if (row.status === 'done') return 'done';
            return 'error';
        },
        columns: [
            {
                key: 'file',
                label: 'URL',
                width: '40%',
                render: row => {
                    const div = document.createElement('div');
                    div.style.fontWeight = '600';
                    div.textContent = truncatePath(row.source_path);
                    div.title = row.source_path;
                    return div;
                }
            },
            {
                key: 'progress',
                label: 'Trạng thái/Tiến trình',
                width: '45%',
                render: row => {
                    const container = document.createElement('div');
                    container.style.display = 'flex';
                    container.style.flexDirection = 'column';
                    container.style.gap = '4px';
                    container.style.width = '100%';

                    const track = document.createElement('div');
                    track.className = 'progress-track';
                    track.style.margin = '0';
                    
                    const bar = document.createElement('div');
                    bar.className = 'progress-bar';
                    
                    let pct = 0;
                    if (row.status === 'done') pct = 100;
                    else if (row.status === 'running') pct = Math.round(row.progress || 0);
                    else if (row.status === 'waiting') pct = 0;
                    
                    bar.style.width = `${pct}%`;
                    track.appendChild(bar);

                    const text = document.createElement('span');
                    text.style.fontSize = '0.68rem';
                    text.style.fontWeight = '600';
                    
                    let textLabel = row.status;
                    let statusColor = 'var(--text-muted)';
                    if (row.status === 'waiting') {
                        textLabel = 'Chờ';
                    } else if (row.status === 'running') {
                        let phaseLabel = row.phase || 'translating';
                        if (phaseLabel === 'preparing') phaseLabel = 'Chuẩn bị';
                        else if (phaseLabel === 'translating') phaseLabel = 'Đang dịch';
                        else if (phaseLabel === 'writing') phaseLabel = 'Đang ghi file';
                        textLabel = `${pct}% (${phaseLabel})`;
                        statusColor = '#ca8a04';
                    } else if (row.status === 'done') {
                        textLabel = '100% (Hoàn thành)';
                        statusColor = '#16a34a';
                    } else if (row.status === 'error') {
                        textLabel = `Lỗi: ${row.error || ''}`;
                        statusColor = '#dc2626';
                    } else if (row.status === 'canceled') {
                        textLabel = 'Đã hủy';
                        statusColor = '#ef4444';
                    }
                    text.style.color = statusColor;
                    text.textContent = textLabel;

                    container.appendChild(track);
                    container.appendChild(text);
                    return container;
                }
            },
            {
                key: 'actions',
                label: 'Thao tác',
                width: '15%',
                render: row => {
                    const container = document.createElement('div');
                    container.style.display = 'flex';
                    container.style.justifyContent = 'center';
                    container.style.gap = '8px';

                    // 1. Folder Button
                    const btnFolder = document.createElement('button');
                    btnFolder.type = 'button';
                    btnFolder.className = 'btn-row-action';
                    btnFolder.setAttribute('aria-label', 'Mở thư mục');
                    btnFolder.title = 'Mở thư mục';
                    btnFolder.innerHTML = `
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2z"></path>
                        </svg>
                    `;
                    if (row.status === 'done' && row.saved_path) {
                        btnFolder.disabled = false;
                        btnFolder.addEventListener('click', async (e) => {
                            e.stopPropagation();
                            btnFolder.disabled = true;
                            try {
                                const res = await api.openTranslateJobLocation(currentBatchId, row.job_id);
                                if (!res.ok) alert("Không thể mở vị trí tệp.");
                            } catch (err) {
                                alert("Lỗi kết nối: " + err.message);
                            } finally {
                                btnFolder.disabled = false;
                            }
                        });
                    } else {
                        btnFolder.disabled = true;
                    }

                    // 2. Eye Button
                    const btnEye = document.createElement('button');
                    btnEye.type = 'button';
                    btnEye.className = 'btn-row-action';
                    btnEye.setAttribute('aria-label', 'Xem chi tiết');
                    btnEye.title = 'Xem chi tiết';
                    btnEye.innerHTML = `
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"></path>
                            <circle cx="12" cy="12" r="3"></circle>
                        </svg>
                    `;
                    if (row.status === 'done') {
                        btnEye.disabled = false;
                        btnEye.addEventListener('click', (e) => {
                            e.stopPropagation();
                            openTranslateModal(currentBatchId, row.job_id);
                        });
                    } else {
                        btnEye.disabled = true;
                    }

                    container.appendChild(btnFolder);
                    container.appendChild(btnEye);
                    return container;
                }
            }
        ],
        selectionGroups: [
            { value: 'waiting', label: 'Chờ', matches: (r, norm) => norm === 'waiting' },
            { value: 'running', label: 'Đang chạy', matches: (r, norm) => norm === 'running' },
            { value: 'done', label: 'Hoàn thành', matches: (r, norm) => norm === 'done' },
            { value: 'error', label: 'Lỗi hoặc đã hủy', matches: (r, norm) => norm === 'error' }
        ],
        bulkActions: [
            { id: 'save', label: 'Lưu', eligible: r => r.status === 'done', onInvoke: (ids) => handleBatchAction('save', ids) },
            { id: 'cancel', label: 'Hủy', eligible: r => r.status === 'waiting' || r.status === 'running', onInvoke: (ids) => handleBatchAction('cancel', ids) },
            { id: 'retry', label: 'Dịch lại', eligible: r => r.status === 'error' || r.status === 'canceled', onInvoke: (ids) => handleBatchAction('retry', ids) }
        ],
        onRowClick: row => {
            if (row.status === 'done') {
                openTranslateModal(currentBatchId, row.job_id);
            }
        },
        onSelectionChange: ids => {
            selectedJobIds = new Set(ids);
        }
    });
    translateQueueInstance.update({ rows: [], elapsedSeconds: 0 });
}

export function startQueuePolling(batchId) {
    currentBatchId = batchId;
    if (pollingTimer) {
        clearTimeout(pollingTimer);
        pollingTimer = null;
    }
    isPollingActive = true;
    pollBatch(batchId);
}

export function stopQueuePolling() {
    isPollingActive = false;
    if (pollingTimer) {
        clearTimeout(pollingTimer);
        pollingTimer = null;
    }
}

async function pollBatch(batchId) {
    if (!isPollingActive || currentBatchId !== batchId) {
        return;
    }

    try {
        const res = await api.getTranslateBatch(batchId);
        if (res.ok) {
            const snapshot = await res.json();
            renderQueueTable(snapshot);

            const jobs = snapshot.jobs || [];
            const hasActiveJobs = jobs.some(j => j.status === 'waiting' || j.status === 'running');
            
            if (hasActiveJobs) {
                pollingTimer = setTimeout(() => pollBatch(batchId), 2000);
            } else {
                isPollingActive = false;
            }
        } else {
            isPollingActive = false;
        }
    } catch (err) {
        console.error("Lỗi polling hàng đợi dịch thuật:", err);
        pollingTimer = setTimeout(() => pollBatch(batchId), 5000);
    }
}

export function renderQueueTable(snapshot) {
    if (!snapshot || !translateQueueInstance) return;

    const elapsed = Math.round(snapshot.total_duration || 0);

    const jobs = snapshot.jobs || [];
    translateQueueInstance.update({
        rows: jobs,
        elapsedSeconds: elapsed
    });
}

async function handleBatchAction(action, selectedIds) {
    if (!currentBatchId) {
        alert("Không có thông tin lô dịch phụ đề hiện tại.");
        return;
    }

    const jobIdsArray = selectedIds || Array.from(selectedJobIds);
    if (jobIdsArray.length === 0) {
        alert("Vui lòng chọn ít nhất một tác vụ.");
        return;
    }

    try {
        const res = await api.dispatchTranslateBatchAction(currentBatchId, action, jobIdsArray);
        if (res.ok) {
            if (translateQueueInstance) {
                translateQueueInstance.selectedRowIds.clear();
                selectedJobIds.clear();
            }
            await refreshBatchSnapshot();
            if (action === 'retry') {
                startQueuePolling(currentBatchId);
            }
        } else {
            const err = await res.json();
            alert("Lỗi: " + (err.detail || "Thao tác hàng đợi thất bại"));
        }
    } catch (err) {
        alert("Lỗi kết nối đến server: " + err.message);
    }
}

export async function refreshBatchSnapshot() {
    if (!currentBatchId) return;
    try {
        const res = await api.getTranslateBatch(currentBatchId);
        if (res.ok) {
            const snapshot = await res.json();
            renderQueueTable(snapshot);
        }
    } catch (err) {
        console.error("Lỗi khi tải lại dữ liệu hàng đợi dịch thuật:", err);
    }
}

export { selectedJobIds, translateQueueInstance, currentBatchId };
