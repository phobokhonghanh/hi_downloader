import {
    formatMsForSubtitle,
    computeGapLabel,
    truncatePath,
    parseSrtTextClient,
    exportSegmentsToSrtClient,
    replaceSegmentTextClient,
    mergeSegmentsClient,
    splitSegmentClient
} from './helpers.js';
import * as api from './api.js';

// DOM elements cache
let modal = null;
let modalTitle = null;
let btnOpenLocation = null;
let statusText = null;
let btnMerge = null;
let btnSplit = null;
let selectAllCheckbox = null;
let modalTableBody = null;
let btnSave = null;
let btnClose = null;

// Modal internal state
let activeMode = 'video'; // 'video' or 'srt'
let currentJob = null;
let currentBatchId = null;
let currentSrtPath = '';
let modalSegments = [];
let onSaveSuccessCallback = null;
let currentSavedPath = '';

export function initSubtitleModal() {
    modal = document.getElementById('subtitle-editor-modal');
    modalTitle = document.getElementById('modal-video-title');
    btnOpenLocation = document.getElementById('btn-modal-open-location');
    statusText = document.getElementById('modal-subtitle-status');
    btnMerge = document.getElementById('btn-modal-merge');
    btnSplit = document.getElementById('btn-modal-split');
    selectAllCheckbox = document.getElementById('modal-select-all');
    modalTableBody = document.getElementById('modal-subtitle-body');
    btnSave = document.getElementById('btn-modal-save');
    btnClose = document.getElementById('btn-modal-close');

    // 1. Select All Listener
    if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener('change', (e) => {
            const checked = e.target.checked;
            if (!modalTableBody) return;
            const checkboxes = modalTableBody.querySelectorAll('.modal-row-checkbox');
            checkboxes.forEach(cb => {
                cb.checked = checked;
            });
            updateModalToolbarButtons();
        });
    }

    // 2. Open Location Trigger
    if (btnOpenLocation) {
        btnOpenLocation.addEventListener('click', async () => {
            if (!currentSavedPath) return;
            btnOpenLocation.disabled = true;
            try {
                const res = await api.openFileLocation(currentSavedPath);
                if (!res.ok) {
                    alert("Không thể mở vị trí tệp.");
                }
            } catch (err) {
                alert("Lỗi kết nối: " + err.message);
            } finally {
                btnOpenLocation.disabled = false;
            }
        });
    }

    // 3. Close Modal Listener
    if (btnClose) {
        btnClose.addEventListener('click', () => {
            closeModal();
        });
    }
    const btnHeaderClose = document.getElementById('btn-modal-header-close');
    if (btnHeaderClose) {
        btnHeaderClose.addEventListener('click', () => {
            closeModal();
        });
    }
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                closeModal();
            }
        });
    }

    // 4. Save Modal Listener
    if (btnSave) {
        btnSave.addEventListener('click', async () => {
            if (modalSegments.length === 0) {
                alert("Không có nội dung phụ đề để lưu.");
                return;
            }

            btnSave.disabled = true;
            updateStatus('Đang lưu thay đổi...', '#2563eb');

            try {
                const srtContent = exportSegmentsToSrtClient(modalSegments);
                if (activeMode === 'srt') {
                    // SRT mode save
                    const res = await api.saveImportedSrt(currentSrtPath, srtContent);
                    if (res.ok) {
                        const data = await res.json();
                        if (data.saved_path) {
                            currentSavedPath = data.saved_path;
                            state.lastSavedSrtPath = data.saved_path;
                            
                            // Enable file location button
                            btnOpenLocation.disabled = false;
                            btnOpenLocation.title = "Mở vị trí file SRT: " + currentSavedPath;
                            
                            updateStatus('Đã lưu file SRT thành công', '#16a34a');
                            alert("Đã lưu chỉnh sửa tệp phụ đề SRT mới:\n" + currentSavedPath);
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
                } else {
                    // Video job mode save
                    const res = await api.updateJobSrt(currentBatchId, currentJob.job_id, srtContent, modalSegments);
                    if (res.ok) {
                        const data = await res.json();
                        if (data.status === 'success' && data.saved_path) {
                            currentSavedPath = data.saved_path;
                            
                            // Enable file location button
                            btnOpenLocation.disabled = false;
                            btnOpenLocation.title = "Mở vị trí file SRT: " + currentSavedPath;
                            
                            updateStatus('Đã lưu thay đổi thành công', '#16a34a');
                            alert("Đã cập nhật và xuất phụ đề thành công:\n" + currentSavedPath);
                            
                            if (onSaveSuccessCallback) {
                                await onSaveSuccessCallback(data.snapshot);
                            }
                        } else {
                            throw new Error(data.detail || "Lỗi lưu phụ đề");
                        }
                    } else {
                        let errMsg = "Lỗi phản hồi từ server";
                        try {
                            const err = await res.json();
                            errMsg = err.detail || err.message || JSON.stringify(err);
                        } catch (e) {}
                        throw new Error(errMsg);
                    }
                }
            } catch (err) {
                alert("Lưu thay đổi thất bại: " + err.message);
                updateStatus('Lỗi lưu thay đổi', '#dc2626');
            } finally {
                btnSave.disabled = false;
            }
        });
    }

    // 5. Merge Event
    if (btnMerge) {
        btnMerge.addEventListener('click', async () => {
            const indices = getCheckedIndices();
            if (indices.length < 2) return;

            // Check consecutiveness
            indices.sort((a, b) => a - b);
            for (let i = 1; i < indices.length; i++) {
                if (indices[i] !== indices[i - 1] + 1) {
                    alert("Chỉ có thể gộp các dòng phụ đề liên tiếp nhau!");
                    return;
                }
            }

            const startIndex = modalSegments[indices[0]].index;
            const endIndex = modalSegments[indices[indices.length - 1]].index;

            try {
                modalSegments = mergeSegmentsClient(modalSegments, startIndex, endIndex, false);
                renderModalTable(modalSegments);
                updateStatus("Gộp dòng thành công", "#16a34a");
            } catch (err) {
                if (err.message === 'gap') {
                    const confirmOverride = confirm("Khoảng cách giữa các dòng vượt quá giới hạn (max_gap_ms). Bạn có muốn gộp và bỏ qua giới hạn khoảng cách không?");
                    if (confirmOverride) {
                        try {
                            modalSegments = mergeSegmentsClient(modalSegments, startIndex, endIndex, true);
                            renderModalTable(modalSegments);
                            updateStatus("Gộp dòng thành công", "#16a34a");
                        } catch (retryErr) {
                            alert("Gộp dòng thất bại: " + retryErr.message);
                            updateStatus("Gộp dòng thất bại", "#dc2626");
                        }
                    }
                } else {
                    alert("Gộp dòng thất bại: " + err.message);
                    updateStatus("Gộp dòng thất bại", "#dc2626");
                }
            }
        });
    }

    // 6. Split Event
    if (btnSplit) {
        btnSplit.addEventListener('click', async () => {
            const indices = getCheckedIndices();
            if (indices.length !== 1) return;

            const idx = indices[0];
            const seg = modalSegments[idx];

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
                segments: modalSegments,
                index: seg.index,
                split_at_ms: splitAtMs,
                first_text: firstText.trim(),
                second_text: secondText.trim()
            };

            try {
                modalSegments = splitSegmentClient(modalSegments, seg.index, splitAtMs, firstText.trim(), secondText.trim());
                renderModalTable(modalSegments);
                updateStatus("Tách dòng thành công", "#16a34a");
            } catch (err) {
                alert("Tách dòng thất bại: " + err.message);
                updateStatus("Tách dòng thất bại", "#dc2626");
            }
        });
    }
}

const LANGUAGE_MAP = {
    'vi': 'Tiếng Việt',
    'en': 'Tiếng Anh',
    'zh': 'Tiếng Trung',
    'ja': 'Tiếng Nhật',
    'ko': 'Tiếng Hàn',
    'es': 'Tiếng Tây Ban Nha',
    'fr': 'Tiếng Pháp',
    'de': 'Tiếng Đức',
    'th': 'Tiếng Thái',
    'id': 'Tiếng Indonesia'
};

function renderSubtitleMetadata(provider, language, totalRows, detectedLanguage) {
    const methodEl = document.getElementById('sub-meta-method');
    const langEl = document.getElementById('sub-meta-language');
    const totalEl = document.getElementById('sub-meta-total');

    if (methodEl) {
        let displayProvider = 'Whisper';
        if (provider && provider.toLowerCase() === 'ocr') {
            displayProvider = 'OCR';
        }
        methodEl.textContent = displayProvider;
    }
    if (langEl) {
        let displayLang = 'Tự động nhận dạng';
        const cleanLang = (language || '').toLowerCase().trim();
        const cleanDetected = (detectedLanguage || '').toLowerCase().trim();
        
        if (cleanDetected && cleanDetected !== 'auto' && cleanDetected !== 'und') {
            const mapped = LANGUAGE_MAP[cleanDetected] || detectedLanguage;
            displayLang = `${mapped} (Nhận dạng)`;
        } else if (cleanLang && cleanLang !== 'auto' && cleanLang !== 'und') {
            displayLang = LANGUAGE_MAP[cleanLang] || language;
        } else if (provider && provider.toLowerCase() !== 'whisper') {
            displayLang = 'Không xác định (nạp từ tệp SRT)';
        }
        langEl.textContent = displayLang;
    }
    if (totalEl) {
        totalEl.textContent = totalRows + ' dòng';
    }
}

export function openModalForJob(job, batchId, onSaveSuccess) {
    activeMode = 'video';
    currentJob = job;
    currentBatchId = batchId;
    currentSrtPath = '';
    onSaveSuccessCallback = onSaveSuccess;
    modalSegments = job.segments || [];
    currentSavedPath = job.saved_path || '';

    if (modalTitle) {
        modalTitle.textContent = "Biên tập: " + truncatePath(job.video_path, 3);
    }
    
    setupModalInitialState();
    renderSubtitleMetadata(job.provider, job.language, modalSegments.length, job.detected_language);
    renderModalTable(modalSegments);
    showModal();
}

export async function openModalForSrt(content, path) {
    activeMode = 'srt';
    currentJob = null;
    currentBatchId = null;
    currentSrtPath = path;
    onSaveSuccessCallback = null;
    currentSavedPath = path; // In SRT mode, source_path is edited, output creates _edit.srt

    updateStatus('Đang xử lý phụ đề SRT...', '#2563eb');
    if (modalTitle) {
        modalTitle.textContent = "Biên tập SRT: " + truncatePath(path, 3);
    }
    
    setupModalInitialState();

    try {
        modalSegments = parseSrtTextClient(content);
        renderSubtitleMetadata('OCR', 'auto', modalSegments.length);
        renderModalTable(modalSegments);
        updateStatus(`Đã nạp phụ đề thành công (${modalSegments.length} dòng)`, "#16a34a");
        showModal();
    } catch (err) {
        alert("Lỗi nạp phụ đề SRT: " + err.message);
        updateStatus("Lỗi nạp phụ đề", "#dc2626");
    }
}

function setupModalInitialState() {
    if (selectAllCheckbox) selectAllCheckbox.checked = false;
    
    if (btnOpenLocation) {
        if (currentSavedPath) {
            btnOpenLocation.disabled = false;
            btnOpenLocation.title = "Mở vị trí file SRT: " + currentSavedPath;
        } else {
            btnOpenLocation.disabled = true;
            btnOpenLocation.title = "Chưa có file đã lưu";
        }
    }
    updateStatus('Chờ', 'var(--text-muted)');
}

function showModal() {
    if (modal) modal.style.display = 'flex';
}

function closeModal() {
    if (modal) modal.style.display = 'none';
}

function updateStatus(text, color) {
    if (statusText) {
        statusText.textContent = "Trạng thái: " + text;
        statusText.style.color = color || 'var(--text-muted)';
    }
}

function updateModalToolbarButtons() {
    const checkedCount = modalTableBody ? modalTableBody.querySelectorAll('.modal-row-checkbox:checked').length : 0;
    if (btnMerge) btnMerge.disabled = checkedCount < 2;
    if (btnSplit) btnSplit.disabled = checkedCount !== 1;
}

function getCheckedIndices() {
    if (!modalTableBody) return [];
    const checkboxes = modalTableBody.querySelectorAll('.modal-row-checkbox:checked');
    return Array.from(checkboxes).map(cb => parseInt(cb.dataset.index, 10));
}

function renderModalTable(segments) {
    if (!modalTableBody) return;
    modalTableBody.innerHTML = '';

    if (selectAllCheckbox) selectAllCheckbox.checked = false;

    if (!segments || segments.length === 0) {
        updateModalToolbarButtons();
        return;
    }

    segments.forEach((seg, idx) => {
        const tr = document.createElement('tr');

        // Checkbox cell
        const tdCheck = document.createElement('td');
        tdCheck.style.textAlign = 'center';
        tdCheck.style.padding = '8px';
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'modal-row-checkbox';
        checkbox.dataset.index = idx;
        checkbox.style.cursor = 'pointer';
        checkbox.addEventListener('change', () => {
            updateModalToolbarButtons();
            const allCheckboxes = modalTableBody.querySelectorAll('.modal-row-checkbox');
            const checkedCheckboxes = modalTableBody.querySelectorAll('.modal-row-checkbox:checked');
            if (selectAllCheckbox) {
                selectAllCheckbox.checked = allCheckboxes.length > 0 && allCheckboxes.length === checkedCheckboxes.length;
            }
        });
        tdCheck.appendChild(checkbox);
        tr.appendChild(tdCheck);

        // Index cell
        const tdIndex = document.createElement('td');
        tdIndex.style.padding = '8px';
        tdIndex.textContent = seg.index;
        tr.appendChild(tdIndex);

        // Start time cell
        const tdStart = document.createElement('td');
        tdStart.style.padding = '8px';
        tdStart.textContent = formatMsForSubtitle(seg.start_ms);
        tr.appendChild(tdStart);

        // End time cell
        const tdEnd = document.createElement('td');
        tdEnd.style.padding = '8px';
        tdEnd.textContent = formatMsForSubtitle(seg.end_ms);
        tr.appendChild(tdEnd);

        // Gap cell
        const tdGap = document.createElement('td');
        tdGap.style.padding = '8px';
        tdGap.textContent = computeGapLabel(segments[idx - 1], seg);
        tr.appendChild(tdGap);

        // Text cell
        const tdText = document.createElement('td');
        tdText.style.padding = '8px';
        tdText.textContent = seg.text; // Safe textContent injection to protect against XSS
        tr.appendChild(tdText);

        // Actions cell
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
                modalSegments = replaceSegmentTextClient(modalSegments, seg.index, trimmedText);
                renderModalTable(modalSegments);
                updateStatus("Sửa nội dung thành công", "#16a34a");
            } catch (err) {
                alert("Sửa nội dung thất bại: " + err.message);
                updateStatus("Sửa nội dung thất bại", "#dc2626");
            }
        });
        tdActions.appendChild(editBtn);
        tr.appendChild(tdActions);

        modalTableBody.appendChild(tr);
    });

    updateModalToolbarButtons();
}
