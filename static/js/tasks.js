import { state } from './state.js';
import * as api from './api.js';
import { triggerTaskPolling, onTasksUpdated } from './polling.js';
import { JobQueue } from './job_queue.js';
import { truncatePath } from './helpers.js?v=2';

const btnClearQueue = document.getElementById('btn-clear-queue');
let downloaderQueueInstance = null;

export async function clearQueue() {
    try {
        await api.clearTasksQueue();
        triggerTaskPolling();
    } catch (e) {
        console.error("Lỗi xóa hàng chờ:", e);
    }
}

export async function cancelTask(taskId) {
    if (!confirm("Hủy tiến trình tải này?")) return;
    try {
        await api.cancelTask(taskId);
        triggerTaskPolling();
    } catch (e) {
        console.error(e);
    }
}

export async function openFolder(taskId) {
    try {
        const res = await api.openFolder(taskId);
        if (!res.ok) {
            const err = await res.json();
            alert("Không thể mở thư mục: " + (err.detail || err.message));
        }
    } catch (e) {
        alert("Lỗi mở thư mục: " + e);
    }
}

export function copyErrorText(btn, taskId) {
    const task = state.allTasks.find(t => t.id === taskId);
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

export function updateTasksUI(tasks) {
    if (!downloaderQueueInstance) return;

    let totalTime = 0;
    tasks.forEach(t => {
        totalTime += t.elapsed_time || 0;
    });

    downloaderQueueInstance.update({
        rows: tasks,
        elapsedSeconds: Math.round(totalTime)
    });
}

export function initTasks() {
    // Subscribe to task updates
    onTasksUpdated(updateTasksUI);

    if (btnClearQueue) {
        btnClearQueue.addEventListener('click', clearQueue);
    }

    const container = document.getElementById('downloader-queue-container');
    if (container) {
        downloaderQueueInstance = new JobQueue(container, {
            selectable: false,
            labels: {
                empty: "Hàng chờ trống. Vui lòng thêm video để bắt đầu.",
                total: "Tổng",
                waiting: "Chờ",
                running: "Đang chạy",
                done: "Hoàn thành",
                error: "Lỗi/Hủy",
                elapsed: "Thời gian chạy"
            },
            getRowId: row => row.id,
            normalizeStatus: row => {
                if (row.status === 'pending') return 'waiting';
                if (['downloading', 'merging', 'processing'].includes(row.status)) return 'running';
                if (row.status === 'completed') return 'done';
                return 'error';
            },
            columns: [
                {
                    key: 'url',
                    label: 'URL',
                    width: '40%',
                    render: row => {
                        const div = document.createElement('div');
                        div.className = 'queue-display-url';
                        const url = row.url || '';
                        if (url.startsWith('http://') || url.startsWith('https://')) {
                            const a = document.createElement('a');
                            a.href = url;
                            a.target = '_blank';
                            a.rel = 'noopener noreferrer';
                            a.textContent = truncatePath(url);
                            a.addEventListener('click', e => e.stopPropagation());
                            div.appendChild(a);
                        } else {
                            div.textContent = truncatePath(url) || row.filename || '—';
                        }
                        div.title = url;
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
                        bar.style.width = `${row.progress}%`;
                        track.appendChild(bar);

                        let statusLabel = row.status;
                        if (row.status === 'merging') statusLabel = 'Đang ghép';
                        else if (row.status === 'downloading') statusLabel = 'Đang tải';
                        else if (row.status === 'processing') statusLabel = 'Đang xử lý';
                        else if (row.status === 'completed') statusLabel = 'Hoàn thành';
                        else if (row.status === 'pending') statusLabel = 'Chờ';
                        else if (row.status === 'failed') statusLabel = 'Lỗi';
                        else if (row.status === 'canceled') statusLabel = 'Đã hủy';

                        const text = document.createElement('span');
                        text.style.fontSize = '0.68rem';
                        text.style.fontWeight = '600';
                        text.style.color = row.status === 'completed' ? '#16a34a' : (row.status === 'failed' ? '#dc2626' : 'var(--text-muted)');
                        
                        let displayMsg = `${statusLabel} (${row.progress}%)`;
                        if (row.error) {
                            const cleanError = row.error.replace(/\u001b\[[0-9;]*m/g, "");
                            displayMsg += ` - Lỗi: ${cleanError}`;
                        }
                        text.textContent = displayMsg;

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
                        
                        const btn = document.createElement('button');
                        btn.type = 'button';
                        btn.className = 'btn-row-action';
                        btn.setAttribute('aria-label', 'Mở thư mục');
                        btn.title = 'Mở thư mục';
                        
                        btn.innerHTML = `
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2z"></path>
                            </svg>
                        `;
                        
                        if (row.status === 'completed') {
                            btn.disabled = false;
                            btn.addEventListener('click', (e) => {
                                e.stopPropagation();
                                openFolder(row.id);
                            });
                        } else {
                            btn.disabled = true;
                        }
                        container.appendChild(btn);
                        return container;
                    }
                }
            ]
        });
    }
}

// Export downloaderQueueInstance for unit testing verification
export { downloaderQueueInstance };
