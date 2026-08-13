import { formatMsForSubtitle, computeGapLabel, truncatePath } from './helpers.js';
import * as api from './api.js';

let modal = null;
let modalTitle = null;
let btnOpenLocation = null;
let statusText = null;
let modalTableBody = null;
let btnSave = null;
let btnClose = null;

let currentJobId = null;
let currentBatchId = null;
let compareSegments = [];
let currentSavedPath = '';
let onSaveSuccessCallback = null;

export function initTranslateModal(onSaveSuccess) {
    modal = document.getElementById('translate-editor-modal');
    modalTitle = document.getElementById('translate-modal-title');
    btnOpenLocation = document.getElementById('btn-translate-modal-open-location');
    statusText = document.getElementById('translate-modal-status');
    modalTableBody = document.getElementById('translate-modal-body');
    btnSave = document.getElementById('btn-translate-modal-save');
    btnClose = document.getElementById('btn-translate-modal-close');
    onSaveSuccessCallback = onSaveSuccess;

    // Listeners setup once
    if (btnOpenLocation) {
        btnOpenLocation.addEventListener('click', async () => {
            if (!currentSavedPath) return;
            btnOpenLocation.disabled = true;
            try {
                const res = await api.openTranslateJobLocation(currentBatchId, currentJobId);
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

    if (btnClose) {
        btnClose.addEventListener('click', () => {
            closeModal();
        });
    }
    const btnHeaderClose = document.getElementById('btn-translate-modal-header-close');
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

    if (btnSave) {
        btnSave.addEventListener('click', async () => {
            if (compareSegments.length === 0) {
                alert("Không có dữ liệu bản dịch để lưu.");
                return;
            }

            // Gather edits
            const edits = {};
            const textareas = modalTableBody.querySelectorAll('.translate-trans-textarea');
            let hasBlank = false;

            textareas.forEach(ta => {
                const idx = parseInt(ta.dataset.index, 10);
                const val = ta.value.trim();
                if (!val) {
                    hasBlank = true;
                }
                edits[idx] = val;
            });

            if (hasBlank) {
                alert("Nội dung bản dịch không được để trống.");
                return;
            }

            btnSave.disabled = true;
            updateStatus('Đang lưu thay đổi...', '#2563eb');

            try {
                const res = await api.saveTranslateJobEdits(currentBatchId, currentJobId, edits);
                if (res.ok) {
                    updateStatus('Đã cập nhật bản dịch thành công', '#16a34a');
                    alert("Đã lưu các chỉnh sửa bản dịch thành công.");
                    if (onSaveSuccessCallback) {
                        await onSaveSuccessCallback();
                    }
                    // Reload comparison values
                    await loadCompareData(currentBatchId, currentJobId);
                } else {
                    const err = await res.json();
                    throw new Error(err.detail || "Lỗi lưu bản dịch");
                }
            } catch (err) {
                alert("Lưu thay đổi thất bại: " + err.message);
                updateStatus('Lỗi lưu thay đổi', '#dc2626');
            } finally {
                btnSave.disabled = false;
            }
        });
    }
}

export async function openTranslateModal(batchId, jobId) {
    currentBatchId = batchId;
    currentJobId = jobId;
    compareSegments = [];
    currentSavedPath = '';

    updateStatus('Đang tải dữ liệu đối chiếu bản dịch...', '#2563eb');
    if (modalTitle) {
        modalTitle.textContent = "Biên tập bản dịch song song";
    }
    
    if (btnOpenLocation) {
        btnOpenLocation.disabled = true;
        btnOpenLocation.title = "Chưa có file đã lưu";
    }

    showModal();
    await loadCompareData(batchId, jobId);
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

function renderTranslateMetadata(elapsedTime, targetLanguage, contextMetadata, totalRows) {
    const elapsedEl = document.getElementById('trans-meta-elapsed');
    const sourceEl = document.getElementById('trans-meta-source');
    const targetEl = document.getElementById('trans-meta-target');
    const totalEl = document.getElementById('trans-meta-total');

    if (elapsedEl) {
        elapsedEl.textContent = (elapsedTime || 0) + 's';
    }
    if (sourceEl) {
        sourceEl.textContent = (contextMetadata && contextMetadata.source_language_name) || 'Không xác định';
    }
    if (targetEl) {
        const cleanLang = (targetLanguage || '').toLowerCase().trim();
        targetEl.textContent = LANGUAGE_MAP[cleanLang] || targetLanguage || 'Không xác định';
    }
    if (totalEl) {
        totalEl.textContent = totalRows + ' dòng';
    }
}

async function loadCompareData(batchId, jobId) {
    try {
        const res = await api.getTranslateJobCompare(batchId, jobId);
        if (res.ok) {
            const data = await res.json();
            compareSegments = data.segments || [];
            currentSavedPath = data.saved_path || '';

            if (modalTitle) {
                modalTitle.textContent = "Đối chiếu bản dịch: " + truncatePath(data.source_path, 3);
            }

            if (btnOpenLocation) {
                if (currentSavedPath) {
                    btnOpenLocation.disabled = false;
                    btnOpenLocation.title = "Mở vị trí file dịch: " + currentSavedPath;
                } else {
                    btnOpenLocation.disabled = true;
                    btnOpenLocation.title = "Chưa có file đã lưu";
                }
            }

            renderTranslateMetadata(data.elapsed_time, data.target_language, data.context_metadata, compareSegments.length);
            renderModalTable();
            updateStatus(`Đã nạp đối chiếu thành công (${compareSegments.length} dòng)`, '#16a34a');
        } else {
            const err = await res.json();
            throw new Error(err.detail || "Không thể tải dữ liệu");
        }
    } catch (err) {
        alert("Lỗi nạp dữ liệu so sánh: " + err.message);
        updateStatus("Lỗi nạp dữ liệu", "#dc2626");
    }
}

function showModal() {
    if (modal) modal.style.display = 'flex';
}

export function closeModal() {
    if (modal) modal.style.display = 'none';
}

function updateStatus(text, color) {
    if (statusText) {
        statusText.textContent = "Trạng thái: " + text;
        statusText.style.color = color || 'var(--text-muted)';
    }
}

function renderModalTable() {
    if (!modalTableBody) return;
    modalTableBody.innerHTML = '';

    compareSegments.forEach((seg, idx) => {
        const tr = document.createElement('tr');

        // Timestamps & Index
        const tdMeta = document.createElement('td');
        tdMeta.style.padding = '8px';
        tdMeta.style.verticalAlign = 'top';
        tdMeta.style.whiteSpace = 'nowrap';
        
        const prevSeg = compareSegments[idx - 1] || null;
        const gapText = computeGapLabel(prevSeg, { start_ms: seg.start_ms });

        tdMeta.innerHTML = `
            <div style="font-weight: 700; color: var(--primary);">#${seg.index}</div>
            <div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 4px;">
                ${formatMsForSubtitle(seg.start_ms)}
            </div>
            <div style="font-size: 0.7rem; color: var(--text-muted);">
                ${formatMsForSubtitle(seg.end_ms)}
            </div>
            <div style="font-size: 0.65rem; color: #a1a1aa; margin-top: 4px;">
                Khoảng cách: ${gapText}
            </div>
        `;
        tr.appendChild(tdMeta);

        // Original Text (Readonly)
        const tdOriginal = document.createElement('td');
        tdOriginal.style.padding = '8px';
        tdOriginal.style.verticalAlign = 'top';
        
        const origTa = document.createElement('textarea');
        origTa.className = 'translate-orig-textarea';
        origTa.readOnly = true;
        origTa.textContent = seg.source_text;
        tdOriginal.appendChild(origTa);
        tr.appendChild(tdOriginal);

        // Translated Text (Editable)
        const tdTranslated = document.createElement('td');
        tdTranslated.style.padding = '8px';
        tdTranslated.style.verticalAlign = 'top';

        const transTa = document.createElement('textarea');
        transTa.className = 'translate-trans-textarea';
        transTa.dataset.index = seg.index;
        transTa.value = seg.translated_text || '';
        tdTranslated.appendChild(transTa);
        tr.appendChild(tdTranslated);

        modalTableBody.appendChild(tr);
    });
}
