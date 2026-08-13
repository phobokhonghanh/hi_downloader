import { state } from './state.js';
import * as api from './api.js';
import { onLogsUpdated } from './polling.js';

// Dynamic getter helpers to prevent stale DOM element references
const getTerminalBody = () => document.getElementById('terminal-body');
const getBtnClearLogs = () => document.getElementById('btn-clear-logs');
const getBtnCopyLogs = () => document.getElementById('btn-copy-logs');
const getBtnScrollBottom = () => document.getElementById('btn-scroll-bottom');

export async function clearLogs() {
    const terminalBody = getTerminalBody();
    try {
        await api.clearLogs();
        if (terminalBody) {
            terminalBody.innerHTML = '<div class="terminal-line" style="color: var(--text-muted);">[LOG] Đã xóa toàn bộ nhật ký.</div>';
        }
    } catch (err) {
        console.error("Lỗi xóa log:", err);
    }
}

export function copyLogs() {
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

export function updateLogsUI(logs) {
    const terminalBody = getTerminalBody();
    if (!terminalBody) return;

    if (logs && logs.error) {
        terminalBody.innerHTML = '<div class="terminal-line" style="color: var(--text-muted);">[LỖI] Không thể kết xuất nhật ký hệ thống thời gian thực.</div>';
        return;
    }

    const wasAtBottom = !state.userIsScrolledUp;

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
}

export function initLogs() {
    // Subscribe to log updates
    onLogsUpdated(updateLogsUI);

    const terminalBody = getTerminalBody();
    const btnScrollBottom = getBtnScrollBottom();
    const btnClearLogs = getBtnClearLogs();
    const btnCopyLogs = getBtnCopyLogs();

    if (terminalBody) {
        terminalBody.addEventListener('scroll', () => {
            const currentTerminal = getTerminalBody();
            const currentScrollBtn = getBtnScrollBottom();
            if (!currentTerminal) return;

            const threshold = 30;
            const distanceToBottom = currentTerminal.scrollHeight - currentTerminal.clientHeight - currentTerminal.scrollTop;
            if (distanceToBottom > threshold) {
                state.userIsScrolledUp = true;
                if (currentScrollBtn) currentScrollBtn.style.display = 'flex';
            } else {
                state.userIsScrolledUp = false;
                if (currentScrollBtn) currentScrollBtn.style.display = 'none';
            }
        });
    }

    if (btnScrollBottom) {
        btnScrollBottom.addEventListener('click', () => {
            const currentTerminal = getTerminalBody();
            const currentScrollBtn = getBtnScrollBottom();
            
            state.userIsScrolledUp = false;
            if (currentScrollBtn) currentScrollBtn.style.display = 'none';
            if (currentTerminal) {
                currentTerminal.scrollTo({
                    top: currentTerminal.scrollHeight,
                    behavior: 'smooth'
                });
            }
        });
    }

    if (btnClearLogs) {
        btnClearLogs.addEventListener('click', clearLogs);
    }

    if (btnCopyLogs) {
        btnCopyLogs.addEventListener('click', copyLogs);
    }
}
