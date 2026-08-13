import { state } from './state.js';
import { fetchTasks, fetchLogs } from './api.js';

let taskPollingTimeoutId = null;
let isTaskPollingActive = false;
let lastTaskActionTime = 0;

let logPollingTimeoutId = null;
let isLogPollingActive = false;
let lastLogActionTime = 0;

const tasksUpdatedCallbacks = [];
const logsUpdatedCallbacks = [];

export function onTasksUpdated(callback) {
    tasksUpdatedCallbacks.push(callback);
}

export function onLogsUpdated(callback) {
    logsUpdatedCallbacks.push(callback);
}

export function setIsAnalyzing(val) {
    state.isAnalyzing = val;
}

export function triggerTaskPolling() {
    lastTaskActionTime = Date.now();
    if (!isTaskPollingActive) {
        isTaskPollingActive = true;
        pollTasks();
    }
}

export function triggerLogPolling() {
    lastLogActionTime = Date.now();
    if (!isLogPollingActive) {
        isLogPollingActive = true;
        pollLogs();
    }
}

async function pollTasks() {
    let hasActive = false;
    try {
        const tasks = await fetchTasks();
        state.allTasks = tasks;
        
        // Notify subscribers
        tasksUpdatedCallbacks.forEach(cb => cb(tasks));

        const activeStatuses = ['pending', 'downloading', 'merging', 'processing'];
        hasActive = tasks.some(t => activeStatuses.includes(t.status));
    } catch (e) {
        console.error("Lỗi trong quá trình adaptive task polling:", e);
    }

    const timeSinceLastAction = Date.now() - lastTaskActionTime;
    if (hasActive || timeSinceLastAction < 5000) {
        taskPollingTimeoutId = setTimeout(pollTasks, 1500);
    } else {
        isTaskPollingActive = false;
        taskPollingTimeoutId = null;
    }
}

async function pollLogs() {
    try {
        const logs = await fetchLogs();
        
        // Notify subscribers
        logsUpdatedCallbacks.forEach(cb => cb(logs));
    } catch (e) {
        console.error("Lỗi trong quá trình log polling:", e);
        logsUpdatedCallbacks.forEach(cb => cb({ error: true }));
    }

    logPollingTimeoutId = setTimeout(pollLogs, 1500);
}

export function resetLogPollingForTesting() {
    if (logPollingTimeoutId) {
        clearTimeout(logPollingTimeoutId);
        logPollingTimeoutId = null;
    }
    isLogPollingActive = false;
}
