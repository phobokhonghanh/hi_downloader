import { truncatePath } from './helpers.js';
import * as api from './api.js';
import { state } from './state.js';

// DOM elements
const sourceRadios = document.getElementsByName('subtitle-source-mode');
const lblSourcePath = document.getElementById('lbl-subtitle-source-path');
const txtSourcePath = document.getElementById('subtitle-source-path');
const btnSelectSource = document.getElementById('btn-subtitle-select-source');
const folderInfo = document.getElementById('subtitle-folder-info');
const folderCount = document.getElementById('subtitle-folder-count');

const selectMethod = document.getElementById('subtitle-method');
const selectModel = document.getElementById('subtitle-model');
const selectLanguage = document.getElementById('subtitle-language');
const selectConcurrency = document.getElementById('subtitle-concurrency');
const btnGenerate = document.getElementById('btn-subtitle-generate');

// Callbacks
let srtLoadedCallback = null;
let batchCreatedCallback = null;

export function onSrtLoaded(cb) {
    srtLoadedCallback = cb;
}

export function onBatchCreated(cb) {
    batchCreatedCallback = cb;
}

export function initSubtitleSources() {
    // 1. Source Mode Change listener
    sourceRadios.forEach(radio => {
        radio.addEventListener('change', (e) => {
            const mode = e.target.value;
            state.currentSubtitleSourceMode = mode;
            state.currentSubtitleSourcePath = '';
            state.currentSubtitleFolderFiles = [];
            
            // Clear displays
            txtSourcePath.value = '';
            txtSourcePath.dataset.fullPath = '';
            txtSourcePath.title = '';
            folderInfo.style.display = 'none';
            folderCount.textContent = '0';
            
            // Update labels and placeholders
            if (mode === 'video') {
                lblSourcePath.textContent = 'Đường dẫn tệp video';
                txtSourcePath.placeholder = 'Chọn file video từ hệ thống...';
                // Show model/language/concurrency controls
                toggleConfigControls(true);
                btnGenerate.textContent = 'Tạo phụ đề';
            } else if (mode === 'folder') {
                lblSourcePath.textContent = 'Đường dẫn thư mục video';
                txtSourcePath.placeholder = 'Chọn thư mục chứa các file video...';
                toggleConfigControls(true);
                btnGenerate.textContent = 'Tạo phụ đề';
            } else if (mode === 'srt') {
                lblSourcePath.textContent = 'Đường dẫn tệp SRT';
                txtSourcePath.placeholder = 'Chọn tệp phụ đề SRT từ hệ thống...';
                // Hide Whisper-only batch controls and action button
                toggleConfigControls(false);
            }
        });
    });

    // 2. Select Source click listener
    if (btnSelectSource) {
        btnSelectSource.addEventListener('click', async () => {
            const mode = state.currentSubtitleSourceMode;
            btnSelectSource.disabled = true;
            try {
                if (mode === 'video') {
                    const res = await api.selectVideoFile();
                    if (res.ok) {
                        const data = await res.json();
                        if (data.status === 'success' && data.path) {
                            updateSourcePathDisplay(data.path);
                        }
                    } else {
                        handleErrorResponse(res, "Không thể chọn file video");
                    }
                } else if (mode === 'folder') {
                    const res = await api.selectVideoFolder();
                    if (res.ok) {
                        const data = await res.json();
                        if (data.status === 'success' && data.path) {
                            updateSourcePathDisplay(data.path);
                            await handleFolderScan(data.path);
                        }
                    } else {
                        handleErrorResponse(res, "Không thể chọn thư mục video");
                    }
                } else if (mode === 'srt') {
                    const res = await api.selectSrtFile();
                    if (res.ok) {
                        const data = await res.json();
                        if (data.status === 'success' && data.path && data.content !== undefined) {
                            updateSourcePathDisplay(data.path);
                            if (srtLoadedCallback) {
                                await srtLoadedCallback(data.content, data.path);
                            }
                        }
                    } else {
                        handleErrorResponse(res, "Không thể chọn file SRT");
                    }
                }
            } catch (err) {
                alert("Lỗi kết nối hộp thoại chọn nguồn: " + err.message);
            } finally {
                btnSelectSource.disabled = false;
            }
        });
    }

    // 3. Create Subtitle / Load SRT click listener
    if (btnGenerate) {
        btnGenerate.addEventListener('click', async () => {
            const mode = state.currentSubtitleSourceMode;
            const path = txtSourcePath.dataset.fullPath;

            if (!path) {
                alert("Vui lòng chọn đường dẫn nguồn trước.");
                return;
            }

            if (mode === 'srt') {
                // SRT mode just triggers callback directly (does not create batch)
                return;
            }

            // Video/Folder batches logic
            const provider = selectMethod.value;
            if (provider === 'ocr') {
                alert("Phương thức OCR hiện chưa được hỗ trợ. Vui lòng chọn Whisper.");
                return;
            }

            let videoPaths = [];
            if (mode === 'video') {
                videoPaths = [path];
            } else if (mode === 'folder') {
                if (state.currentSubtitleFolderFiles.length === 0) {
                    alert("Không tìm thấy tệp video hợp lệ nào trong thư mục được chọn.");
                    return;
                }
                videoPaths = state.currentSubtitleFolderFiles.map(f => f.path);
            }

            // Prevent duplicate clicks
            if (state.isGeneratingSubtitle) return;
            state.isGeneratingSubtitle = true;
            btnGenerate.disabled = true;

            try {
                const model = selectModel.value;
                const language = selectLanguage.value || null;
                const concurrency = parseInt(selectConcurrency.value, 10) || 2;

                const res = await api.createSubtitleBatch(videoPaths, provider, model, language, concurrency);
                if (res.ok) {
                    const data = await res.json();
                    if (data.batch_id) {
                        state.currentSubtitleBatchId = data.batch_id;
                        if (batchCreatedCallback) {
                            await batchCreatedCallback(data.batch_id, data.snapshot);
                        }
                    }
                } else {
                    let errMsg = "Lỗi khởi tạo hàng đợi";
                    try {
                        const err = await res.json();
                        errMsg = err.detail || err.message || errMsg;
                    } catch (e) {}
                    alert("Lỗi: " + errMsg);
                }
            } catch (err) {
                alert("Lỗi kết nối tạo hàng đợi: " + err.message);
            } finally {
                state.isGeneratingSubtitle = false;
                btnGenerate.disabled = false;
            }
        });
    }
}

async function handleFolderScan(folderPath) {
    try {
        const res = await api.scanFolder(folderPath);
        if (res.ok) {
            const data = await res.json();
            state.currentSubtitleFolderFiles = data.files || [];
            folderCount.textContent = data.total || 0;
            folderInfo.style.display = 'block';
        } else {
            let errMsg = "Không thể quét thư mục";
            try {
                const err = await res.json();
                errMsg = err.detail || err.message || errMsg;
            } catch (e) {}
            alert("Lỗi: " + errMsg);
        }
    } catch (err) {
        alert("Lỗi kết nối quét thư mục: " + err.message);
    }
}

function updateSourcePathDisplay(fullPath) {
    state.currentSubtitleSourcePath = fullPath;
    txtSourcePath.dataset.fullPath = fullPath;
    txtSourcePath.value = truncatePath(fullPath, 3);
    txtSourcePath.title = fullPath;
}



function toggleConfigControls(visible) {
    const methodContainer = document.getElementById('container-subtitle-method');
    const modelContainer = document.getElementById('container-subtitle-model');
    const languageContainer = document.getElementById('container-subtitle-language');
    const concurrencyContainer = document.getElementById('container-subtitle-concurrency');
    const generateBtn = document.getElementById('btn-subtitle-generate');
    
    const displayVal = visible ? 'block' : 'none';
    if (methodContainer) methodContainer.style.display = displayVal;
    if (modelContainer) modelContainer.style.display = displayVal;
    if (languageContainer) languageContainer.style.display = displayVal;
    if (concurrencyContainer) concurrencyContainer.style.display = displayVal;
    if (generateBtn) generateBtn.style.display = visible ? '' : 'none';
}

async function handleErrorResponse(res, prefix) {
    let errMsg = "Lỗi không xác định";
    try {
        const err = await res.json();
        errMsg = err.message || err.detail || JSON.stringify(err);
    } catch (e) {
        errMsg = await res.text();
    }
    alert(`${prefix}: ${errMsg}`);
}
