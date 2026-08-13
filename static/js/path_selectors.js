import { truncatePath } from './helpers.js';
import * as api from './api.js';

const getBtnSelectDir = () => document.getElementById('btn-select-dir');
const getCustomOutputDir = () => document.getElementById('custom-output-dir');
const getBtnSelectProxy = () => document.getElementById('btn-select-proxy');
const getBtnClearProxy = () => document.getElementById('btn-clear-proxy');
const getCustomProxyFile = () => document.getElementById('custom-proxy-file');

export function updateDirDisplay(fullPath) {
    if (!fullPath) return;
    const customOutputDir = getCustomOutputDir();
    if (customOutputDir) {
        customOutputDir.dataset.fullPath = fullPath;
        customOutputDir.value = truncatePath(fullPath, 3);
        customOutputDir.title = fullPath;
    }
}

export function updateProxyDisplay(customPath, systemPath, proxyMode, proxyDisabled) {
    const checkboxDisabled = document.getElementById('proxy-disabled-checkbox');
    const customProxyFile = getCustomProxyFile();
    const btnSelectProxy = getBtnSelectProxy();
    const btnClearProxy = getBtnClearProxy();

    if (checkboxDisabled) {
        checkboxDisabled.checked = !!proxyDisabled;
    }

    if (!customProxyFile) return;

    // Display the custom path if configured, else fallback to system path informationally
    if (customPath) {
        customProxyFile.dataset.fullPath = customPath;
        customProxyFile.value = truncatePath(customPath, 3);
        customProxyFile.title = customPath;
    } else if (systemPath) {
        customProxyFile.dataset.fullPath = systemPath;
        customProxyFile.value = truncatePath(systemPath, 3);
        customProxyFile.title = systemPath;
    } else {
        customProxyFile.dataset.fullPath = '';
        customProxyFile.value = '';
        customProxyFile.placeholder = 'Dùng proxy system mặc định';
        customProxyFile.title = '';
    }

    // Disable controls if bypass is checked
    if (proxyDisabled) {
        if (btnSelectProxy) btnSelectProxy.disabled = true;
        if (btnClearProxy) btnClearProxy.disabled = true;
    } else {
        if (btnSelectProxy) btnSelectProxy.disabled = false;
        // Only enable clear if there is a custom path to clear
        if (btnClearProxy) btnClearProxy.disabled = !customPath;
    }
}

export async function checkSystem() {
    try {
        const data = await api.fetchSystem();
        updateDirDisplay(data.download_dir);
        updateProxyDisplay(data.proxy_file, data.system_proxy_file, data.proxy_mode, data.proxy_disabled);
    } catch (err) {
        console.error("Lỗi quét hệ thống:", err);
    }
}

export function initSelectors() {
    const btnSelectDir = getBtnSelectDir();
    const btnSelectProxy = getBtnSelectProxy();
    const btnClearProxy = getBtnClearProxy();

    // OS directory selection click handler
    if (btnSelectDir) {
        btnSelectDir.addEventListener('click', async () => {
            const currentBtn = getBtnSelectDir();
            if (currentBtn) currentBtn.disabled = true;
            try {
                const res = await api.selectDirectory();
                if (res.ok) {
                    const data = await res.json();
                    if (data.status === 'success' && data.path) {
                        updateDirDisplay(data.path);
                    }
                } else {
                    let errMsg = "Lỗi không xác định";
                    try {
                        const err = await res.json();
                        errMsg = err.message || err.detail || JSON.stringify(err);
                    } catch (e) {
                        errMsg = await res.text();
                    }
                    alert("Không thể chọn thư mục: " + errMsg);
                }
            } catch (e) {
                alert("Lỗi kết nối hộp thoại chọn thư mục.");
            } finally {
                const currentBtn = getBtnSelectDir();
                if (currentBtn) currentBtn.disabled = false;
            }
        });
    }

    if (btnSelectProxy) {
        btnSelectProxy.addEventListener('click', async () => {
            const currentBtn = getBtnSelectProxy();
            if (currentBtn) currentBtn.disabled = true;
            try {
                const res = await api.selectProxyFile();
                if (res.ok) {
                    const data = await res.json();
                    if (data.status === 'success' && data.path) {
                        await checkSystem();
                    }
                } else {
                    let errMsg = "Lỗi không xác định";
                    try {
                        const err = await res.json();
                        errMsg = err.message || err.detail || JSON.stringify(err);
                    } catch (e) {
                        errMsg = await res.text();
                    }
                    alert("Không thể chọn file proxy: " + errMsg);
                }
            } catch (e) {
                alert("Lỗi kết nối hộp thoại chọn file proxy.");
            } finally {
                const currentBtn = getBtnSelectProxy();
                if (currentBtn) currentBtn.disabled = false;
            }
        });
    }

    if (btnClearProxy) {
        btnClearProxy.addEventListener('click', async () => {
            const currentBtn = getBtnClearProxy();
            if (currentBtn) currentBtn.disabled = true;
            try {
                const res = await api.clearProxyFile();
                if (res.ok) {
                    await checkSystem();
                } else {
                    alert("Không thể xóa proxy cá nhân.");
                }
            } catch (e) {
                alert("Lỗi kết nối xóa proxy cá nhân.");
            } finally {
                const currentBtn = getBtnClearProxy();
                if (currentBtn) currentBtn.disabled = false;
            }
        });
    }

    // Proxy mode checkbox listener
    const checkboxDisabled = document.getElementById('proxy-disabled-checkbox');
    if (checkboxDisabled) {
        checkboxDisabled.addEventListener('change', async (event) => {
            const isDisabled = event.target.checked;
            try {
                await api.setProxyDisabled(isDisabled);
                await checkSystem();
            } catch (err) {
                alert("Lỗi thiết lập chế độ proxy: " + err);
            }
        });
    }
}
