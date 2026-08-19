import { truncatePath } from './helpers.js';
import * as api from './api.js';
import { initTranslateQueue, startQueuePolling, refreshBatchSnapshot } from './translate_queue.js';
import { initTranslateModal } from './translate_modal.js';

let activeSourceFiles = [];
let profilesList = [];
let providersCatalog = [];

export async function initTranslate() {
    const sourceRadios = document.getElementsByName('translate-source-mode');
    const lblSourcePath = document.getElementById('lbl-translate-source-path');
    const txtSourcePath = document.getElementById('translate-source-path');
    const btnSelectSource = document.getElementById('btn-translate-select-source');

    const folderInfo = document.getElementById('translate-folder-info');
    const folderCount = document.getElementById('translate-folder-count');
    const fileList = document.getElementById('translate-file-list');

    const selectLanguage = document.getElementById('translate-language');
    const selectProfile = document.getElementById('translate-profile');
    const selectConcurrency = document.getElementById('translate-concurrency');
    const btnStart = document.getElementById('btn-translate-start');

    // Load dynamic translation profiles catalog list
    await updateProfilesUI();
    try {
        providersCatalog = await api.fetchTranslateProviders();
    } catch (err) {
        console.error("Lỗi lấy danh sách nhà cung cấp:", err);
    }

    // Initialize translate queue and comparison editor modal once
    initTranslateQueue();
    initTranslateModal(refreshBatchSnapshot);

    // 1. Model Selection change listener
    if (selectProfile) {
        selectProfile.addEventListener('change', async () => {
            const profileVal = selectProfile.value;
            if (!profileVal) {
                await updateStartButton();
                return;
            }

            const profileObj = profilesList.find(p => p.profile === profileVal);
            if (!profileObj) return;

            const provider = profileObj.provider || "gemini";
            try {
                const creds = await api.fetchTranslateCredentials(provider);
                if (!creds.configured) {
                    openQuickKeyModal(provider, profileObj.label);
                } else {
                    await updateStartButton();
                }
            } catch (err) {
                console.error("Lỗi kiểm tra credentials nhà cung cấp:", err);
            }
        });
    }

    // 2. Source Mode Switch Listeners
    sourceRadios.forEach(radio => {
        radio.addEventListener('change', async () => {
            const mode = radio.value;
            txtSourcePath.value = '';
            txtSourcePath.removeAttribute('data-full-path');
            activeSourceFiles = [];
            
            if (folderInfo) folderInfo.style.display = 'none';
            if (fileList) fileList.innerHTML = '';

            if (mode === 'srt') {
                if (lblSourcePath) lblSourcePath.textContent = "Đường dẫn tệp SRT";
                if (txtSourcePath) txtSourcePath.placeholder = "Chọn file SRT nguồn từ hệ thống...";
            } else {
                if (lblSourcePath) lblSourcePath.textContent = "Đường dẫn thư mục SRT";
                if (txtSourcePath) txtSourcePath.placeholder = "Chọn thư mục chứa các file SRT...";
            }
            await updateStartButton();
        });
    });

    // 3. Source Picker Listener
    if (btnSelectSource) {
        btnSelectSource.addEventListener('click', async () => {
            const mode = Array.from(sourceRadios).find(r => r.checked)?.value || 'srt';
            btnSelectSource.disabled = true;

            try {
                if (mode === 'srt') {
                    const res = await api.selectSrtFile();
                    if (res.ok) {
                        const data = await res.json();
                        if (data.status === 'success' && data.path) {
                            txtSourcePath.value = truncatePath(data.path, 3);
                            txtSourcePath.setAttribute('data-full-path', data.path);
                            activeSourceFiles = [data.path];
                        }
                    }
                } else {
                    const res = await api.selectVideoFolder();
                    if (res.ok) {
                        const data = await res.json();
                        if (data.status === 'success' && data.path) {
                            txtSourcePath.value = truncatePath(data.path, 3);
                            txtSourcePath.setAttribute('data-full-path', data.path);
                            await handleFolderScan(data.path);
                        }
                    }
                }
            } catch (err) {
                alert("Lỗi hộp thoại chọn tệp/thư mục: " + err.message);
            } finally {
                btnSelectSource.disabled = false;
                await updateStartButton();
            }
        });
    }

    // 4. Start Batch Translation Listener
    if (btnStart) {
        btnStart.addEventListener('click', async () => {
            if (activeSourceFiles.length === 0) {
                alert("Không có file SRT nào được chọn để dịch.");
                return;
            }

            btnStart.disabled = true;
            const targetLang = selectLanguage.value;
            const profile = selectProfile.value;
            const concurrency = parseInt(selectConcurrency.value, 10);
            const chkTimeConstraint = document.getElementById('translate-time-constraint');
            const txtTargetWps = document.getElementById('translate-target-wps');

            const enableTimeConstraint = chkTimeConstraint ? chkTimeConstraint.checked : true;
            const targetWps = txtTargetWps ? (parseFloat(txtTargetWps.value) || 4.2) : 4.2;

            try {
                const res = await api.createTranslateBatch(
                    activeSourceFiles,
                    targetLang,
                    profile,
                    concurrency,
                    enableTimeConstraint,
                    targetWps
                );
                if (res.ok) {
                    const data = await res.json();
                    startQueuePolling(data.batch_id);
                } else {
                    const err = await res.json();
                    throw new Error(err.detail || "Lỗi phản hồi tạo lô dịch");
                }
            } catch (err) {
                alert("Lỗi khởi chạy lô dịch phụ đề: " + err.message);
            } finally {
                btnStart.disabled = false;
            }
        });
    }

    // Helpers
    async function updateProfilesUI() {
        try {
            profilesList = await api.fetchTranslateProfiles();
            if (selectProfile) {
                selectProfile.innerHTML = '<option value="">-- Chọn cấu hình dịch --</option>';
                profilesList.forEach(p => {
                    const opt = document.createElement('option');
                    opt.value = p.profile;
                    opt.textContent = p.label;
                    selectProfile.appendChild(opt);
                });
            }
        } catch (err) {
            console.error("Lỗi lấy danh sách cấu hình dịch profiles:", err);
        }
    }

    function openQuickKeyModal(provider, profileLabel) {
        const quickModal = document.getElementById('quick-key-modal');
        const txtInput = document.getElementById('quick-key-input');
        const chkPersist = document.getElementById('quick-key-persist');
        const btnSave = document.getElementById('btn-quick-key-save');
        const btnCancel = document.getElementById('btn-quick-key-cancel');
        const titleEl = document.getElementById('quick-key-title');
        const labelEl = document.getElementById('quick-key-label');
        
        if (!quickModal || !txtInput || !btnSave || !btnCancel) return;

        const providerObj = providersCatalog.find(p => p.id === provider);
        const displayName = providerObj ? providerObj.name : provider.toUpperCase();

        if (titleEl) titleEl.textContent = `Cấu hình API key cho ${displayName}`;
        if (labelEl) labelEl.textContent = "API key";

        txtInput.value = '';
        if (chkPersist) chkPersist.checked = false;
        
        quickModal.style.display = 'flex';

        // Clean event listeners to avoid memory leaks or duplicate handlers
        const cleanUp = () => {
            quickModal.style.display = 'none';
            btnSave.replaceWith(btnSave.cloneNode(true));
            btnCancel.replaceWith(btnCancel.cloneNode(true));
        };

        const onSave = async () => {
            const key = txtInput.value.trim();
            const persist = chkPersist ? chkPersist.checked : false;

            if (!key) {
                alert("Vui lòng nhập khoá API.");
                return;
            }

            btnSave.disabled = true;
            try {
                const res = await api.setTranslateCredentials(provider, key, persist);
                if (res.ok) {
                    alert(`Đã cấu hình khoá API cho ${displayName} thành công.`);
                    cleanUp();
                    await updateStartButton();
                } else {
                    const err = await res.json();
                    throw new Error(err.detail || "Không thể lưu khoá");
                }
            } catch (err) {
                alert("Lỗi lưu khoá API: " + err.message);
                btnSave.disabled = false;
            }
        };

        const onCancel = async () => {
            cleanUp();
            if (selectProfile) {
                selectProfile.value = ''; // reset back to placeholder
            }
            await updateStartButton();
        };

        // Fetch the fresh clones and bind
        const freshSaveBtn = document.getElementById('btn-quick-key-save');
        const freshCancelBtn = document.getElementById('btn-quick-key-cancel');
        
        freshSaveBtn.addEventListener('click', onSave);
        freshCancelBtn.addEventListener('click', onCancel);
    }

    async function handleFolderScan(folderPath) {
        if (!fileList || !folderCount || !folderInfo) return;

        fileList.innerHTML = '<div style="color: var(--text-muted); font-size: 0.8rem;">Đang quét thư mục...</div>';
        folderInfo.style.display = 'block';

        try {
            const res = await api.scanTranslateFolder(folderPath);
            if (res.ok) {
                const data = await res.json();
                activeSourceFiles = data.files || [];
                folderCount.textContent = activeSourceFiles.length;

                fileList.innerHTML = '';
                if (activeSourceFiles.length === 0) {
                    fileList.innerHTML = '<div style="color: #dc2626; font-weight: 600; font-size: 0.8rem;">Không tìm thấy file .srt trực tiếp nào.</div>';
                } else {
                    activeSourceFiles.forEach(f => {
                        const item = document.createElement('div');
                        item.className = 'translate-file-item';
                        item.textContent = truncatePath(f, 3);
                        item.title = f;
                        fileList.appendChild(item);
                    });
                }
            } else {
                throw new Error("Lỗi quét tệp");
            }
        } catch (err) {
            fileList.innerHTML = `<div style="color: #dc2626; font-weight: 600; font-size: 0.8rem;">Lỗi quét thư mục: ${err.message}</div>`;
            activeSourceFiles = [];
            folderCount.textContent = '0';
        }
    }

    async function updateStartButton() {
        if (!btnStart) return;

        const profileVal = selectProfile ? selectProfile.value : "";
        if (!profileVal || activeSourceFiles.length === 0) {
            btnStart.disabled = true;
            return;
        }

        const profileObj = (profilesList || []).find(p => p.profile === profileVal);
        if (!profileObj) {
            btnStart.disabled = true;
            return;
        }

        const provider = profileObj.provider || "gemini";
        try {
            const creds = await api.fetchTranslateCredentials(provider);
            btnStart.disabled = !creds.configured;
        } catch (err) {
            console.error("Lỗi kiểm tra credentials cho start button:", err);
            btnStart.disabled = true;
        }
    }
}
