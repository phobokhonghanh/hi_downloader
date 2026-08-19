export async function fetchSystem() {
    const res = await fetch('/api/system');
    return res.json();
}

export async function selectDirectory() {
    const res = await fetch('/api/select-directory', { method: 'POST' });
    return res;
}

export async function selectProxyFile() {
    const res = await fetch('/api/select-proxy-file', { method: 'POST' });
    return res;
}

export async function clearProxyFile() {
    const res = await fetch('/api/proxy-file/clear', { method: 'POST' });
    return res;
}

export async function setProxyMode(mode) {
    const res = await fetch('/api/proxy-mode/set', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: mode })
    });
    return res;
}

export async function setProxyDisabled(disabled) {
    const res = await fetch('/api/proxy-disabled/set', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ disabled: disabled })
    });
    return res;
}

export async function selectVideoFile() {
    const res = await fetch('/api/select-video-file', { method: 'POST' });
    return res;
}

export async function selectSrtFile() {
    const res = await fetch('/api/select-srt-file', { method: 'POST' });
    return res;
}

export async function analyzeUrl(url, cookies_browser) {
    const res = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            url: url,
            cookies_browser: cookies_browser || null
        })
    });
    return res;
}

export async function downloadVideo(reqBody) {
    const res = await fetch('/api/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(reqBody)
    });
    return res;
}

export async function fetchTasks() {
    const res = await fetch('/api/tasks');
    return res.json();
}

export async function clearTasksQueue() {
    const res = await fetch('/api/tasks/clear', { method: 'POST' });
    return res;
}

export async function cancelTask(taskId) {
    const res = await fetch(`/api/tasks/${taskId}/cancel`, { method: 'POST' });
    return res;
}

export async function openFolder(taskId) {
    const res = await fetch(`/api/tasks/${taskId}/open-folder`, { method: 'POST' });
    return res;
}

export async function clearLogs() {
    const res = await fetch('/api/logs/clear', { method: 'POST' });
    return res;
}

export async function fetchLogs() {
    const res = await fetch('/api/logs');
    return res.json();
}

export async function runSubtitleModule(params) {
    const res = await fetch('/api/modules/subtitle/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ params: params })
    });
    return res;
}

export async function saveSrt(videoPath, content) {
    const res = await fetch('/api/subtitle/save-srt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            video_path: videoPath,
            content: content
        })
    });
    return res;
}

export async function openFileLocation(path) {
    const res = await fetch('/api/subtitle/open-file-location', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: path })
    });
    return res;
}

export async function selectVideoFolder() {
    const res = await fetch('/api/subtitle/select-video-folder', { method: 'POST' });
    return res;
}

export async function scanFolder(folderPath) {
    const res = await fetch('/api/subtitle/scan-folder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder_path: folderPath })
    });
    return res;
}

export async function saveImportedSrt(sourcePath, content) {
    const res = await fetch('/api/subtitle/save-imported-srt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_path: sourcePath, content: content })
    });
    return res;
}

export async function createSubtitleBatch(videoPaths, provider, model, language, concurrency) {
    const res = await fetch('/api/subtitle/batches', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            video_paths: videoPaths,
            provider: provider,
            model: model,
            language: language,
            concurrency: concurrency
        })
    });
    return res;
}

export async function getSubtitleBatch(batchId) {
    const res = await fetch(`/api/subtitle/batches/${batchId}`);
    return res;
}

export async function dispatchBatchAction(batchId, action, jobIds) {
    const res = await fetch(`/api/subtitle/batches/${batchId}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: action, job_ids: jobIds })
    });
    return res;
}

export async function updateJobSrt(batchId, jobId, srtText, segments) {
    const res = await fetch(`/api/subtitle/batches/${batchId}/jobs/${jobId}/update-srt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ srt_text: srtText, segments: segments })
    });
    return res;
}

export async function fetchTranslateProfiles() {
    const res = await fetch('/api/translate/profiles');
    return res.json();
}

export async function fetchTranslateProviders() {
    const res = await fetch('/api/translate/providers');
    return res.json();
}

export async function fetchTranslateCredentials(provider) {
    const url = provider ? `/api/translate/credentials/${provider}` : '/api/translate/credentials';
    const res = await fetch(url);
    return res.json();
}

export async function setTranslateCredentials(provider, apiKey, persist) {
    const url = provider ? `/api/translate/credentials/${provider}` : '/api/translate/credentials';
    const res = await fetch(url, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: apiKey, persist: persist, provider: provider })
    });
    return res;
}

export async function deleteTranslateCredentials(provider) {
    const url = provider ? `/api/translate/credentials/${provider}` : '/api/translate/credentials';
    const res = await fetch(url, { method: 'DELETE' });
    return res;
}

export async function revealTranslateCredentials(provider) {
    const res = await fetch(`/api/translate/credentials/${provider}/reveal`);
    return res;
}

export async function testTranslateCredentials(provider) {
    const url = provider ? `/api/translate/credentials/test/${provider}` : '/api/translate/credentials/test';
    const res = await fetch(url, { method: 'POST' });
    return res;
}

export async function scanTranslateFolder(path) {
    const res = await fetch('/api/translate/scan-folder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: path })
    });
    return res;
}

export async function createTranslateBatch(files, targetLanguage, profile, concurrency, enableTimeConstraint = true, targetWps = 4.2) {
    const res = await fetch('/api/translate/batches', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            files: files,
            target_language: targetLanguage,
            profile: profile,
            concurrency: concurrency,
            enable_time_constraint: enableTimeConstraint,
            target_wps: targetWps
        })
    });
    return res;
}

export async function getTranslateBatch(batchId) {
    const res = await fetch(`/api/translate/batches/${batchId}`);
    return res;
}

export async function dispatchTranslateBatchAction(batchId, action, jobIds) {
    const res = await fetch(`/api/translate/batches/${batchId}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: action, job_ids: jobIds })
    });
    return res;
}

export async function getTranslateJobCompare(batchId, jobId) {
    const res = await fetch(`/api/translate/batches/${batchId}/jobs/${jobId}/compare`);
    return res;
}

export async function saveTranslateJobEdits(batchId, jobId, edits) {
    const res = await fetch(`/api/translate/batches/${batchId}/jobs/${jobId}/edits`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ edits: edits })
    });
    return res;
}

export async function openTranslateJobLocation(batchId, jobId) {
    const res = await fetch(`/api/translate/batches/${batchId}/jobs/${jobId}/open-location`, {
        method: 'POST'
    });
    return res;
}
