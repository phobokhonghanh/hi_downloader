import * as api from './api.js';

export function initSettings() {
    const btnOpenSettings = document.getElementById('btn-open-settings');
    const modalSettings = document.getElementById('global-settings-modal');
    const btnCloseSettings = document.getElementById('btn-close-settings-modal');
    const paneBody = document.getElementById('settings-pane-body');

    if (btnOpenSettings && modalSettings) {
        btnOpenSettings.addEventListener('click', async () => {
            modalSettings.style.display = 'flex';
            await loadSettingsProviders();
        });
    }

    if (btnCloseSettings && modalSettings) {
        btnCloseSettings.addEventListener('click', () => {
            modalSettings.style.display = 'none';
        });
    }

    // Close settings modal if clicked outside card
    if (modalSettings) {
        modalSettings.addEventListener('click', (e) => {
            if (e.target === modalSettings) {
                modalSettings.style.display = 'none';
            }
        });
    }

    async function loadSettingsProviders() {
        if (!paneBody) return;
        paneBody.innerHTML = '<div style="color: var(--text-muted); font-size: 0.8rem;">Đang tải danh sách nhà cung cấp...</div>';

        try {
            const providers = await api.fetchTranslateProviders();
            const credentialsData = await api.fetchTranslateCredentials();
            const providersStatus = credentialsData.providers || {};

            paneBody.innerHTML = '';

            if (providers.length === 0) {
                paneBody.innerHTML = '<div style="color: var(--text-muted); font-size: 0.8rem;">Không có nhà cung cấp cấu hình dịch nào.</div>';
                return;
            }

            providers.forEach(p => {
                const status = providersStatus[p.id] || { configured: false, source: 'none', hint: '' };
                const row = renderProviderSettingsRow(p, status);
                paneBody.appendChild(row);
            });
        } catch (err) {
            paneBody.innerHTML = `<div style="color: #dc2626; font-size: 0.8rem; font-weight: 600;">Lỗi tải dữ liệu cấu hình: ${err.message}</div>`;
        }
    }

    function renderProviderSettingsRow(provider, status) {
        const container = document.createElement('div');
        container.style.border = '1px solid var(--panel-border)';
        container.style.borderRadius = 'var(--border-radius)';
        container.style.padding = '15px';
        container.style.background = '#f8fafc';
        container.style.display = 'flex';
        container.style.flexDirection = 'column';
        container.style.gap = '10px';

        let sourceLabel = "Chưa cấu hình";
        let sourceColor = "var(--text-muted)";
        if (status.configured) {
            sourceColor = "#16a34a";
            if (status.source === 'session') sourceLabel = "Đã cấu hình (Phiên làm việc)";
            else if (status.source === 'secret_service') sourceLabel = "Đã cấu hình (Hệ thống - Secret Service)";
            else if (status.source === 'environment') {
                sourceLabel = `Đã cấu hình từ biến môi trường (${provider.env_var})`;
                sourceColor = "#2563eb";
            }
        }

        container.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px;">
                <strong style="font-size: 0.85rem; color: var(--text-color);">${provider.name}</strong>
                <span class="provider-status-badge" style="font-size: 0.72rem; font-weight: 700; color: ${sourceColor};">${sourceLabel}</span>
            </div>
            
            <div class="form-group" style="margin-bottom: 0;">
                <label style="font-size: 0.72rem; margin-bottom: 4px; display: block;">API key</label>
                <div style="display: flex; gap: 8px; align-items: center;">
                    <input type="password" class="provider-key-input" style="flex: 1; padding: 6px 10px; font-size: 0.78rem;" 
                        placeholder="${status.configured ? '••••••••••••' : 'Nhập API key...'}" 
                        ${status.source === 'environment' ? 'disabled' : ''}>
                    
                    <button type="button" class="btn btn-outline-blue btn-toggle-reveal" title="Hiện khóa" aria-label="Hiện khóa" 
                        style="padding: 6px; height: 32px; display: flex; align-items: center; justify-content: center; width: 34px;"
                        ${status.source === 'environment' || !status.configured ? 'disabled' : ''}>
                        <svg class="icon-eye" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"></path>
                            <circle cx="12" cy="12" r="3"></circle>
                        </svg>
                    </button>
                </div>

                <div class="persist-container" style="margin-top: 8px; display: ${status.source === 'environment' ? 'none' : 'block'};">
                    <label style="display: flex; align-items: center; gap: 4px; font-weight: normal; cursor: pointer; font-size: 0.72rem; margin-bottom: 0;">
                        <input type="checkbox" class="provider-persist" ${status.source === 'secret_service' ? 'checked' : ''} style="cursor: pointer;">
                        Ghi nhớ khoá API lâu dài (OS Secret Service)
                    </label>
                </div>
            </div>

            <div style="display: flex; gap: 8px; margin-top: 5px; justify-content: flex-end;">
                ${status.source === 'environment' ? `
                    <button type="button" class="btn btn-outline-blue btn-override-env" style="padding: 5px 12px; font-size: 0.75rem;">Ghi đè khóa</button>
                ` : ''}
                <button type="button" class="btn btn-solid-blue btn-save-provider" disabled style="padding: 5px 12px; font-size: 0.75rem;">Lưu</button>
                <button type="button" class="btn btn-outline-blue btn-test-provider" ${!status.configured ? 'disabled' : ''} style="padding: 5px 12px; font-size: 0.75rem;">Kiểm tra</button>
                <button type="button" class="btn btn-outline-blue btn-delete-provider" style="padding: 5px 12px; font-size: 0.75rem; color: #dc2626; border-color: #fca5a5; display: ${status.source === 'environment' || !status.configured ? 'none' : 'block'};">Xoá</button>
            </div>
        `;

        // Bind interactive elements
        const input = container.querySelector('.provider-key-input');
        const btnReveal = container.querySelector('.btn-toggle-reveal');
        const chkPersist = container.querySelector('.provider-persist');
        const btnSave = container.querySelector('.btn-save-provider');
        const btnTest = container.querySelector('.btn-test-provider');
        const btnDelete = container.querySelector('.btn-delete-provider');
        const btnOverride = container.querySelector('.btn-override-env');

        let originalKeyRevealed = null;

        if (input && btnSave) {
            input.addEventListener('input', () => {
                btnSave.disabled = !input.value.trim();
            });
        }

        if (btnOverride) {
            btnOverride.addEventListener('click', () => {
                input.removeAttribute('disabled');
                input.placeholder = "Nhập khoá API ghi đè...";
                input.focus();
                btnOverride.style.display = 'none';
                const persistDiv = container.querySelector('.persist-container');
                if (persistDiv) persistDiv.style.display = 'block';
            });
        }

        if (btnReveal && input) {
            btnReveal.addEventListener('click', async () => {
                if (input.type === 'password') {
                    if (originalKeyRevealed !== null) {
                        input.value = originalKeyRevealed;
                        input.type = 'text';
                        btnReveal.title = "Ẩn khóa";
                    } else {
                        btnReveal.disabled = true;
                        try {
                            const res = await api.revealTranslateCredentials(provider.id);
                            if (res.ok) {
                                const data = await res.json();
                                originalKeyRevealed = data.api_key;
                                input.value = originalKeyRevealed;
                                input.type = 'text';
                                btnReveal.title = "Ẩn khóa";
                            } else {
                                alert("Không thể giải mã/tiết lộ khóa API.");
                            }
                        } catch (err) {
                            alert("Lỗi tiết lộ khóa: " + err.message);
                        } finally {
                            btnReveal.disabled = false;
                        }
                    }
                } else {
                    input.type = 'password';
                    input.value = '';
                    input.placeholder = "••••••••••••";
                    btnReveal.title = "Hiện khóa";
                }
            });
        }

        if (btnSave && input) {
            btnSave.addEventListener('click', async () => {
                const key = input.value.trim();
                const persist = chkPersist ? chkPersist.checked : false;
                if (!key) return;

                btnSave.disabled = true;
                try {
                    const res = await api.setTranslateCredentials(provider.id, key, persist);
                    if (res.ok) {
                        alert(`Đã lưu cấu hình khóa API cho ${provider.name} thành công.`);
                        await loadSettingsProviders();
                    } else {
                        const err = await res.json();
                        throw new Error(err.detail || "Không thể lưu");
                    }
                } catch (err) {
                    alert("Lỗi lưu khóa: " + err.message);
                    btnSave.disabled = false;
                }
            });
        }

        if (btnTest) {
            btnTest.addEventListener('click', async () => {
                btnTest.disabled = true;
                try {
                    const res = await api.testTranslateCredentials(provider.id);
                    if (res.ok) {
                        alert(`Kết nối thử đến ${provider.name} thành công!`);
                    } else {
                        const err = await res.json();
                        throw new Error(err.detail || "Kết nối thử thất bại");
                    }
                } catch (err) {
                    alert(`Lỗi kiểm thử khóa ${provider.name}: ` + err.message);
                } finally {
                    btnTest.disabled = false;
                }
            });
        }

        if (btnDelete) {
            btnDelete.addEventListener('click', async () => {
                if (!confirm(`Bạn có chắc chắn muốn xóa khóa API cấu hình của ${provider.name} không?`)) {
                    return;
                }
                btnDelete.disabled = true;
                try {
                    const res = await api.deleteTranslateCredentials(provider.id);
                    if (res.ok) {
                        alert(`Đã xóa cấu hình khóa cho ${provider.name}.`);
                        await loadSettingsProviders();
                    } else {
                        throw new Error("Xóa cấu hình thất bại");
                    }
                } catch (err) {
                    alert("Lỗi xóa cấu hình: " + err.message);
                    btnDelete.disabled = false;
                }
            });
        }

        return container;
    }
}
