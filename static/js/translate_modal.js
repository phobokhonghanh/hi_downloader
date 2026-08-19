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

    setupFilterButtons();

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

let activeFilter = 'all';

function setupFilterButtons() {
    const filterGroup = document.getElementById('translate-filter-btn-group');
    if (!filterGroup) return;

    const buttons = filterGroup.querySelectorAll('.filter-btn');
    buttons.forEach(btn => {
        btn.addEventListener('click', () => {
            buttons.forEach(b => {
                b.classList.remove('active', 'btn-solid-blue');
                b.classList.add('btn-outline-blue');
            });
            btn.classList.add('active', 'btn-solid-blue');
            btn.classList.remove('btn-outline-blue');
            activeFilter = btn.dataset.filter || 'all';
            renderModalTable();
        });
    });
}

function renderModalTable() {
    if (!modalTableBody) return;
    modalTableBody.innerHTML = '';

    // Update filter counts
    const countAll = compareSegments.length;
    const countAsr = compareSegments.filter(s => s.asr_corrected).length;
    const countOvertime = compareSegments.filter(s => s.is_overtime).length;

    const elAll = document.getElementById('filter-count-all');
    const elAsr = document.getElementById('filter-count-asr');
    const elOver = document.getElementById('filter-count-overtime');
    if (elAll) elAll.textContent = countAll;
    if (elAsr) elAsr.textContent = countAsr;
    if (elOver) elOver.textContent = countOvertime;

    // Filter rows
    const visibleSegments = compareSegments.filter(seg => {
        if (activeFilter === 'asr') return !!seg.asr_corrected;
        if (activeFilter === 'overtime') return !!seg.is_overtime;
        return true;
    });

    if (visibleSegments.length === 0) {
        const emptyTr = document.createElement('tr');
        emptyTr.innerHTML = `
            <td colspan="3" style="padding: 30px; text-align: center; color: var(--text-muted); font-size: 0.8rem;">
                Không có câu thoại nào phù hợp với bộ lọc "${activeFilter === 'asr' ? 'Sửa ASR' : activeFilter === 'overtime' ? 'Rút gọn TTS' : 'Tất cả'}".
            </td>
        `;
        modalTableBody.appendChild(emptyTr);
        return;
    }

    visibleSegments.forEach((seg, idx) => {
        const tr = document.createElement('tr');
        tr.style.borderBottom = '1px solid #e2e8f0';
        if (seg.asr_corrected) {
            tr.style.background = '#fffbeb';
        } else if (seg.is_overtime) {
            tr.style.background = '#f0f9ff';
        }

        // Timestamps & Index
        const tdMeta = document.createElement('td');
        tdMeta.style.padding = '8px';
        tdMeta.style.verticalAlign = 'top';
        tdMeta.style.whiteSpace = 'nowrap';
        
        const prevSeg = visibleSegments[idx - 1] || null;
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
        
        const origLabel = document.createElement('div');
        origLabel.style.fontSize = '0.68rem';
        origLabel.style.fontWeight = '600';
        origLabel.style.color = 'var(--text-muted)';
        origLabel.style.marginBottom = '2px';
        origLabel.textContent = 'Gốc:';
        tdOriginal.appendChild(origLabel);

        const origTa = document.createElement('textarea');
        origTa.className = 'translate-orig-textarea';
        origTa.readOnly = true;
        origTa.textContent = seg.source_text;
        tdOriginal.appendChild(origTa);

        if (seg.asr_corrected && seg.corrected_source) {
            const corrLabel = document.createElement('div');
            corrLabel.style.fontSize = '0.68rem';
            corrLabel.style.fontWeight = '700';
            corrLabel.style.color = '#b45309';
            corrLabel.style.marginTop = '6px';
            corrLabel.style.marginBottom = '2px';
            corrLabel.textContent = 'Chỉnh sửa:';
            tdOriginal.appendChild(corrLabel);

            const corrTa = document.createElement('textarea');
            corrTa.className = 'translate-orig-textarea';
            corrTa.readOnly = true;
            corrTa.style.borderColor = '#fde68a';
            corrTa.style.background = '#fffbeb';
            corrTa.textContent = seg.corrected_source;
            tdOriginal.appendChild(corrTa);
        }

        tr.appendChild(tdOriginal);

        // Translated Text (Editable)
        const tdTranslated = document.createElement('td');
        tdTranslated.style.padding = '8px';
        tdTranslated.style.verticalAlign = 'top';

        const transHeader = document.createElement('div');
        transHeader.style.display = 'flex';
        transHeader.style.justifyContent = 'space-between';
        transHeader.style.alignItems = 'center';
        transHeader.style.marginBottom = '4px';

        const transLabel = document.createElement('span');
        transLabel.style.fontSize = '0.68rem';
        transLabel.style.fontWeight = '600';
        transLabel.style.color = 'var(--text-muted)';
        transLabel.textContent = 'Bản dịch:';
        transHeader.appendChild(transLabel);

        const contextualText = seg.translated_text || '';
        const rawText = seg.original_translation || '';

        let transTa = null;

        if (seg.asr_corrected && rawText) {
            const pillContainer = document.createElement('div');
            pillContainer.style.display = 'flex';
            pillContainer.style.gap = '2px';
            pillContainer.style.background = '#e2e8f0';
            pillContainer.style.borderRadius = '4px';
            pillContainer.style.padding = '2px';

            const optCorrBtn = document.createElement('button');
            optCorrBtn.type = 'button';
            optCorrBtn.style.padding = '2px 8px';
            optCorrBtn.style.fontSize = '0.65rem';
            optCorrBtn.style.border = 'none';
            optCorrBtn.style.borderRadius = '3px';
            optCorrBtn.style.cursor = 'pointer';
            optCorrBtn.style.background = '#2563eb';
            optCorrBtn.style.color = '#ffffff';
            optCorrBtn.style.fontWeight = '600';
            optCorrBtn.textContent = 'Chỉnh sửa';

            const optOrigBtn = document.createElement('button');
            optOrigBtn.type = 'button';
            optOrigBtn.style.padding = '2px 8px';
            optOrigBtn.style.fontSize = '0.65rem';
            optOrigBtn.style.border = 'none';
            optOrigBtn.style.borderRadius = '3px';
            optOrigBtn.style.cursor = 'pointer';
            optOrigBtn.style.background = 'transparent';
            optOrigBtn.style.color = '#475569';
            optOrigBtn.textContent = 'Gốc';

            const altPreview = document.createElement('div');
            altPreview.style.fontSize = '0.65rem';
            altPreview.style.color = '#64748b';
            altPreview.style.marginTop = '4px';
            altPreview.style.fontStyle = 'italic';

            const updatePreview = (isCorr) => {
                const altLabel = isCorr ? 'Gốc' : 'Chỉnh sửa';
                const altVal = isCorr ? rawText : contextualText;
                altPreview.innerHTML = `<span style="font-weight:600; font-style:normal;">Đối chiếu (${altLabel}):</span> "${altVal}"`;
            };

            updatePreview(true);

            optCorrBtn.addEventListener('click', () => {
                transTa.value = contextualText;
                optCorrBtn.style.background = '#2563eb';
                optCorrBtn.style.color = '#ffffff';
                optOrigBtn.style.background = 'transparent';
                optOrigBtn.style.color = '#475569';
                updatePreview(true);
            });

            optOrigBtn.addEventListener('click', () => {
                transTa.value = rawText;
                optOrigBtn.style.background = '#2563eb';
                optOrigBtn.style.color = '#ffffff';
                optCorrBtn.style.background = 'transparent';
                optCorrBtn.style.color = '#475569';
                updatePreview(false);
            });

            pillContainer.appendChild(optCorrBtn);
            pillContainer.appendChild(optOrigBtn);
            transHeader.appendChild(pillContainer);
            tdTranslated.appendChild(transHeader);

            transTa = document.createElement('textarea');
            transTa.className = 'translate-trans-textarea';
            transTa.dataset.index = seg.index;
            transTa.value = contextualText;
            tdTranslated.appendChild(transTa);
            tdTranslated.appendChild(altPreview);
        } else {
            tdTranslated.appendChild(transHeader);

            transTa = document.createElement('textarea');
            transTa.className = 'translate-trans-textarea';
            transTa.dataset.index = seg.index;
            transTa.value = contextualText;
            tdTranslated.appendChild(transTa);
        }

        tr.appendChild(tdTranslated);

        modalTableBody.appendChild(tr);
    });
}
