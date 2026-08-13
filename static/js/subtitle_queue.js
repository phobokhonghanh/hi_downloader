import { truncatePath } from './helpers.js';
import * as api from './api.js';
import { state } from './state.js';
import { JobQueue } from './job_queue.js';

let selectedJobIds = new Set();
let pollingTimer = null;
let isPollingActive = false;
let onOpenJobCallback = null;
let subtitleQueueInstance = null;

export function onOpenJob(cb) {
    onOpenJobCallback = cb;
}

export function initSubtitleQueue() {
    const container = document.getElementById('subtitle-queue-container');
    if (container) {
        subtitleQueueInstance = new JobQueue(container, {
            selectable: true,
            showSummaryInStatsBar: false,
            labels: {
                empty: "Chưa có hàng đợi phụ đề nào hoạt động. Hãy chọn video hoặc thư mục và nhấn \"Tạo phụ đề\".",
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
                    key: 'video',
                    label: 'URL',
                    width: '40%',
                    render: row => {
                        const div = document.createElement('div');
                        div.style.fontWeight = '600';
                        div.textContent = truncatePath(row.video_path);
                        div.title = row.video_path;
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

                        let statusText = row.status;
                        let statusColor = 'var(--text-muted)';
                        if (row.status === 'waiting') {
                            statusText = 'Đang chờ';
                        } else if (row.status === 'running') {
                            let phaseLabel = row.phase || 'transcribing';
                            if (phaseLabel === 'preparing') phaseLabel = 'Đang chuẩn bị';
                            else if (phaseLabel === 'loading model') phaseLabel = 'Đang tải mô hình';
                            else if (phaseLabel === 'transcribing') phaseLabel = 'Đang nhận dạng';
                            else if (phaseLabel === 'formatting') phaseLabel = 'Đang xuất phụ đề';
                            statusText = `${pct}% (${phaseLabel})`;
                            statusColor = '#ca8a04';
                        } else if (row.status === 'done') {
                            statusText = '100% (Hoàn thành)';
                            statusColor = '#16a34a';
                        } else if (row.status === 'error') {
                            statusText = `Lỗi: ${row.error || ''}`;
                            statusColor = '#dc2626';
                        } else if (row.status === 'canceled') {
                            statusText = 'Đã hủy';
                            statusColor = '#ef4444';
                        }

                        const text = document.createElement('span');
                        text.style.fontSize = '0.72rem';
                        text.style.fontWeight = '600';
                        text.style.color = statusColor;
                        text.textContent = statusText;

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
                                    const res = await api.openFileLocation(row.saved_path);
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
                                if (onOpenJobCallback) {
                                    onOpenJobCallback(row);
                                }
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
                { id: 'retry', label: 'Chạy lại', eligible: r => r.status === 'error' || r.status === 'canceled', onInvoke: (ids) => handleBatchAction('retry', ids) }
            ],
            onRowClick: row => {
                if (row.status === 'done' && onOpenJobCallback) {
                    onOpenJobCallback(row);
                }
            },
            onSelectionChange: ids => {
                selectedJobIds = new Set(ids);
            }
        });
        subtitleQueueInstance.update({ rows: [], elapsedSeconds: 0 });
    }
}

async function handleBatchAction(action, selectedIds) {
    if (!state.currentSubtitleBatchId) {
        alert("Không tìm thấy thông tin hàng đợi phụ đề hiện tại.");
        return;
    }

    const jobIdsArray = selectedIds || Array.from(selectedJobIds);
    if (jobIdsArray.length === 0) {
        alert("Vui lòng chọn ít nhất một tác vụ để thực hiện hành động.");
        return;
    }



    try {
        const res = await api.dispatchBatchAction(state.currentSubtitleBatchId, action, jobIdsArray);
        if (res.ok) {
            const data = await res.json();
            let applied = 0;
            let skipped = 0;
            if (data.results) {
                for (const jobId in data.results) {
                    const outcome = data.results[jobId].outcome;
                    if (outcome === 'applied') {
                        applied++;
                    } else if (outcome === 'skipped') {
                        skipped++;
                    }
                }
            }
            alert(`Đã áp dụng: ${applied}, bỏ qua: ${skipped}`);
            
            if (subtitleQueueInstance) {
                subtitleQueueInstance.selectedRowIds.clear();
                selectedJobIds.clear();
            }

            await refreshBatchSnapshot();
            
            if (action === 'retry') {
                startQueuePolling(state.currentSubtitleBatchId);
            }
        } else {
            let errMsg = "Thao tác hàng đợi thất bại";
            try {
                const err = await res.json();
                errMsg = err.detail || err.message || errMsg;
            } catch (e) {}
            alert("Lỗi: " + errMsg);
        }
    } catch (err) {
        alert("Lỗi kết nối đến server: " + err.message);
    }
}

async function refreshBatchSnapshot() {
    if (!state.currentSubtitleBatchId) return;
    try {
        const res = await api.getSubtitleBatch(state.currentSubtitleBatchId);
        if (res.ok) {
            const snapshot = await res.json();
            renderQueueTable(snapshot);
        }
    } catch (err) {
        console.error("Lỗi khi tải lại dữ liệu hàng đợi:", err);
    }
}

export function renderQueueTable(snapshot) {
    if (!snapshot) return;

    const elapsed = Math.round(snapshot.total_duration || 0);

    if (!subtitleQueueInstance) return;

    const jobs = snapshot.jobs || [];
    subtitleQueueInstance.update({
        rows: jobs,
        elapsedSeconds: elapsed
    });
}

export function startQueuePolling(batchId) {
    if (isPollingActive) {
        stopQueuePolling();
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
    if (!isPollingActive || state.currentSubtitleBatchId !== batchId) {
        return;
    }

    try {
        const res = await api.getSubtitleBatch(batchId);
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
        console.error("Lỗi polling hàng đợi:", err);
        pollingTimer = setTimeout(() => pollBatch(batchId), 5000);
    }
}

export function shouldStopPolling(snapshot, currentBatchId) {
    if (!snapshot || !currentBatchId) return true;
    const jobs = snapshot.jobs || [];
    const hasActiveJobs = jobs.some(j => j.status === 'waiting' || j.status === 'running');
    return !hasActiveJobs;
}

export function calculateJobStats(jobs) {
    const stats = { total: 0, waiting: 0, running: 0, done: 0, error: 0 };
    if (!jobs) return stats;
    stats.total = jobs.length;
    jobs.forEach(job => {
        if (job.status === 'waiting') stats.waiting++;
        else if (job.status === 'running') stats.running++;
        else if (job.status === 'done') stats.done++;
        else if (job.status === 'error' || job.status === 'canceled') stats.error++;
    });
    return stats;
}

export function getEligibleJobIdsForAction(jobs, action, selectedIds) {
    const selectedSet = new Set(selectedIds);
    return jobs
        .filter(job => selectedSet.has(job.job_id))
        .filter(job => {
            if (action === 'save') return job.status === 'done';
            if (action === 'cancel') return job.status === 'waiting' || job.status === 'running';
            if (action === 'retry') return job.status === 'error' || job.status === 'canceled';
            return false;
        })
        .map(job => job.job_id);
}

export { selectedJobIds, subtitleQueueInstance };
