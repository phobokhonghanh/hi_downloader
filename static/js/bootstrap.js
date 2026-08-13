// Startup helper elements
const startupLoading = document.getElementById('startup-loading');
const startupError = document.getElementById('startup-error');
const startupErrorMessage = document.getElementById('startup-error-message');
const btnStartupRetry = document.getElementById('btn-startup-retry');

if (btnStartupRetry) {
    btnStartupRetry.addEventListener('click', () => {
        window.location.reload();
    });
}

(async () => {
    try {
        // 1. Fetch fragments in parallel
        const [resDownloader, resSubtitle, resTranslate] = await Promise.all([
            fetch('/static/fragments/downloader.html'),
            fetch('/static/fragments/subtitle.html'),
            fetch('/static/fragments/translate.html')
        ]);

        if (!resDownloader.ok) {
            throw new Error(`Không thể tải downloader.html (Mã phản hồi: ${resDownloader.status})`);
        }
        if (!resSubtitle.ok) {
            throw new Error(`Không thể tải subtitle.html (Mã phản hồi: ${resSubtitle.status})`);
        }
        if (!resTranslate.ok) {
            throw new Error(`Không thể tải translate.html (Mã phản hồi: ${resTranslate.status})`);
        }

        const downloaderHtml = await resDownloader.text();
        const subtitleHtml = await resSubtitle.text();
        const translateHtml = await resTranslate.text();

        // 2. Mount fragments into DOM tree
        const downloaderView = document.getElementById('downloader-view');
        const subtitleView = document.getElementById('subtitle-view');
        const translateView = document.getElementById('translate-view');

        if (downloaderView) downloaderView.innerHTML = downloaderHtml;
        if (subtitleView) subtitleView.innerHTML = subtitleHtml;
        if (translateView) translateView.innerHTML = translateHtml;

        // 3. Dynamically import modules after DOM is ready to prevent top-level query selector failures
        const version = '2';
        const { state } = await import(`./state.js?v=${version}`);
        const api = await import(`./api.js?v=${version}`);
        const { initSelectors, checkSystem } = await import(`./path_selectors.js?v=${version}`);
        const { initAnalyzeHistory, loadHistory, registerFinalLogsUpdate } = await import(`./analyze_history.js?v=${version}`);
        const { initDownload } = await import(`./download.js?v=${version}`);
        const { initTasks, updateTasksUI } = await import(`./tasks.js?v=${version}`);
        const { initLogs, updateLogsUI } = await import(`./logs.js?v=${version}`);
        const { initSubtitle } = await import(`./subtitle.js?v=${version}`);
        const { initTranslate } = await import(`./translate.js?v=${version}`);
        const { initSettings } = await import(`./settings.js?v=${version}`);
        const { triggerTaskPolling, triggerLogPolling } = await import(`./polling.js?v=${version}`);

        // 4. Initialize elements and listeners
        initSelectors();
        initAnalyzeHistory();
        initDownload();
        initTasks();
        initLogs();
        // Start the single independent log polling loop immediately after logs init
        triggerLogPolling();

        initSubtitle();
        initTranslate();
        initSettings();

        // 5. Connect sidebar navigation
        const btnModeDownload = document.getElementById('btn-mode-download');
        const btnModeSubtitle = document.getElementById('btn-mode-subtitle');
        const btnModeTranslate = document.getElementById('btn-mode-translate');

        if (btnModeDownload && btnModeSubtitle && btnModeTranslate && downloaderView && subtitleView && translateView) {
            btnModeDownload.addEventListener('click', () => {
                btnModeDownload.classList.add('active');
                btnModeSubtitle.classList.remove('active');
                btnModeTranslate.classList.remove('active');
                downloaderView.style.display = 'grid';
                subtitleView.style.display = 'none';
                translateView.style.display = 'none';
            });

            btnModeSubtitle.addEventListener('click', () => {
                btnModeSubtitle.classList.add('active');
                btnModeDownload.classList.remove('active');
                btnModeTranslate.classList.remove('active');
                downloaderView.style.display = 'none';
                subtitleView.style.display = 'grid';
                translateView.style.display = 'none';
            });

            btnModeTranslate.addEventListener('click', () => {
                btnModeTranslate.classList.add('active');
                btnModeDownload.classList.remove('active');
                btnModeSubtitle.classList.remove('active');
                downloaderView.style.display = 'none';
                subtitleView.style.display = 'none';
                translateView.style.display = 'grid';
            });
        }

        // Connect analysis final logs update callback
        registerFinalLogsUpdate(async () => {
            try {
                const logs = await api.fetchLogs();
                updateLogsUI(logs);
            } catch (e) {
                console.error("Lỗi cập nhật logs sau phân tích:", e);
            }
        });

        // 6. Scan initial configurations
        await checkSystem();
        loadHistory();

        // Render initial tasks/logs lists
        const tasks = await api.fetchTasks();
        state.allTasks = tasks;
        updateTasksUI(tasks);

        try {
            const logs = await api.fetchLogs();
            updateLogsUI(logs);
        } catch (e) {
            console.error("Lỗi fetchLogs ban đầu:", e);
            updateLogsUI({ error: true });
        }
        
        const activeStatuses = ['pending', 'downloading', 'merging', 'processing'];
        const hasActive = state.allTasks.some(t => activeStatuses.includes(t.status));
        if (hasActive) {
            triggerTaskPolling();
        }

        // Hide loading state and display default view
        if (startupLoading) startupLoading.style.display = 'none';
        if (downloaderView) downloaderView.style.display = 'grid';

    } catch (err) {
        console.error("Lỗi khởi tạo ứng dụng:", err);
        if (startupLoading) startupLoading.style.display = 'none';
        if (startupError) startupError.style.display = 'flex';
        if (startupErrorMessage) startupErrorMessage.textContent = err.message || err;
    }
})();
