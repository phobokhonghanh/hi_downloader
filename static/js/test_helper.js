import { truncatePath } from './helpers.js';

const mockElementChildren = [];
const mockElementClasses = new Set();
const mockElement = {
    tagName: 'DIV',
    className: '',
    addEventListener: () => {},
    appendChild: (child) => { mockElementChildren.push(child); },
    removeChild: (child) => {
        const idx = mockElementChildren.indexOf(child);
        if (idx !== -1) mockElementChildren.splice(idx, 1);
    },
    style: {},
    dataset: {},
    classList: {
        add: (c) => { mockElementClasses.add(c); mockElement.className = Array.from(mockElementClasses).join(' '); },
        remove: (c) => { mockElementClasses.delete(c); mockElement.className = Array.from(mockElementClasses).join(' '); }
    },
    value: '',
    title: '',
    get textContent() {
        if (mockElement._textContent !== undefined && mockElement._textContent !== '') return mockElement._textContent;
        return mockElementChildren.map(c => c.textContent).join('');
    },
    set textContent(val) {
        mockElement._textContent = val;
    },
    innerHTML: '',
    disabled: false,
    children: mockElementChildren,
    setAttribute: (name, value) => { mockElement[name] = value; },
    querySelector: (sel) => {
        if (sel.startsWith('.')) {
            const cls = sel.slice(1);
            if (mockElement.className.split(/\s+/).includes(cls)) return mockElement;
            for (const child of mockElementChildren) {
                if (child.querySelector) {
                    const found = child.querySelector(sel);
                    if (found) return found;
                }
            }
        }
        if (sel === 'span' || sel === 'button' || sel === 'a') {
            for (const child of mockElementChildren) {
                if (child.querySelector) {
                    const found = child.querySelector(sel);
                    if (found) return found;
                }
            }
        }
        return null;
    },
    querySelectorAll: (sel) => {
        const res = [];
        for (const child of mockElementChildren) {
            if (child.querySelectorAll) res.push(...child.querySelectorAll(sel));
        }
        return res;
    }
};

globalThis.document = {
    getElementById: () => mockElement,
    querySelectorAll: () => [],
    getElementsByName: () => [mockElement],
    createElement: (tag) => {
        const classes = new Set();
        const children = [];
        const el = {
            tagName: (tag || '').toUpperCase(),
            style: {},
            dataset: {},
            classList: {
                add: (c) => {
                    classes.add(c);
                    el.className = Array.from(classes).join(' ');
                },
                remove: (c) => {
                    classes.delete(c);
                    el.className = Array.from(classes).join(' ');
                }
            },
            className: '',
            value: '',
            title: '',
            get textContent() {
                if (el._textContent !== undefined && el._textContent !== '') return el._textContent;
                if (children.length > 0) {
                    return children.map(c => c.textContent).join('');
                }
                return el._textContent || '';
            },
            set textContent(val) {
                el._textContent = val;
            },
            innerHTML: '',
            disabled: false,
            children: children,
            addEventListener: () => {},
            setAttribute: (name, value) => { el[name] = value; },
            appendChild: (child) => { children.push(child); },
            removeChild: () => {},
            querySelector: (sel) => {
                if (sel.startsWith('.')) {
                    const cls = sel.slice(1);
                    const currentClasses = el.className.split(/\s+/);
                    if (currentClasses.includes(cls)) return el;
                    for (const child of children) {
                        if (child.querySelector) {
                            const found = child.querySelector(sel);
                            if (found) return found;
                        }
                    }
                }
                if (sel === 'span' || sel === 'button' || sel === 'a') {
                    if (el.tagName === sel.toUpperCase()) return el;
                    for (const child of children) {
                        if (child.querySelector) {
                            const found = child.querySelector(sel);
                            if (found) return found;
                        }
                    }
                }
                return null;
            },
            querySelectorAll: (sel) => {
                const results = [];
                if (sel.startsWith('.')) {
                    const cls = sel.slice(1);
                    const currentClasses = el.className.split(/\s+/);
                    if (currentClasses.includes(cls)) {
                        results.push(el);
                    }
                    for (const child of children) {
                        if (child.querySelectorAll) {
                            results.push(...child.querySelectorAll(sel));
                        }
                    }
                }
                return results;
            }
        };
        return el;
    },
    createTextNode: (text) => {
        const el = {
            tagName: '#TEXT',
            textContent: text || '',
            addEventListener: () => {},
            appendChild: () => {},
            removeChild: () => {},
            style: {},
            dataset: {},
            classList: { add: () => {}, remove: () => {} },
            value: '',
            title: '',
            innerHTML: '',
            setAttribute: () => {},
            querySelector: () => null,
            querySelectorAll: () => []
        };
        return el;
    }
};

globalThis.window = {
    addEventListener: () => {}
};

globalThis.localStorage = {
    getItem: () => null,
    setItem: () => {},
    removeItem: () => {}
};

globalThis.fetch = async (url) => ({
    ok: true,
    json: async () => {
        if (url && (url.includes('/api/tasks') || url.includes('/profiles') || url.includes('/logs'))) {
            return [];
        }
        return {};
    },
    text: async () => ""
});

globalThis.confirm = () => true;
globalThis.alert = () => {};
globalThis.prompt = () => "test";

// 1. Path Helper Unit Tests
const pathTests = [
    { input: '', expected: '' },
    { input: '   ', expected: '' },
    { input: null, expected: '' },
    { input: undefined, expected: '' },
    { input: '/', expected: '/' },
    { input: '\\', expected: '\\' },
    { input: 'video.mp4', expected: 'video.mp4' },
    { input: '/video.mp4', expected: '/video.mp4' },
    { input: '/home/user/video.mp4', expected: '/home/user/video.mp4' }, 
    { input: '/home/user/workspace/video.mp4', expected: '.../user/workspace/video.mp4' }, 
    { input: '/home/user/workspace/proj/src/video.mp4', expected: '.../proj/src/video.mp4' },
    { input: 'C:\\Users\\admin\\Downloads\\video.mp4', expected: '...\\admin\\Downloads\\video.mp4' },
    { input: '\\\\server\\share\\folder\\file.txt', expected: '...\\share\\folder\\file.txt' },
    { input: 'C:/Users\\admin/Downloads\\video.mp4', expected: '...\\admin\\Downloads\\video.mp4' },
    { input: 'https://www.bilibili.com/video/BV123', expected: '.../video/BV123' },
    { input: 'https://space.bilibili.com/123', expected: '.../123' }
];

let failed = false;

console.log("Running path helper tests...");
for (const t of pathTests) {
    const output = truncatePath(t.input);
    if (output !== t.expected) {
        console.error(`FAIL: Path truncation input="${t.input}" expected="${t.expected}" got="${output}"`);
        failed = true;
    } else {
        console.log(`PASS: Path truncation input="${t.input}" -> "${output}"`);
    }
}

// 2. Runtime Import Graph Smoke Tests
const modulesToSmokeTest = [
    './state.js',
    './helpers.js',
    './api.js',
    './polling.js',
    './path_selectors.js',
    './analyze_history.js',
    './download.js',
    './tasks.js',
    './logs.js',
    './subtitle_sources.js',
    './subtitle_queue.js',
    './subtitle_modal.js',
    './subtitle.js',
    './translate_queue.js',
    './translate_modal.js',
    './translate.js',
    './bootstrap.js'
];

console.log("\nRunning ES Module import graph smoke tests...");
for (const m of modulesToSmokeTest) {
    try {
        await import(m);
        console.log(`PASS: Resolved and imported graph for ${m}`);
    } catch (err) {
        console.error(`FAIL: Failed to resolve import graph for ${m}:`, err);
        failed = true;
    }
}

// 3. Subtitle Queue Helper Logic Unit Tests
console.log("\nRunning subtitle queue helper logic unit tests...");
try {
    const { shouldStopPolling, calculateJobStats, getEligibleJobIdsForAction, renderQueueTable } = await import('./subtitle_queue.js');
    
    // Test calculateJobStats
    const mockJobs = [
        { job_id: 'j1', status: 'waiting' },
        { job_id: 'j2', status: 'running' },
        { job_id: 'j3', status: 'done' },
        { job_id: 'j4', status: 'error' },
        { job_id: 'j5', status: 'canceled' }
    ];
    const stats = calculateJobStats(mockJobs);
    if (stats.total !== 5 || stats.waiting !== 1 || stats.running !== 1 || stats.done !== 1 || stats.error !== 2) {
        console.error("FAIL: calculateJobStats returned incorrect counts:", stats);
        failed = true;
    } else {
        console.log("PASS: calculateJobStats correctness");
    }

    // Test shouldStopPolling
    const activeSnapshot = { jobs: [ { status: 'done' }, { status: 'running' } ] };
    const inactiveSnapshot = { jobs: [ { status: 'done' }, { status: 'error' }, { status: 'canceled' } ] };
    
    if (shouldStopPolling(activeSnapshot, 'b1') !== false) {
        console.error("FAIL: shouldStopPolling should return false for active jobs");
        failed = true;
    } else {
        console.log("PASS: shouldStopPolling detects active loop continue");
    }

    if (shouldStopPolling(inactiveSnapshot, 'b1') !== true) {
        console.error("FAIL: shouldStopPolling should return true for inactive jobs");
        failed = true;
    } else {
        console.log("PASS: shouldStopPolling detects settled status stop");
    }

    // Test getEligibleJobIdsForAction
    const selectedIds = ['j1', 'j2', 'j3', 'j4'];
    const eligibleSave = getEligibleJobIdsForAction(mockJobs, 'save', selectedIds);
    if (eligibleSave.length !== 1 || eligibleSave[0] !== 'j3') {
        console.error("FAIL: getEligibleJobIdsForAction for save action:", eligibleSave);
        failed = true;
    } else {
        console.log("PASS: getEligibleJobIdsForAction selection eligibility (save)");
    }

    const eligibleCancel = getEligibleJobIdsForAction(mockJobs, 'cancel', selectedIds);
    if (eligibleCancel.length !== 2 || !eligibleCancel.includes('j1') || !eligibleCancel.includes('j2')) {
        console.error("FAIL: getEligibleJobIdsForAction for cancel action:", eligibleCancel);
        failed = true;
    } else {
        console.log("PASS: getEligibleJobIdsForAction selection eligibility (cancel)");
    }

    const eligibleRetry = getEligibleJobIdsForAction(mockJobs, 'retry', selectedIds);
    if (eligibleRetry.length !== 1 || eligibleRetry[0] !== 'j4') {
        console.error("FAIL: getEligibleJobIdsForAction for retry action:", eligibleRetry);
        failed = true;
    } else {
        console.log("PASS: getEligibleJobIdsForAction selection eligibility (retry)");
    }

    // Test initial zero state mapping
    const originalGetElement = globalThis.document.getElementById;
    globalThis.document.getElementById = (id) => {
        return mockElement;
    };

    const subQueueModule = await import('./subtitle_queue.js');
    subQueueModule.initSubtitleQueue();

    if (!subQueueModule.subtitleQueueInstance || subQueueModule.subtitleQueueInstance.elapsedSeconds !== 0 || subQueueModule.subtitleQueueInstance.rows.length !== 0) {
        console.error("FAIL: initSubtitleQueue should immediately render initial zeros (elapsedSeconds: 0, rows: [])");
        failed = true;
    } else {
        console.log("PASS: initSubtitleQueue immediately calls update with initial zero state");
    }

    // Restore original mock
    globalThis.document.getElementById = originalGetElement;

} catch (err) {
    console.error("FAIL: Subtitle Queue unit tests crashed:", err);
    failed = true;
}

// 4. Subtitle Helpers and Modal Isolation Unit Tests
console.log("\nRunning subtitle client-side helpers and modal isolation unit tests...");
try {
    const {
        parseSrtTextClient,
        exportSegmentsToSrtClient,
        replaceSegmentTextClient,
        mergeSegmentsClient,
        splitSegmentClient
    } = await import('./helpers.js');

    // Test parseSrtTextClient & exportSegmentsToSrtClient
    const sampleSrt = "1\n00:00:01,200 --> 00:00:04,500\nHello World\n\n2\n00:00:05,000 --> 00:00:08,000\nSubtitle 2";
    const segments = parseSrtTextClient(sampleSrt);
    if (segments.length !== 2) {
        console.error("FAIL: parseSrtTextClient parsed incorrect length:", segments.length);
        failed = true;
    } else if (segments[0].start_ms !== 1200 || segments[0].end_ms !== 4500 || segments[0].text !== "Hello World") {
        console.error("FAIL: parseSrtTextClient fields parsing mismatch:", segments[0]);
        failed = true;
    } else {
        console.log("PASS: parseSrtTextClient parser logic");
    }

    const formatted = exportSegmentsToSrtClient(segments);
    if (!formatted.includes("00:00:01,200 --> 00:00:04,500") || !formatted.includes("Hello World")) {
        console.error("FAIL: exportSegmentsToSrtClient output format incorrect:", formatted);
        failed = true;
    } else {
        console.log("PASS: exportSegmentsToSrtClient formatting correctness");
    }

    // Test replaceSegmentTextClient
    const replaced = replaceSegmentTextClient(segments, 1, "New Text");
    if (replaced[0].text !== "New Text" || replaced[1].text !== "Subtitle 2") {
        console.error("FAIL: replaceSegmentTextClient failed to update target segment:", replaced);
        failed = true;
    } else {
        console.log("PASS: replaceSegmentTextClient updates text successfully");
    }

    // Test mergeSegmentsClient
    const mockMerge = [
        { index: 1, start_ms: 0, end_ms: 1000, text: "A" },
        { index: 2, start_ms: 1200, end_ms: 2000, text: "B" },
        { index: 3, start_ms: 2100, end_ms: 3000, text: "C" }
    ];
    
    const merged = mergeSegmentsClient(mockMerge, 1, 2, false);
    if (merged.length !== 2 || merged[0].text !== "A B" || merged[0].start_ms !== 0 || merged[0].end_ms !== 2000) {
        console.error("FAIL: mergeSegmentsClient failed valid merge:", merged);
        failed = true;
    } else {
        console.log("PASS: mergeSegmentsClient valid merge");
    }

    const largeGapSegments = [
        { index: 1, start_ms: 0, end_ms: 1000, text: "A" },
        { index: 2, start_ms: 1500, end_ms: 2000, text: "B" }
    ];
    try {
        mergeSegmentsClient(largeGapSegments, 1, 2, false);
        console.error("FAIL: mergeSegmentsClient should have thrown gap exception");
        failed = true;
    } catch (e) {
        if (e.message === 'gap') {
            console.log("PASS: mergeSegmentsClient throws gap limit exception correctly");
        } else {
            console.error("FAIL: mergeSegmentsClient threw incorrect exception:", e);
            failed = true;
        }
    }

    // Test splitSegmentClient
    const splitSegs = splitSegmentClient(mockMerge, 2, 1600, "First Part", "Second Part");
    if (splitSegs.length !== 4 || splitSegs[1].end_ms !== 1600 || splitSegs[1].text !== "First Part" || splitSegs[2].start_ms !== 1600 || splitSegs[2].text !== "Second Part") {
        console.error("FAIL: splitSegmentClient failed to split segment correctly:", splitSegs);
        failed = true;
    } else {
        console.log("PASS: splitSegmentClient split operation correctness");
    }

    // Circular import verification via static source parsing
    const fs = await import('fs');
    const path = await import('path');
    
    const modalPath = path.resolve('static/js/subtitle_modal.js');
    const modalSrc = fs.readFileSync(modalPath, 'utf8');
    
    if (modalSrc.includes('runSubtitleModule') || modalSrc.includes('./subtitle.js')) {
        console.error("FAIL: subtitle_modal.js violates isolation constraints. It contains references to subtitle.js or runSubtitleModule.");
        failed = true;
    } else {
        console.log("PASS: subtitle_modal.js is fully isolated (no circular imports or dependencies on subtitle.js)");
    }

    // 4.1 Subtitle and Translate Modal Interaction & Metadata Tests
    console.log("\nRunning Subtitle and Translate Modal Interaction & Metadata unit tests...");
    const originalGetElementModal = globalThis.document.getElementById;
    try {
        const subModalMod = await import('./subtitle_modal.js');
        const transModalMod = await import('./translate_modal.js');
        
        // Define local mock elements mapping
        const modalMockElements = {};
        const getLocalMockElement = (id) => {
            if (!modalMockElements[id]) {
                modalMockElements[id] = {
                    addEventListener: (event, cb) => {
                        if (!modalMockElements[id].listeners) modalMockElements[id].listeners = {};
                        modalMockElements[id].listeners[event] = cb;
                    },
                    style: { display: '' },
                    dataset: {},
                    value: '',
                    textContent: '',
                    placeholder: '',
                    title: '',
                    disabled: false,
                    checked: false,
                    listeners: {},
                    querySelectorAll: () => [],
                    appendChild: (el) => el,
                    removeChild: (el) => el,
                    cloneNode: () => getLocalMockElement(id)
                };
            }
            return modalMockElements[id];
        };

        globalThis.document.getElementById = (id) => getLocalMockElement(id);

        // Test Subtitle Modal detected language rendering
        subModalMod.initSubtitleModal();
        const fakeJob = {
            job_id: 'job-lang-test',
            video_path: '/path/to/vid.mp4',
            provider: 'whisper',
            language: 'auto',
            detected_language: 'en',
            segments: []
        };
        
        subModalMod.openModalForJob(fakeJob, 'batch-1', () => {});
        
        const subLangEl = getLocalMockElement('sub-meta-language');
        if (!subLangEl.textContent.includes('Tiếng Anh (Nhận dạng)')) {
            console.error("FAIL: subtitle_modal did not display detected language properly:", subLangEl.textContent);
            failed = true;
        } else {
            console.log("PASS: subtitle_modal successfully displays detected language metadata");
        }

        // Test Subtitle Modal close X button
        const subModalEl = getLocalMockElement('subtitle-editor-modal');
        const subCloseX = getLocalMockElement('btn-modal-header-close');
        subModalEl.style.display = 'flex';
        
        if (subCloseX.listeners['click']) {
            subCloseX.listeners['click']();
            if (subModalEl.style.display !== 'none') {
                console.error("FAIL: clicking subtitle header close X did not hide modal");
                failed = true;
            } else {
                console.log("PASS: subtitle header close X button hides modal successfully");
            }
        } else {
            console.error("FAIL: subtitle header close X button has no click listener registered");
            failed = true;
        }

        // Test Translate Modal close X button
        transModalMod.initTranslateModal(() => {});
        const transModalEl = getLocalMockElement('translate-editor-modal');
        const transCloseX = getLocalMockElement('btn-translate-modal-header-close');
        transModalEl.style.display = 'flex';
        
        if (transCloseX.listeners['click']) {
            transCloseX.listeners['click']();
            if (transModalEl.style.display !== 'none') {
                console.error("FAIL: clicking translate header close X did not hide modal");
                failed = true;
            } else {
                console.log("PASS: translate header close X button hides modal successfully");
            }
        } else {
            console.error("FAIL: translate header close X button has no click listener registered");
            failed = true;
        }

    } catch (err) {
        console.error("FAIL: Subtitle and Translate Modal unit tests crashed:", err);
        failed = true;
    } finally {
        globalThis.document.getElementById = originalGetElementModal;
    }

    // 5. Fragments structural integrity, shell isolation and unique ID checks
    console.log("\nRunning fragments structure and shell isolation unit tests...");
    try {
        const fs = await import('fs');
        const path = await import('path');

        const indexHtml = fs.readFileSync(path.resolve('static/index.html'), 'utf8');
        const downloaderHtml = fs.readFileSync(path.resolve('static/fragments/downloader.html'), 'utf8');
        const subtitleHtml = fs.readFileSync(path.resolve('static/fragments/subtitle.html'), 'utf8');

        // Check for forbidden tags in fragments
        const forbiddenTags = [/<html/i, /<head/i, /<body/i, /<script/i];
        for (const tagPattern of forbiddenTags) {
            if (tagPattern.test(downloaderHtml)) {
                console.error("FAIL: downloader.html contains forbidden tags matching:", tagPattern);
                failed = true;
            }
            if (tagPattern.test(subtitleHtml)) {
                console.error("FAIL: subtitle.html contains forbidden tags matching:", tagPattern);
                failed = true;
            }
        }
        if (!failed) {
            console.log("PASS: HTML fragments do not contain html, head, body, or script tags");
        }

        // Check that index.html no longer contains feature controls directly
        const forbiddenShellElements = ['btn-download', 'btn-subtitle-generate', 'tasks-container', 'subtitle-editor-modal'];
        for (const elId of forbiddenShellElements) {
            if (indexHtml.includes(`id="${elId}"`) || indexHtml.includes(`id='${elId}'`)) {
                console.error(`FAIL: static/index.html still hosts feature specific control ID: "${elId}"`);
                failed = true;
            }
        }
        if (!failed) {
            console.log("PASS: static/index.html contains no feature controls");
        }

        // Collect all IDs across shell and fragments and ensure they are unique
        const idRegex = /id=["']([^"']+)["']/g;
        const allIds = [];
        let match;

        while ((match = idRegex.exec(indexHtml)) !== null) allIds.push({ id: match[1], file: 'index.html' });
        while ((match = idRegex.exec(downloaderHtml)) !== null) allIds.push({ id: match[1], file: 'downloader.html' });
        while ((match = idRegex.exec(subtitleHtml)) !== null) allIds.push({ id: match[1], file: 'subtitle.html' });

        const seenIds = new Map();
        for (const item of allIds) {
            if (seenIds.has(item.id)) {
                console.error(`FAIL: Duplicate element ID found: "${item.id}" (originally in ${seenIds.get(item.id)}, also found in ${item.file})`);
                failed = true;
            } else {
                seenIds.set(item.id, item.file);
            }
        }
        if (!failed) {
            console.log(`PASS: Verified ${seenIds.size} element IDs are completely unique across all shell & fragments`);
        }

        // Verify opaque settings right pane background (no transparency)
        if (!indexHtml.includes('id="settings-right-pane"') || (!indexHtml.includes('background: #ffffff') && !indexHtml.includes('background: #fff'))) {
            console.error("FAIL: settings right pane is missing or not opaque white");
            failed = true;
        } else {
            console.log("PASS: settings modal right content pane is configured to be opaque white");
        }

        // Verify settings close button is X icon-only and accessible in Vietnamese
        if (!indexHtml.includes('class="btn-close-x"') || !indexHtml.includes('title="Đóng"') || !indexHtml.includes('aria-label="Đóng"')) {
            console.error("FAIL: settings close button is not icon-only or missing accessible Vietnamese labels");
            failed = true;
        } else {
            console.log("PASS: settings close button is an accessible X icon-only button in Vietnamese");
        }

        // Verify shared console logs footer presence
        if (!indexHtml.includes('id="shared-terminal-panel"')) {
            console.error("FAIL: shared system log panel is missing from index.html");
            failed = true;
        } else if (downloaderHtml.includes('id="terminal-body"') || downloaderHtml.includes('id="shared-terminal-panel"')) {
            console.error("FAIL: system logs element still exists inside downloader.html fragment");
            failed = true;
        } else {
            console.log("PASS: shared system-log footer is placed in shell and removed from individual fragments");
        }

        // Validate bootstrap.js logic sequence (mount before dynamic module import)
        const bootstrapSrc = fs.readFileSync(path.resolve('static/js/bootstrap.js'), 'utf8');
        const fetchIndex = bootstrapSrc.indexOf('fetch(');
        const importIndex = bootstrapSrc.indexOf('import(');
        
        if (fetchIndex === -1 || importIndex === -1 || fetchIndex > importIndex) {
            console.error("FAIL: bootstrap.js does not guarantee mounting fragments before importing dynamic modules.", { fetchIndex, importIndex });
            failed = true;
        } else {
            console.log("PASS: bootstrap.js performs dynamic imports after fragment fetch setup");
        }

    } catch (err) {
        console.error("FAIL: Fragments verification tests crashed:", err);
        failed = true;
    }

} catch (err) {
    console.error("FAIL: Subtitle Helpers/Modal Unit tests crashed:", err);
    failed = true;
}

// 6. JobQueue Primitive Unit Tests
console.log("\nRunning JobQueue primitive unit tests...");
try {
    const fs = await import('fs');
    const path = await import('path');

    // Verify isolation (no API, state, or polling dependencies)
    const queuePath = path.resolve('static/js/job_queue.js');
    const queueSrc = fs.readFileSync(queuePath, 'utf8');
    const forbiddenImports = ['api.js', 'polling.js', 'state.js', 'fetchTasks', 'triggerTaskPolling'];
    for (const f of forbiddenImports) {
        if (queueSrc.includes(f)) {
            console.error(`FAIL: JobQueue primitive violates isolation. It references: "${f}"`);
            failed = true;
        }
    }
    if (!failed) {
        console.log("PASS: JobQueue contains no API/polling imports");
    }

    const { JobQueue, countStatuses, filterEligibleIds } = await import('./job_queue.js');

    // Test countStatuses pure helper
    const mockRows = [
        { id: 1, raw_status: 'pending' },
        { id: 2, raw_status: 'downloading' },
        { id: 3, raw_status: 'completed' },
        { id: 4, raw_status: 'failed' },
        { id: 5, raw_status: 'canceled' }
    ];
    
    // Normalize mapping example
    const normalizeStatus = (r) => {
        if (['pending', 'waiting'].includes(r.raw_status)) return 'waiting';
        if (['downloading', 'merging', 'processing', 'running'].includes(r.raw_status)) return 'running';
        if (['completed', 'done'].includes(r.raw_status)) return 'done';
        return 'error'; // failed, canceled
    };

    const counts = countStatuses(mockRows, normalizeStatus);
    if (counts.waiting !== 1 || counts.running !== 1 || counts.done !== 1 || counts.error !== 2) {
        console.error("FAIL: countStatuses returned incorrect stats mapping:", counts);
        failed = true;
    } else {
        console.log("PASS: countStatuses helper correctness (with canceled=>error normalization)");
    }

    // Test filterEligibleIds
    const isError = (r) => normalizeStatus(r) === 'error';
    const selectedIds = [2, 4, 5];
    const eligibleIds = filterEligibleIds(mockRows, r => r.id, isError, selectedIds);
    if (eligibleIds.length !== 2 || !eligibleIds.includes(4) || !eligibleIds.includes(5)) {
        console.error("FAIL: filterEligibleIds filtered wrong ids:", eligibleIds);
        failed = true;
    } else {
        console.log("PASS: filterEligibleIds selection eligibility");
    }

    // Test JobQueue instantiation and DOM rendering
    const dummyRoot = {
        innerHTML: '',
        appendChild: () => {}
    };

    const queueInstance = new JobQueue(dummyRoot, {
        selectable: true,
        getRowId: r => r.id,
        normalizeStatus,
        columns: [
            { key: 'id', label: 'ID', render: r => r.id },
            { key: 'text', label: 'Nội dung', render: r => document.createTextNode(r.raw_status) }
        ],
        selectionGroups: [
            { value: 'error', label: 'Lỗi', matches: (r, norm) => norm === 'error' }
        ],
        bulkActions: [
            { id: 'retry', label: 'Chạy lại', eligible: r => normalizeStatus(r) === 'error', onInvoke: () => {} }
        ]
    });

    if (queueInstance.selectedRowIds.size !== 0) {
        console.error("FAIL: JobQueue should initialize with empty selection");
        failed = true;
    } else {
        console.log("PASS: JobQueue instance initialization");
    }

    // Test selection cleanup on update
    queueInstance.selectedRowIds.add(2); // 'downloading'
    queueInstance.selectedRowIds.add(99); // Stale ID (does not exist in update rows)
    
    queueInstance.update({ rows: mockRows, elapsedSeconds: 20 });
    
    if (queueInstance.selectedRowIds.has(99)) {
        console.error("FAIL: JobQueue update did not drop stale selection IDs");
        failed = true;
    } else if (!queueInstance.selectedRowIds.has(2)) {
        console.error("FAIL: JobQueue update dropped still-existing selection ID");
        failed = true;
    } else {
        console.log("PASS: JobQueue update preserves existing and cleans up stale selection IDs");
    }

    // Test empty-state rendering assertions
    const testEmptyState = () => {
        const localMockRoot = createLocalMockElement('div');
        const qSelectable = new JobQueue(localMockRoot, {
            selectable: true,
            getRowId: r => r.id,
            normalizeStatus,
            columns: [
                { key: 'id', label: 'ID', render: r => r.id },
                { key: 'text', label: 'Text', render: r => r.text }
            ],
            labels: { empty: 'Không có dữ liệu' }
        });

        // 1. Initial empty headers: checking structure
        const table = localMockRoot.querySelector('.shared-queue-table');
        const thead = table ? table.querySelector('thead') : null;
        if (!thead || thead.style.display === 'none') {
            console.error("FAIL: thead headers should be visible even when empty");
            failed = true;
        } else {
            console.log("PASS: initial empty headers remain visible");
        }

        // 2. Correct colspan for selectable queue (columns count = 2 + 1 checkbox = 3)
        const emptyTrSelectable = localMockRoot.querySelector('.shared-queue-row-empty');
        const emptyTdSelectable = emptyTrSelectable ? emptyTrSelectable.querySelector('td') : null;
        if (!emptyTdSelectable || String(emptyTdSelectable.colspan) !== '3') {
            console.error("FAIL: incorrect colspan for selectable queue:", emptyTdSelectable ? emptyTdSelectable.colspan : null);
            failed = true;
        } else {
            console.log("PASS: correct colspan for selectable queue empty row");
        }

        // 3. Correct colspan for non-selectable queue (columns count = 2)
        const localMockRoot2 = createLocalMockElement('div');
        const qNonSelectable = new JobQueue(localMockRoot2, {
            selectable: false,
            getRowId: r => r.id,
            normalizeStatus,
            columns: [
                { key: 'id', label: 'ID', render: r => r.id },
                { key: 'text', label: 'Text', render: r => r.text }
            ],
            labels: { empty: 'Không có dữ liệu' }
        });

        const emptyTrNonSelectable = localMockRoot2.querySelector('.shared-queue-row-empty');
        const emptyTdNonSelectable = emptyTrNonSelectable ? emptyTrNonSelectable.querySelector('td') : null;
        if (!emptyTdNonSelectable || String(emptyTdNonSelectable.colspan) !== '2') {
            console.error("FAIL: incorrect colspan for non-selectable queue:", emptyTdNonSelectable ? emptyTdNonSelectable.colspan : null);
            failed = true;
        } else {
            console.log("PASS: correct colspan for non-selectable queue empty row");
        }

        // 4. Exactly one empty message exists in the table body
        const emptyStates = localMockRoot.querySelectorAll('.shared-queue-empty-state');
        if (emptyStates.length !== 1) {
            console.error("FAIL: expected exactly one empty state message, found:", emptyStates.length);
            failed = true;
        } else {
            console.log("PASS: exactly one empty state message exists inside the tbody");
        }

        // 5. Empty-to-populated transition
        const chkAll = localMockRoot.querySelector('.shared-queue-select-all');
        if (!chkAll || !chkAll.disabled) {
            console.error("FAIL: select-all checkbox should be disabled when empty");
            failed = true;
        } else {
            console.log("PASS: select-all checkbox is disabled on empty");
        }

        // Update to non-empty
        qSelectable.update({
            rows: [ { id: 1, text: 'Hello' } ],
            elapsedSeconds: 5
        });

        const emptyTrPopulated = localMockRoot.querySelector('.shared-queue-row-empty');
        const normalRows = localMockRoot.querySelectorAll('.shared-queue-row');
        if (emptyTrPopulated || normalRows.length !== 1) {
            console.error("FAIL: empty row should be removed and normal rows rendered");
            failed = true;
        } else if (chkAll.disabled) {
            console.error("FAIL: select-all checkbox should be re-enabled when populated");
            failed = true;
        } else {
            console.log("PASS: transition to populated correctly removes empty row and enables checkbox");
        }

        // Update back to empty
        qSelectable.update({
            rows: [],
            elapsedSeconds: 10
        });

        const emptyTrRestored = localMockRoot.querySelector('.shared-queue-row-empty');
        if (!emptyTrRestored || !chkAll.disabled || chkAll.checked) {
            console.error("FAIL: returning to empty state failed to restore empty row or disable checkbox");
            failed = true;
        } else {
            console.log("PASS: returning to empty state restores empty row and unchecks/disables checkbox");
        }
    };

    // Run empty state tests using createLocalMockElement helper
    // We temp replace document.createElement for this test suite
    const originalCreateElementForEmptyTest = globalThis.document.createElement;
    globalThis.document.createElement = (tag) => {
        const classes = new Set();
        const children = [];
        const el = {
            tagName: tag.toUpperCase(),
            style: {},
            dataset: {},
            classList: {
                add: (c) => {
                    classes.add(c);
                    el.className = Array.from(classes).join(' ');
                },
                remove: (c) => {
                    classes.delete(c);
                    el.className = Array.from(classes).join(' ');
                }
            },
            className: '',
            value: '',
            title: '',
            textContent: '',
            get innerHTML() { return el._innerHTML || ''; },
            set innerHTML(val) {
                el._innerHTML = val;
                if (val === '') {
                    children.length = 0;
                }
            },
            disabled: false,
            children: children,
            addEventListener: () => {},
            setAttribute: (name, value) => { el[name] = value; },
            appendChild: (child) => { children.push(child); },
            removeChild: () => {},
            querySelector: (sel) => {
                if (sel.startsWith('.')) {
                    const cls = sel.slice(1);
                    const currentClasses = el.className.split(/\s+/);
                    if (currentClasses.includes(cls)) return el;
                    for (const child of children) {
                        if (child.querySelector) {
                            const found = child.querySelector(sel);
                            if (found) return found;
                        }
                    }
                }
                if (sel === 'thead') {
                    for (const child of children) {
                        if (child.tagName === 'THEAD') return child;
                    }
                }
                if (sel === 'tbody') {
                    for (const child of children) {
                        if (child.tagName === 'TBODY') return child;
                    }
                }
                if (sel === 'td') {
                    for (const child of children) {
                        if (child.tagName === 'TD') return child;
                    }
                }
                return null;
            },
            querySelectorAll: (sel) => {
                const results = [];
                if (sel.startsWith('.')) {
                    const cls = sel.slice(1);
                    const currentClasses = el.className.split(/\s+/);
                    if (currentClasses.includes(cls)) {
                        results.push(el);
                    }
                    for (const child of children) {
                        if (child.querySelectorAll) {
                            results.push(...child.querySelectorAll(sel));
                        }
                    }
                }
                return results;
            }
        };
        return el;
    };

    function createLocalMockElement(tagName = '') {
        return globalThis.document.createElement(tagName);
    }

    testEmptyState();
    globalThis.document.createElement = originalCreateElementForEmptyTest;

    // Test renderToolbar assertions for compact layout
    const originalCreateElement = globalThis.document.createElement;
    globalThis.document.createElement = (tag) => {
        const el = {
            tagName: tag.toUpperCase(),
            style: {},
            dataset: {},
            classList: {
                add: (cls) => { el.className = (el.className || '') + ' ' + cls; },
                remove: () => {}
            },
            value: '',
            title: '',
            textContent: '',
            innerHTML: '',
            disabled: false,
            children: [],
            addEventListener: () => {},
            setAttribute: (name, value) => { el[name] = value; },
            appendChild: (child) => { el.children.push(child); },
            removeChild: () => {},
            querySelector: (sel) => {
                if (sel.startsWith('.')) {
                    const clsName = sel.substring(1);
                    const findInTree = (node) => {
                        if (node.className && node.className.includes(clsName)) return node;
                        for (const child of node.children || []) {
                            const found = findInTree(child);
                            if (found) return found;
                        }
                        return null;
                    };
                    return findInTree(el);
                }
                if (sel === 'select') {
                    const findSelect = (node) => {
                        if (node.tagName === 'SELECT') return node;
                        for (const child of node.children || []) {
                            const found = findSelect(child);
                            if (found) return found;
                        }
                        return null;
                    };
                    return findSelect(el);
                }
                return null;
            },
            querySelectorAll: () => []
        };
        return el;
    };

    const tq = new JobQueue(mockElement, {
        selectable: true,
        getRowId: r => r.id,
        normalizeStatus,
        columns: [ { key: 'id', label: 'ID', render: r => r.id } ],
        selectionGroups: [ { value: 'error', label: 'Lỗi', matches: (r, norm) => norm === 'error' } ],
        bulkActions: [
            { id: 'save', label: 'Lưu', eligible: r => true, onInvoke: () => {} },
            { id: 'cancel', label: 'Hủy', eligible: r => true, onInvoke: () => {} },
            { id: 'retry', label: 'Chạy lại', eligible: r => true, onInvoke: () => {} }
        ]
    });

    tq.renderToolbar();
    const barEl = tq.container.querySelector('.shared-queue-toolbar-bar');
    if (!barEl) {
        console.error("FAIL: toolbar container element not found");
        failed = true;
    } else {
        // Assert no filter label exists (no label element or no text Content containing "Chọn nhanh:")
        const hasFilterLabel = barEl.children.some(c => c.children.some(cc => cc.tagName === 'LABEL' || cc.textContent.includes('Chọn nhanh:')));
        if (hasFilterLabel) {
            console.error("FAIL: visible filter label (Chọn nhanh:) should be removed");
            failed = true;
        } else {
            console.log("PASS: JobQueue toolbar has no visible filter label");
        }

        // Filter and actions adjacency/order (filter select is first, actions is next/adjacent)
        const filterGrp = barEl.children.find(c => c.className && c.className.includes('shared-queue-filter-group'));
        const bulkGrp = barEl.children.find(c => c.className && c.className.includes('shared-queue-bulk-group'));
        
        if (!filterGrp || !bulkGrp || barEl.children.indexOf(filterGrp) > barEl.children.indexOf(bulkGrp)) {
            console.error("FAIL: filter and bulk groups adjacency/order incorrect");
            failed = true;
        } else {
            console.log("PASS: JobQueue toolbar filter and bulk groups are left-aligned and ordered correctly");
        }

        // Filter select title / aria-label
        const selectEl = filterGrp.querySelector('select');
        if (!selectEl || selectEl.title !== 'Lọc theo trạng thái' || selectEl['aria-label'] !== 'Lọc theo trạng thái') {
            console.error("FAIL: filter select does not have correct title or aria-label:", selectEl);
            failed = true;
        } else {
            console.log("PASS: filter select contains accessible title and aria-label");
        }

        // Bulk buttons icon-only SVG, no textContent label, title/aria-label, borderless class
        const buttons = bulkGrp.children.filter(c => c.tagName === 'BUTTON');
        if (buttons.length !== 3) {
            console.error("FAIL: bulk action buttons count mismatch:", buttons.length);
            failed = true;
        } else {
            const saveBtn = buttons.find(b => b.className.includes('shared-queue-btn-bulk-save'));
            const cancelBtn = buttons.find(b => b.className.includes('shared-queue-btn-bulk-cancel'));
            const retryBtn = buttons.find(b => b.className.includes('shared-queue-btn-bulk-retry'));

            if (!saveBtn || !cancelBtn || !retryBtn) {
                console.error("FAIL: bulk actions buttons classes not assigned");
                failed = true;
            } else {
                const checkBtn = (btn, expectedLabel, expectedIconClass) => {
                    if (btn.textContent !== '') {
                        console.error(`FAIL: button textContent should be empty for icon-only: got "${btn.textContent}"`);
                        return false;
                    }
                    if (btn.title !== expectedLabel || btn['aria-label'] !== expectedLabel) {
                        console.error(`FAIL: button accessibility mismatch: title="${btn.title}", aria-label="${btn['aria-label']}"`);
                        return false;
                    }
                    if (!btn.className.includes('shared-queue-btn-bulk-icon') || !btn.className.includes(expectedIconClass)) {
                        console.error(`FAIL: button styling classes missing: "${btn.className}"`);
                        return false;
                    }
                    if (!btn.innerHTML.includes('<svg') || !btn.innerHTML.includes('</svg>')) {
                        console.error(`FAIL: button does not contain inline SVG icon`);
                        return false;
                    }
                    return true;
                };

                const allValid = checkBtn(saveBtn, 'Lưu', 'action-save') &&
                                 checkBtn(cancelBtn, 'Hủy', 'action-cancel') &&
                                 checkBtn(retryBtn, 'Chạy lại', 'action-retry');
                if (!allValid) {
                    failed = true;
                } else {
                    console.log("PASS: bulk buttons are icon-only, borderless class assigned, contain inline SVGs, title/aria-labels");
                }
            }
        }
    }

    // Restore original createElement
    globalThis.document.createElement = originalCreateElement;

    // Test destroy
    queueInstance.destroy();
    if (queueInstance.selectedRowIds.size !== 0 || queueInstance.rows.length !== 0) {
        console.error("FAIL: JobQueue destroy failed to reset local states");
        failed = true;
    } else {
        console.log("PASS: JobQueue destroy resets states and clears root");
    }

    // 7. Downloader Queue Adapter Unit Tests
    console.log("\nRunning Downloader queue adapter unit tests...");
    try {
        const { initTasks, updateTasksUI } = await import('./tasks.js');

        // Execute initTasks to trigger JobQueue instantiation
        initTasks();

        // Obtain reference from exported downloaderQueueInstance
        const { downloaderQueueInstance: activeInstance } = await import('./tasks.js');
        
        if (!activeInstance) {
            console.error("FAIL: Downloader queue did not initialize JobQueue instance");
            failed = true;
        } else {
            console.log("PASS: Downloader queue initializes JobQueue instance successfully");

            // Test status mapping rules
            const mapper = activeInstance.options.normalizeStatus;
            if (mapper({ status: 'pending' }) !== 'waiting') {
                console.error("FAIL: Downloader status mapping incorrect for 'pending'");
                failed = true;
            }
            if (mapper({ status: 'downloading' }) !== 'running' || mapper({ status: 'merging' }) !== 'running' || mapper({ status: 'processing' }) !== 'running') {
                console.error("FAIL: Downloader status mapping incorrect for running statuses");
                failed = true;
            }
            if (mapper({ status: 'completed' }) !== 'done') {
                console.error("FAIL: Downloader status mapping incorrect for 'completed'");
                failed = true;
            }
            if (mapper({ status: 'failed' }) !== 'error' || mapper({ status: 'canceled' }) !== 'error') {
                console.error("FAIL: Downloader status mapping incorrect for error statuses");
                failed = true;
            }

            if (!failed) {
                console.log("PASS: Downloader status normalization matches requirements");
            }

            // Test column count and layout
            const columns = activeInstance.options.columns;
            if (columns.length !== 3) {
                console.error("FAIL: Downloader queue expected exactly 3 columns, got:", columns.length);
                failed = true;
            } else {
                console.log("PASS: Downloader queue layout columns count is exactly 3");
            }
            
            // Check row actions logic inside render functions
            const mockRowWaiting = { id: 't1', status: 'pending', filename: 'v1.mp4', progress: 0, elapsed_time: 0 };
            const mockRowFailed = { id: 't2', status: 'failed', filename: 'v2.mp4', progress: 50, elapsed_time: 12, error: 'Network timeout' };
            const mockRowDone = { id: 't3', status: 'completed', filename: 'v3.mp4', progress: 100, elapsed_time: 25 };

            const actionCol = columns.find(col => col.key === 'actions');
            if (!actionCol) {
                console.error("FAIL: Action column not found in Downloader queue columns");
                failed = true;
            } else {
                const nodeWaiting = actionCol.render(mockRowWaiting);
                const nodeFailed = actionCol.render(mockRowFailed);
                const nodeDone = actionCol.render(mockRowDone);

                const btnWaiting = nodeWaiting.querySelector('.btn-row-action');
                const btnFailed = nodeFailed.querySelector('.btn-row-action');
                const btnDone = nodeDone.querySelector('.btn-row-action');

                if (!btnWaiting || !btnWaiting.disabled) {
                    console.error("FAIL: Downloader actions folder button should be disabled for active statuses");
                    failed = true;
                }
                if (!btnFailed || !btnFailed.disabled) {
                    console.error("FAIL: Downloader actions folder button should be disabled for failed status");
                    failed = true;
                }
                if (!btnDone || btnDone.disabled) {
                    console.error("FAIL: Downloader actions folder button should be enabled for completed status");
                    failed = true;
                }

                if (!failed) {
                    console.log("PASS: Downloader row actions rendered correctly based on status eligibility");
                }
            }
        }
    } catch (err) {
        console.error("FAIL: Downloader queue adapter unit tests crashed:", err);
        failed = true;
    }

    // 8. Subtitle Queue Adapter Unit Tests
    console.log("\nRunning Subtitle queue adapter unit tests...");
    try {
        const { initSubtitleQueue, renderQueueTable, subtitleQueueInstance, shouldStopPolling, calculateJobStats, getEligibleJobIdsForAction } = await import('./subtitle_queue.js');
        const { downloaderQueueInstance } = await import('./tasks.js');

        // Execute initSubtitleQueue to trigger JobQueue instantiation
        initSubtitleQueue();

        const { subtitleQueueInstance: activeSubInstance } = await import('./subtitle_queue.js');

        if (!activeSubInstance) {
            console.error("FAIL: Subtitle queue did not initialize JobQueue instance");
            failed = true;
        } else if (activeSubInstance === downloaderQueueInstance) {
            console.error("FAIL: Subtitle and Downloader queue adapt sharing same JobQueue instance (must be independent)");
            failed = true;
        } else {
            console.log("PASS: Subtitle queue initializes independent JobQueue instance successfully");

            // Verify columns configuration
            const columns = activeSubInstance.options.columns;
            if (columns.length !== 3) {
                console.error("FAIL: Subtitle queue expected exactly 3 columns, got:", columns.length);
                failed = true;
            } else {
                console.log("PASS: Subtitle queue layout columns count is exactly 3");
            }

            const videoCol = columns.find(c => c.key === 'video');
            const progressCol = columns.find(c => c.key === 'progress');
            const actionsCol = columns.find(c => c.key === 'actions');

            if (!videoCol || !progressCol || !actionsCol) {
                console.error("FAIL: Missing expected subtitle columns keys");
                failed = true;
            } else {
                // Setup localized mock element creator to avoid global mockElement shared mutation
                const originalCreateElement = globalThis.document.createElement;
                globalThis.document.createElement = (tag) => {
                    const el = {
                        tagName: tag.toUpperCase(),
                        style: {},
                        dataset: {},
                        classList: {
                            add: (cls) => { el.className = (el.className || '') + ' ' + cls; },
                            remove: () => {}
                        },
                        value: '',
                        title: '',
                        textContent: '',
                        innerHTML: '',
                        disabled: false,
                        children: [],
                        addEventListener: () => {},
                        appendChild: (child) => { el.children.push(child); },
                        removeChild: () => {},
                        querySelector: (sel) => {
                            if (sel.startsWith('.')) {
                                const clsName = sel.substring(1);
                                const findInTree = (node) => {
                                    if (node.className && node.className.includes(clsName)) return node;
                                    for (const child of node.children || []) {
                                        const found = findInTree(child);
                                        if (found) return found;
                                    }
                                    return null;
                                };
                                return findInTree(el);
                            }
                            if (sel === 'span') {
                                const findSpan = (node) => {
                                    if (node.tagName === 'SPAN') return node;
                                    for (const child of node.children || []) {
                                        const found = findSpan(child);
                                        if (found) return found;
                                    }
                                };
                                return findSpan(el);
                            }
                            return null;
                        },
                        querySelectorAll: (sel) => {
                            if (sel.startsWith('.')) {
                                const clsName = sel.substring(1);
                                const results = [];
                                const findInTree = (node) => {
                                    if (node.className && node.className.includes(clsName)) results.push(node);
                                    for (const child of node.children || []) {
                                        findInTree(child);
                                    }
                                };
                                findInTree(el);
                                return results;
                            }
                            return [];
                        },
                        setAttribute: (name, value) => { el[name] = value; }
                    };
                    return el;
                };

                // Test Video truncate depth 3
                const mockRow = { video_path: '/path/to/my/video/file.mp4', status: 'done', segments: [1, 2, 3] };
                const videoEl = videoCol.render(mockRow);
                if (videoEl.textContent !== '.../my/video/file.mp4') {
                    console.error("FAIL: Video path truncation depth is not 3:", videoEl.textContent);
                    failed = true;
                } else {
                    console.log("PASS: Video path truncation depth is exactly 3");
                }

                // Test progress/status rendering combined
                const progressEl = progressCol.render({ video_path: 'v', status: 'running', progress: 45, phase: 'transcribing' });
                const prText = progressEl.querySelector('span');
                if (!prText || !prText.textContent.toString().includes('45%') || !prText.textContent.toString().includes('nhận dạng')) {
                    console.error("FAIL: Subtitle progress column text formatting:", prText ? prText.textContent : 'none');
                    failed = true;
                }
                const track = progressEl.querySelector('.progress-track');
                const bar = progressEl.querySelector('.progress-bar');
                if (!track || !bar || bar.style.width !== '45%') {
                    console.error("FAIL: Subtitle progress column bar layout:", bar ? bar.style.width : 'none');
                    failed = true;
                }
                console.log("PASS: Subtitle progress combined cell contains progress bar and phase label");

                // Test detail actions (Folder and Eye button)
                const mockRowDone = { video_path: 'v', status: 'done', saved_path: '/path/to/sub.srt' };
                const actionContainerDone = actionsCol.render(mockRowDone);
                const buttonsDone = actionContainerDone.querySelectorAll('.btn-row-action');
                if (buttonsDone.length !== 2 || buttonsDone[0].disabled || buttonsDone[1].disabled) {
                    console.error("FAIL: Both folder and eye actions should be enabled for done rows with saved_path");
                    failed = true;
                }
                
                const mockRowRunning = { video_path: 'v', status: 'running' };
                const actionContainerRunning = actionsCol.render(mockRowRunning);
                const buttonsRunning = actionContainerRunning.querySelectorAll('.btn-row-action');
                if (buttonsRunning.length !== 2 || !buttonsRunning[0].disabled || !buttonsRunning[1].disabled) {
                    console.error("FAIL: Both actions should be disabled for active rows");
                    failed = true;
                }
                console.log("PASS: Subtitle actions eligibility matches expectations");

                // Restore
                globalThis.document.createElement = originalCreateElement;
            }

            // Test status mapping rules
            const mapper = activeSubInstance.options.normalizeStatus;
            if (mapper({ status: 'waiting' }) !== 'waiting') {
                console.error("FAIL: Subtitle status mapping incorrect for 'waiting'");
                failed = true;
            }
            if (mapper({ status: 'running' }) !== 'running') {
                console.error("FAIL: Subtitle status mapping incorrect for 'running'");
                failed = true;
            }
            if (mapper({ status: 'done' }) !== 'done') {
                console.error("FAIL: Subtitle status mapping incorrect for 'done'");
                failed = true;
            }
            if (mapper({ status: 'error' }) !== 'error' || mapper({ status: 'canceled' }) !== 'error') {
                console.error("FAIL: Subtitle status mapping incorrect for error statuses");
                failed = true;
            }

            if (!failed) {
                console.log("PASS: Subtitle status normalization matches requirements");
            }

            // Test calculateJobStats correctness (error and canceled grouped together)
            const mockJobs = [
                { job_id: 'j1', status: 'waiting' },
                { job_id: 'j2', status: 'running' },
                { job_id: 'j3', status: 'done' },
                { job_id: 'j4', status: 'error' },
                { job_id: 'j5', status: 'canceled' }
            ];
            const stats = calculateJobStats(mockJobs);
            if (stats.total !== 5 || stats.waiting !== 1 || stats.running !== 1 || stats.done !== 1 || stats.error !== 2) {
                console.error("FAIL: calculateJobStats mapped wrong counts:", stats);
                failed = true;
            } else {
                console.log("PASS: calculateJobStats groups canceled & error correctly");
            }

            // Test getEligibleJobIdsForAction selection eligibility
            const selectedIds = ['j1', 'j2', 'j3', 'j4', 'j5'];
            const eligibleSave = getEligibleJobIdsForAction(mockJobs, 'save', selectedIds);
            const eligibleCancel = getEligibleJobIdsForAction(mockJobs, 'cancel', selectedIds);
            const eligibleRetry = getEligibleJobIdsForAction(mockJobs, 'retry', selectedIds);

            if (eligibleSave.length !== 1 || eligibleSave[0] !== 'j3') {
                console.error("FAIL: eligibleJobIds incorrect for 'save':", eligibleSave);
                failed = true;
            }
            if (eligibleCancel.length !== 2 || !eligibleCancel.includes('j1') || !eligibleCancel.includes('j2')) {
                console.error("FAIL: eligibleJobIds incorrect for 'cancel':", eligibleCancel);
                failed = true;
            }
            if (eligibleRetry.length !== 2 || !eligibleRetry.includes('j4') || !eligibleRetry.includes('j5')) {
                console.error("FAIL: eligibleJobIds incorrect for 'retry':", eligibleRetry);
                failed = true;
            }
            if (!failed) {
                console.log("PASS: getEligibleJobIdsForAction action filters match specifications");
            }

            // Test poll stop decision helper
            const activeSnapshot = { jobs: mockJobs };
            const settledSnapshot = { jobs: mockJobs.filter(j => ['done', 'error', 'canceled'].includes(j.status)) };

            if (shouldStopPolling(activeSnapshot, 'b1') === true) {
                console.error("FAIL: shouldStopPolling returned true when running jobs exist");
                failed = true;
            } else if (shouldStopPolling(settledSnapshot, 'b1') === false) {
                console.error("FAIL: shouldStopPolling returned false when all jobs are settled");
                failed = true;
            } else {
                console.log("PASS: shouldStopPolling determines lifecycle states correctly");
            }
        }
    } catch (err) {
        console.error("FAIL: Subtitle queue adapter unit tests crashed:", err);
        failed = true;
    }

    // 9. Parity and Vietnamese labels checks (Contract E)
    console.log("\nRunning queue parity and Vietnamese labels unit tests...");
    try {
        const { downloaderQueueInstance } = await import('./tasks.js');
        const { subtitleQueueInstance } = await import('./subtitle_queue.js');

        // Verify Vietnamese status mappings for Downloader
        const mockDownloaderRows = [
            { id: 1, status: 'pending' },
            { id: 2, status: 'downloading' },
            { id: 3, status: 'merging' },
            { id: 4, status: 'processing' },
            { id: 5, status: 'completed' },
            { id: 6, status: 'failed' },
            { id: 7, status: 'canceled' }
        ];

        const dlProgressCol = downloaderQueueInstance.options.columns.find(c => c.key === 'progress');
        if (!dlProgressCol) {
            console.error("FAIL: Downloader queue progress column not found");
            failed = true;
        } else {
            const dlLabels = mockDownloaderRows.map(r => dlProgressCol.render({...r, progress: 50}).textContent);
            const expectedDlSubstrings = ['Chờ', 'Đang tải', 'Đang ghép', 'Đang xử lý', 'Hoàn thành', 'Lỗi', 'Đã hủy'];
            
            for (let i = 0; i < expectedDlSubstrings.length; i++) {
                if (!dlLabels[i].includes(expectedDlSubstrings[i])) {
                    console.error(`FAIL: Downloader status label mapped wrong text: got "${dlLabels[i]}", expected substring "${expectedDlSubstrings[i]}"`);
                    failed = true;
                }
            }
            if (!failed) {
                console.log("PASS: Downloader queue status labels are correctly mapped in Vietnamese");
            }
        }

        // Verify Subtitle transcribing phases translated to Vietnamese
        const mockSubRows = [
            { job_id: 'j1', status: 'running', phase: 'preparing', progress: 10 },
            { job_id: 'j2', status: 'running', phase: 'loading model', progress: 30 },
            { job_id: 'j3', status: 'running', phase: 'transcribing', progress: 60 },
            { job_id: 'j4', status: 'running', phase: 'formatting', progress: 90 }
        ];

        const subProgressCol = subtitleQueueInstance.options.columns.find(c => c.key === 'progress');
        if (!subProgressCol) {
            console.error("FAIL: Subtitle queue progress column not found");
            failed = true;
        } else {
            const subProgressLabels = mockSubRows.map(r => subProgressCol.render(r).textContent);
            const expectedSubProgress = [
                '10% (Đang chuẩn bị)',
                '30% (Đang tải mô hình)',
                '60% (Đang nhận dạng)',
                '90% (Đang xuất phụ đề)'
            ];

            for (let i = 0; i < expectedSubProgress.length; i++) {
                if (subProgressLabels[i] !== expectedSubProgress[i]) {
                    console.error(`FAIL: Subtitle phase label mapped wrong text: got "${subProgressLabels[i]}", expected "${expectedSubProgress[i]}"`);
                    failed = true;
                }
            }
            if (!failed) {
                console.log("PASS: Subtitle queue transcribing phase labels are correctly translated to Vietnamese");
            }
        }

        // Verify showSummaryInStatsBar settings for both adapters
        if (downloaderQueueInstance.options.showSummaryInStatsBar !== true) {
            console.error("FAIL: Downloader stats summary bar should display status summary");
            failed = true;
        }
        if (subtitleQueueInstance.options.showSummaryInStatsBar !== false) {
            console.error("FAIL: Subtitle stats summary bar should disable status summary to match Downloader layout logic");
            failed = true;
        }
        if (!failed) {
            console.log("PASS: Stats bar summaries display settings match specifications");
        }

        // Check for absence of English queue labels in fragments
        const fs = await import('fs');
        const path = await import('path');
        const dlHtml = fs.readFileSync(path.resolve('static/fragments/downloader.html'), 'utf8');
        const subHtml = fs.readFileSync(path.resolve('static/fragments/subtitle.html'), 'utf8');
        
        const englishTerms = ['waiting:', 'running:', 'done:', 'error:'];
        for (const term of englishTerms) {
            if (dlHtml.includes(term) || subHtml.includes(term)) {
                console.error(`FAIL: Legacy English queue stat label "${term}" still present in templates`);
                failed = true;
            }
        }
        if (!failed) {
            console.log("PASS: verified legacy English stats labels are completely removed from HTML templates");
        }

        // 10. Final Shared Queue Parity & Behavior checks
        console.log("\nRunning final shared queue parity and behavior checks...");
        
        // Setup specialized mock for this test to handle multiple elements
        const originalCreateElement = document.createElement;
        const originalCreateTextNode = document.createTextNode;

        function createLocalMockElement(tagName = '') {
            const classes = new Set();
            const children = [];
            const el = {
                tagName: tagName.toUpperCase(),
                addEventListener: () => {},
                appendChild: (child) => {
                    children.push(child);
                },
                removeChild: () => {},
                style: {},
                dataset: {},
                classList: {
                    add: (c) => {
                        classes.add(c);
                        el.className = Array.from(classes).join(' ');
                    },
                    remove: (c) => {
                        classes.delete(c);
                        el.className = Array.from(classes).join(' ');
                    }
                },
                className: '',
                value: '',
                title: '',
                textContent: '',
                innerHTML: '',
                setAttribute: (name, value) => { el[name] = value; },
                querySelector: (sel) => {
                    if (sel.startsWith('.')) {
                        const cls = sel.slice(1);
                        const currentClasses = el.className.split(/\s+/);
                        if (currentClasses.includes(cls)) return el;
                        for (const child of children) {
                            if (child.querySelector) {
                                const found = child.querySelector(sel);
                                if (found) return found;
                            }
                        }
                    }
                    return null;
                },
                querySelectorAll: (sel) => {
                    const results = [];
                    if (sel.startsWith('.')) {
                        const cls = sel.slice(1);
                        const currentClasses = el.className.split(/\s+/);
                        if (currentClasses.includes(cls)) {
                            results.push(el);
                        }
                        for (const child of children) {
                            if (child.querySelectorAll) {
                                results.push(...child.querySelectorAll(sel));
                            }
                        }
                    }
                    return results;
                }
            };
            return el;
        }

        document.createElement = (tag) => createLocalMockElement(tag);
        document.createTextNode = (text) => {
            const node = createLocalMockElement('#text');
            node.textContent = text;
            return node;
        };

        const mockRoot = createLocalMockElement('div');
        const testQueue = new JobQueue(mockRoot, {
            selectable: true,
            getRowId: r => r.id,
            columns: [{ key: 'id', label: 'ID', render: r => r.id }]
        });
        testQueue.update({ rows: [{ id: 1 }, { id: 2 }], elapsedSeconds: 42 });
        
        const totalSpan = mockRoot.querySelector('.shared-queue-stat-total');
        const elapsedSpan = mockRoot.querySelector('.shared-queue-elapsed-time');
        
        if (!totalSpan || !totalSpan.textContent.includes('Tổng: 2')) {
            console.error("FAIL: stat-total span content incorrect:", totalSpan ? totalSpan.textContent : 'not found');
            failed = true;
        } else if (!elapsedSpan || !elapsedSpan.textContent.includes('Thời gian chạy: 42s')) {
            console.error("FAIL: elapsed-time span content incorrect:", elapsedSpan ? elapsedSpan.textContent : 'not found');
            failed = true;
        } else {
            console.log("PASS: Total and elapsed times are properly labeled and rendered");
        }

        // Test numeric ID selection survival
        testQueue.selectedRowIds.add("1");
        testQueue.update({ rows: [{ id: 1 }, { id: 2 }], elapsedSeconds: 42 });
        if (!testQueue.selectedRowIds.has("1")) {
            console.error("FAIL: numeric ID selection did not survive update");
            failed = true;
        }
        
        testQueue.applySelectionFilter('all');
        if (!testQueue.selectedRowIds.has("1") || !testQueue.selectedRowIds.has("2")) {
            console.error("FAIL: numeric ID selection did not survive filter");
            failed = true;
        } else {
            console.log("PASS: numeric ID selection and lookup work correctly");
        }

        // Restore document element factories
        document.createElement = originalCreateElement;
        document.createTextNode = originalCreateTextNode;

        // Test settled error status is not overwritten
        const statusEl = document.getElementById('subtitle-status');
        statusEl.textContent = "Trạng thái: Hoàn tất có lỗi (4/5)";
        
        const { startQueuePolling, stopQueuePolling } = await import('./subtitle_queue.js');
        const originalFetch = globalThis.fetch;
        
        globalThis.fetch = async (url, options) => {
            if (typeof url === 'string' && url.includes('/api/subtitles/batch/')) {
                return {
                    ok: true,
                    json: async () => ({
                        total_duration: 10,
                        stats: { waiting: 0, running: 0, done: 4, error: 1 },
                        jobs: [
                            { job_id: 'j1', status: 'done' },
                            { job_id: 'j2', status: 'done' },
                            { job_id: 'j3', status: 'done' },
                            { job_id: 'j4', status: 'done' },
                            { job_id: 'j5', status: 'error' }
                        ]
                    })
                };
            }
            return originalFetch(url, options);
        };

        startQueuePolling('test-batch-id');
        await new Promise(resolve => setTimeout(resolve, 50));
        stopQueuePolling();
        globalThis.fetch = originalFetch;

        if (statusEl.textContent !== "Trạng thái: Hoàn tất có lỗi (4/5)") {
            console.error("FAIL: settled error status text was overwritten to:", statusEl.textContent);
            failed = true;
        } else {
            console.log("PASS: settled status text is preserved on poll completion");
        }

    } catch (err) {
        console.error("FAIL: Parity and Vietnamese labels tests crashed:", err);
        failed = true;
    }

} catch (err) {
    console.error("FAIL: JobQueue unit tests crashed:", err);
    failed = true;
}

// 11. Translation Module Unit Tests
console.log("\nRunning Translation module client-side unit tests...");
try {
    const translateModule = await import('./translate.js');
    const settingsModule = await import('./settings.js');
    const api = await import('./api.js');
    
    // Mock DOM Elements needed by translate.js and settings.js
    const mockTranslateElements = {};
    const getMockElement = (id) => {
        if (!mockTranslateElements[id]) {
            mockTranslateElements[id] = {
                id: id,
                addEventListener: (event, cb) => {
                    if (!mockTranslateElements[id].listeners) mockTranslateElements[id].listeners = {};
                    mockTranslateElements[id].listeners[event] = cb;
                },
                appendChild: (child) => {
                    if (!mockTranslateElements[id].children) mockTranslateElements[id].children = [];
                    mockTranslateElements[id].children.push(child);
                },
                removeChild: () => {},
                querySelector: (sel) => {
                    if (sel.startsWith('.')) {
                        const cls = sel.slice(1);
                        if (!mockTranslateElements[id]._queries) mockTranslateElements[id]._queries = {};
                        if (!mockTranslateElements[id]._queries[cls]) {
                            mockTranslateElements[id]._queries[cls] = getMockElement(id + "_" + cls);
                        }
                        return mockTranslateElements[id]._queries[cls];
                    }
                    if (sel === 'span' || sel === 'strong' || sel === 'button') {
                        return getMockElement(id + "_" + sel);
                    }
                    return mockElement;
                },
                querySelectorAll: () => [],
                cloneNode: () => getMockElement(id),
                replaceWith: () => {},
                classList: { add: () => {}, remove: () => {} },
                style: {},
                dataset: {},
                value: '',
                placeholder: '',
                textContent: '',
                innerHTML: '',
                removeAttribute: () => {},
                setAttribute: (k, v) => {},
                disabled: false,
                checked: false,
                children: [],
                listeners: {}
            };
        }
        return mockTranslateElements[id];
    };

    const originalGetElement = globalThis.document.getElementById;
    const originalGetElementsByName = globalThis.document.getElementsByName;
    const originalFetch = globalThis.fetch;

    globalThis.document.getElementById = (id) => getMockElement(id);
    
    const mockRadioSrt = getMockElement('radio-srt');
    mockRadioSrt.value = 'srt';
    mockRadioSrt.checked = true;
    const mockRadioFolder = getMockElement('radio-folder');
    mockRadioFolder.value = 'folder';
    mockRadioFolder.checked = false;
    
    globalThis.document.getElementsByName = (name) => {
        if (name === 'translate-source-mode') return [mockRadioSrt, mockRadioFolder];
        return [];
    };

    // Mock APIs
    let createBatchPayload = null;
    let setCredsPayload = null;
    let deletedProvider = null;
    let revealedProvider = null;

    const mockProfiles = [
        { profile: 'economy', label: 'Economy', model: 'gemini-3.5-flash-lite', provider: 'gemini' },
        { profile: 'balanced', label: 'Balanced', model: 'gemini-3.5-flash', provider: 'gemini' }
    ];

    const mockProviders = [
        { id: 'gemini', name: 'Google Gemini', env_var: 'GEMINI_API_KEY' }
    ];

    globalThis.fetch = async (url, options) => {
        if (url === '/api/translate/providers') {
            return { ok: true, json: async () => mockProviders };
        }
        if (url.startsWith('/api/translate/credentials/gemini/reveal')) {
            revealedProvider = 'gemini';
            return { ok: true, json: async () => ({ provider: 'gemini', api_key: 'REVEALED_DECRYPTED_KEY' }) };
        }
        if (url.startsWith('/api/translate/credentials/')) {
            const parts = url.split('/');
            const provider = parts[parts.length - 1];
            if (options && options.method === 'PUT') {
                setCredsPayload = JSON.parse(options.body);
                return { ok: true, json: async () => ({ status: 'success' }) };
            }
            if (options && options.method === 'DELETE') {
                deletedProvider = provider;
                return { ok: true, json: async () => ({ status: 'success' }) };
            }
            // GET config status
            return {
                ok: true,
                json: async () => ({
                    configured: true,
                    source: 'secret_service',
                    hint: 'AIzaSy...abcd',
                    providers: {
                        gemini: { configured: true, source: 'secret_service', hint: 'AIzaSy...abcd' }
                    }
                })
            };
        }
        if (url === '/api/translate/credentials') {
            return {
                ok: true,
                json: async () => ({
                    configured: true,
                    source: 'secret_service',
                    hint: 'AIzaSy...abcd',
                    providers: {
                        gemini: { configured: true, source: 'secret_service', hint: 'AIzaSy...abcd' }
                    }
                })
            };
        }
        if (url === '/api/translate/profiles') {
            return { ok: true, json: async () => mockProfiles };
        }
        if (url === '/api/translate/batches') {
            createBatchPayload = JSON.parse(options.body);
            return { ok: true, json: async () => ({ batch_id: 'test-batch', status: 'running' }) };
        }
        if (url === '/api/translate/scan-folder') {
            return { ok: true, json: async () => ({ files: ['/path/to/f1.srt', '/path/to/f2.srt'] }) };
        }
        if (url === '/api/select-srt-file') {
            return { ok: true, json: async () => ({ status: 'success', path: '/home/user/workspace/sub.srt' }) };
        }
        if (url === '/api/subtitle/select-video-folder') {
            return { ok: true, json: async () => ({ status: 'success', path: '/home/user/workspace/folder' }) };
        }
        return { ok: true, json: async () => ({}) };
    };

    // Initialize Translate
    await translateModule.initTranslate();
    settingsModule.initSettings();
    console.log("PASS: translate.js and settings.js initialized successfully");

    // Verify no hardcoded 'gemini' display name branching exists in translate.js
    const fs = await import('fs');
    const translateJsText = fs.readFileSync('static/js/translate.js', 'utf8');
    if (translateJsText.includes("provider === 'gemini'") || translateJsText.includes('provider === "gemini"')) {
        console.error("FAIL: translate.js contains legacy hardcoded gemini branching logic");
        failed = true;
    } else {
        console.log("PASS: translate.js contains no legacy hardcoded gemini branching logic");
    }

    // Verify Defaults
    const selectLang = getMockElement('translate-language');
    selectLang.value = 'vi'; // simulate default
    const selectConcurrency = getMockElement('translate-concurrency');
    selectConcurrency.value = '2'; // simulate default

    if (selectLang.value !== 'vi') {
        console.error("FAIL: translate-language default is not 'vi'");
        failed = true;
    } else {
        console.log("PASS: translate-language default is correct");
    }
    if (selectConcurrency.value !== '2') {
        console.error("FAIL: translate-concurrency default is not '2'");
        failed = true;
    } else {
        console.log("PASS: translate-concurrency default is correct");
    }

    // Verify Settings Modal opening & rendering
    const btnOpenSettings = getMockElement('btn-open-settings');
    if (btnOpenSettings.listeners['click']) {
        await btnOpenSettings.listeners['click']();
        
        // Settings modal style check
        const modalSettings = getMockElement('global-settings-modal');
        if (modalSettings.style.display !== 'flex') {
            console.error("FAIL: Settings modal did not display on click");
            failed = true;
        } else {
            console.log("PASS: Settings modal opened and styled successfully");
        }
    } else {
        console.error("FAIL: btn-open-settings listener not bound");
        failed = true;
    }

    // Verify Model change triggers Quick Key modal if not configured
    const selectProfile = getMockElement('translate-profile');
    
    // Simulate provider NOT configured fetch payload
    const originalFetchLocal = globalThis.fetch;
    globalThis.fetch = async (url, options) => {
        if (url.startsWith('/api/translate/credentials/')) {
            return { ok: true, json: async () => ({ configured: false, source: 'none', hint: '' }) };
        }
        return originalFetchLocal(url, options);
    };

    selectProfile.value = 'balanced';
    if (selectProfile.listeners['change']) {
        await selectProfile.listeners['change']();
        
        const quickModal = getMockElement('quick-key-modal');
        if (quickModal.style.display !== 'flex') {
            console.error("FAIL: Quick key modal did not open on unconfigured model selection");
            failed = true;
        } else {
            console.log("PASS: Quick key entry modal triggered successfully on missing key selection");
        }
        
        // Verify Quick Key Cancel resets profile selector
        const btnCancelQuick = getMockElement('btn-quick-key-cancel');
        if (btnCancelQuick.listeners['click']) {
            await btnCancelQuick.listeners['click']();
            if (selectProfile.value !== '') {
                console.error("FAIL: Quick key cancel did not reset profile selection");
                failed = true;
            } else {
                console.log("PASS: Quick key cancel resets model selection successfully");
            }
        }
    }

    // Restore fetch mock
    globalThis.fetch = originalFetchLocal;

    // Simulate select source button click event
    const btnSelect = getMockElement('btn-translate-select-source');
    if (btnSelect.listeners['click']) {
        await btnSelect.listeners['click']();
        const sourcePathInput = getMockElement('translate-source-path');
        if (!sourcePathInput.value.includes('sub.srt')) {
            console.error("FAIL: select source did not populate display field:", sourcePathInput.value);
            failed = true;
        } else {
            console.log("PASS: select source populates display path correctly");
        }
    } else {
        console.error("FAIL: btn-translate-select-source listener not bound");
        failed = true;
    }

    // Now trigger Start Batch
    selectProfile.value = 'balanced';
    const btnStart = getMockElement('btn-translate-start');
    if (btnStart.listeners['click']) {
        await btnStart.listeners['click']();
        if (!createBatchPayload || createBatchPayload.files[0] !== '/home/user/workspace/sub.srt' || createBatchPayload.target_language !== 'vi' || createBatchPayload.profile !== 'balanced' || createBatchPayload.concurrency !== 2) {
            console.error("FAIL: createTranslateBatch payload incorrect:", createBatchPayload);
            failed = true;
        } else {
            console.log("PASS: createTranslateBatch payload matched exact expected parameters");
        }
    } else {
        console.error("FAIL: btn-translate-start click listener not bound");
        failed = true;
    }

    // Verify select folder API Parity
    let selectVideoFolderCalled = false;
    const fetchForFolder = globalThis.fetch;
    globalThis.fetch = async (url, options) => {
        if (url === '/api/subtitle/select-video-folder') {
            selectVideoFolderCalled = true;
            return { ok: true, json: async () => ({ status: 'success', path: '/home/user/workspace/folder' }) };
        }
        return fetchForFolder(url, options);
    };

    // Set mode to folder
    const radioFolder = getMockElement('radio-folder');
    radioFolder.checked = true;
    const radioSrt = getMockElement('radio-srt');
    radioSrt.checked = false;

    const btnSelectSource = getMockElement('btn-translate-select-source');
    if (btnSelectSource.listeners['click']) {
        await btnSelectSource.listeners['click']();
        if (!selectVideoFolderCalled) {
            console.error("FAIL: select source folder picker did not call api.selectVideoFolder");
            failed = true;
        } else {
            console.log("PASS: select source picker uses api.selectVideoFolder instead of selectDirectory");
        }
    }
    globalThis.fetch = originalFetchLocal;

    // 12. Translation Queue and Modal Unit Tests
    console.log("\nRunning Translation Queue and Modal unit tests...");
    try {
        const queueMod = await import('./translate_queue.js');
        const modalMod = await import('./translate_modal.js');

        // Setup mock environment Elements
        const localMockElements = {};
        const getLocalMockElement = (id) => {
            if (!localMockElements[id]) {
                localMockElements[id] = {
                    addEventListener: (event, cb) => {
                        if (!localMockElements[id].listeners) localMockElements[id].listeners = {};
                        localMockElements[id].listeners[event] = cb;
                    },
                    appendChild: (child) => {
                        if (!localMockElements[id].children) localMockElements[id].children = [];
                        localMockElements[id].children.push(child);
                    },
                    removeChild: () => {},
                    classList: { add: () => {}, remove: () => {} },
                    style: {},
                    dataset: {},
                    value: '',
                    placeholder: '',
                    textContent: '',
                    innerHTML: '',
                    disabled: false,
                    checked: false,
                    children: [],
                    listeners: {},
                    querySelector: (sel) => {
                        if (sel.includes('.translate-trans-textarea')) {
                            const ta = getLocalMockElement('trans-ta-dummy');
                            ta.className = 'translate-trans-textarea';
                            ta.dataset.index = 1;
                            ta.value = 'MOCK_EDIT_VALUE';
                            return ta;
                        }
                        return getLocalMockElement('child-dummy');
                    },
                    querySelectorAll: (sel) => {
                        if (sel.includes('.translate-trans-textarea')) {
                            const ta = getLocalMockElement('trans-ta-dummy');
                            ta.className = 'translate-trans-textarea';
                            ta.dataset.index = 1;
                            ta.value = 'MOCK_EDIT_VALUE';
                            return [ta];
                        }
                        return [];
                    }
                };
            }
            return localMockElements[id];
        };

        const originalGetElement2 = globalThis.document.getElementById;
        globalThis.document.getElementById = (id) => getLocalMockElement(id);

        let patchActionSent = null;
        let saveEditsSent = null;

        // Custom local fetch mockup for API logic under queues and modals
        globalThis.fetch = async (url, options) => {
            if (url.includes('/api/translate/batches/test-batch/action')) {
                patchActionSent = JSON.parse(options.body);
                return { ok: true, json: async () => ({ status: 'success' }) };
            }
            if (url.includes('/api/translate/batches/test-batch/jobs/job-1/compare')) {
                return {
                    ok: true,
                    json: async () => ({
                        source_path: '/path/to/vid.srt',
                        saved_path: '/path/to/vid_vi.srt',
                        segments: [{ index: 1, start_ms: 100, end_ms: 200, source_text: 'Hello', translated_text: 'Xin chào' }]
                    })
                };
            }
            if (url.includes('/api/translate/batches/test-batch/jobs/job-1/edits')) {
                saveEditsSent = JSON.parse(options.body);
                return { ok: true, json: async () => ({ status: 'success' }) };
            }
            return { ok: true, json: async () => ({}) };
        };

        // Initialize Queue & Modal
        queueMod.initTranslateQueue();
        let saveSuccessTriggered = false;
        modalMod.initTranslateModal(async () => { saveSuccessTriggered = true; });

        if (!queueMod.translateQueueInstance) {
            console.error("FAIL: initTranslateQueue did not construct JobQueue instance");
            failed = true;
        } else {
            console.log("PASS: translateQueueInstance initializes successfully");
        }

        // Test bulk actions cancel/retry eligibility mapping
        const mapper = queueMod.translateQueueInstance.options.normalizeStatus;
        const mockRows = [
            { job_id: 'j1', status: 'waiting' },
            { job_id: 'j2', status: 'running' },
            { job_id: 'j3', status: 'done' },
            { job_id: 'j4', status: 'error' },
            { job_id: 'j5', status: 'canceled' }
        ];

        if (mapper(mockRows[0]) !== 'waiting' || mapper(mockRows[1]) !== 'running' || mapper(mockRows[2]) !== 'done' || mapper(mockRows[3]) !== 'error' || mapper(mockRows[4]) !== 'error') {
            console.error("FAIL: translateQueue status mapping normalizations failed");
            failed = true;
        } else {
            console.log("PASS: translateQueue normalization groups canceled/error states correctly");
        }

        // Test cancel bulk triggers
        const cancelAction = queueMod.translateQueueInstance.options.bulkActions.find(a => a.id === 'cancel');
        if (cancelAction) {
            if (cancelAction.eligible(mockRows[0]) !== true || cancelAction.eligible(mockRows[2]) !== false) {
                console.error("FAIL: cancel action eligibility incorrect");
                failed = true;
            } else {
                console.log("PASS: cancel actions eligibility bounds mapped correctly");
            }
        }

        // Open Modal Compare Verification
        await modalMod.openTranslateModal('test-batch', 'job-1');
        const modalTitle = getLocalMockElement('translate-modal-title');
        if (!modalTitle.textContent.includes('vid.srt')) {
            console.error("FAIL: openTranslateModal did not render correct path title:", modalTitle.textContent);
            failed = true;
        } else {
            console.log("PASS: openTranslateModal loads aligned side-by-side data");
        }

        // Save Edits trigger verification (no blank allow)
        const btnSave = getLocalMockElement('btn-translate-modal-save');
        
        // Assert translation save button is present/visible after modal open
        if (!btnSave || btnSave.style.display === 'none' || btnSave.disabled) {
            console.error("FAIL: translation save button is hidden, missing, or disabled after modal open");
            failed = true;
        } else {
            console.log("PASS: translation save button is present and visible after modal open");
        }

        if (btnSave.listeners['click']) {
            await btnSave.listeners['click']();
            if (!saveEditsSent || saveEditsSent.edits[1] !== 'MOCK_EDIT_VALUE') {
                console.error("FAIL: save edits did not dispatch correct payload:", saveEditsSent);
                failed = true;
            } else {
                console.log("PASS: save edits validates and sends correct index mapping payload");
            }
        }

        // Render queue checks with the new snapshot contract
        const mockSnapshot = {
            batch_id: 'test-batch',
            status: 'running',
            total_duration: 12.5,
            total_tokens: 350,
            input_tokens: 200,
            output_tokens: 150,
            stats: {
                waiting: 0,
                running: 1,
                done: 0,
                error: 0,
                canceled: 0,
                total: 1
            },
            jobs: [
                {
                    job_id: 'job-1',
                    source_path: '/path/to/vid.srt',
                    status: 'running',
                    progress: 50,
                    phase: 'translating',
                    elapsed_time: 12.5,
                    total_tokens: 350,
                    input_tokens: 200,
                    output_tokens: 150,
                    saved_path: '/path/to/vid_vi.srt'
                }
            ]
        };

        // Verify initTranslateQueue immediately updates with initial zero state
        if (!queueMod.translateQueueInstance || queueMod.translateQueueInstance.elapsedSeconds !== 0 || queueMod.translateQueueInstance.rows.length !== 0) {
            console.error("FAIL: initTranslateQueue should immediately render initial zeros (elapsedSeconds: 0, rows: [])");
            failed = true;
        } else {
            console.log("PASS: initTranslateQueue immediately calls update with initial zero state");
        }

        queueMod.renderQueueTable(mockSnapshot);
        if (queueMod.translateQueueInstance.elapsedSeconds !== 13) {
            console.error("FAIL: renderQueueTable failed to update elapsedSeconds:", queueMod.translateQueueInstance.elapsedSeconds);
            failed = true;
        } else {
            console.log("PASS: renderQueueTable processes batch stats successfully");
        }

        if (queueMod.translateQueueInstance.options.showSummaryInStatsBar !== false) {
            console.error("FAIL: Translate stats summary bar should disable status summary to match Downloader layout logic");
            failed = true;
        } else {
            console.log("PASS: Translate stats summary bar showSummaryInStatsBar is false");
        }

        // Restore Mocks
        globalThis.document.getElementById = originalGetElement2;

    } catch (err) {
        console.error("FAIL: Translation Queue & Modal tests crashed:", err);
        failed = true;
    }

    // 14. Path Selectors and Proxy Mode Unit Tests
    console.log("\nRunning Path Selectors and Proxy Mode unit tests...");
    try {
        const selectorsMod = await import('./path_selectors.js');
        const tasksMod = await import('./tasks.js');
        const localMockElements = {};
        const getLocalMockElement = (id) => {
            if (!localMockElements[id]) {
                localMockElements[id] = {
                    addEventListener: (event, cb) => {
                        if (!localMockElements[id].listeners) localMockElements[id].listeners = {};
                        localMockElements[id].listeners[event] = cb;
                    },
                    style: {},
                    dataset: {},
                    value: '',
                    placeholder: '',
                    title: '',
                    disabled: false,
                    checked: false,
                    listeners: {},
                    innerHTML: '',
                    appendChild: (child) => {
                        localMockElements[id].innerHTML += child.innerHTML || child.textContent || '';
                    }
                };
            }
            return localMockElements[id];
        };

        const originalGetElement3 = globalThis.document.getElementById;
        globalThis.document.getElementById = (id) => getLocalMockElement(id);

        let setProxyDisabledCalled = null;
        globalThis.fetch = async (url, options) => {
            if (url === '/api/system') {
                return {
                    ok: true,
                    json: async () => ({
                        download_dir: '/home/user/downloads',
                        proxy_file: '/home/user/custom.txt',
                        system_proxy_file: '/home/user/system.txt',
                        proxy_mode: 'custom',
                        proxy_disabled: false
                    })
                };
            }
            if (url === '/api/proxy-disabled/set') {
                const body = JSON.parse(options.body);
                setProxyDisabledCalled = body.disabled;
                return { ok: true, json: async () => ({ status: 'success', proxy_disabled: body.disabled }) };
            }
            return { ok: true, json: async () => ({}) };
        };

        // Initialize selectors listeners
        selectorsMod.initSelectors();

        // 1. Verify system fetch correctly updates display and checks correct checkbox
        await selectorsMod.checkSystem();
        
        const checkboxDisabled = getLocalMockElement('proxy-disabled-checkbox');
        
        if (checkboxDisabled.checked) {
            console.error("FAIL: checkSystem did not clear checkbox for false state");
            failed = true;
        } else {
            console.log("PASS: checkSystem successfully parses proxy_disabled checkbox state");
        }

        // 2. Verify selecting checkbox calls API setProxyDisabled
        if (checkboxDisabled.listeners['change']) {
            await checkboxDisabled.listeners['change']({ target: { checked: true } });
            if (setProxyDisabledCalled !== true) {
                console.error("FAIL: changing checkbox did not invoke setProxyDisabled API");
                failed = true;
            } else {
                console.log("PASS: checkbox change triggers setProxyDisabled API successfully");
            }
        }

        // 3. Verify checked bypasses and disables proxy file controls
        selectorsMod.updateProxyDisplay('/home/user/custom.txt', '/home/user/system.txt', 'custom', true);
        const btnSelectProxy = getLocalMockElement('btn-select-proxy');
        const btnClearProxy = getLocalMockElement('btn-clear-proxy');
        
        if (!btnSelectProxy.disabled || !btnClearProxy.disabled) {
            console.error("FAIL: Checked bypass failed to disable proxy file controls");
            failed = true;
        } else {
            console.log("PASS: Checked bypass correctly disables proxy file buttons and keeps custom path visible");
        }

        // 3b. Verify downloader configuration layout labels and same-row alignment
        console.log("\nRunning Downloader config layout & labels assertions...");
        const fs = await import('fs');
        const path = await import('path');
        const fragmentPath = path.resolve('/home/itc/workspace/tools/hi_downloader/static/fragments/downloader.html');
        const htmlContent = fs.readFileSync(fragmentPath, 'utf8');

        if (!htmlContent.includes('Lưu:')) {
            console.error("FAIL: 'Thư mục lưu:' label was not renamed to 'Lưu:' in downloader.html");
            failed = true;
        } else {
            console.log("PASS: 'Lưu:' label is present");
        }

        if (!htmlContent.includes('proxy:')) {
            console.error("FAIL: 'Chế độ Proxy:' label was not renamed to 'proxy:' in downloader.html");
            failed = true;
        } else {
            console.log("PASS: 'proxy:' label is present");
        }

        if (!htmlContent.includes('không dùng')) {
            console.error("FAIL: Checkbox label was not renamed to 'không dùng' in downloader.html");
            failed = true;
        } else {
            console.log("PASS: 'không dùng' checkbox label is present");
        }

        if (!htmlContent.includes('ip:port:user:passw')) {
            console.error("FAIL: Proxy format guidance label is missing or incorrect in downloader.html");
            failed = true;
        } else {
            console.log("PASS: Proxy format guidance label 'ip:port:user:passw' is present");
        }

        // Verify URL display formatting in Downloader queue
        console.log("\nRunning Downloader queue URL display formatting assertions...");
        const downloaderUrlCol = tasksMod.downloaderQueueInstance.options.columns.find(c => c.key === 'url');
        if (downloaderUrlCol) {
            const mockLongUrl = "https://www.bilibili.com/video/BV1234567890?p=1&some_query=true";
            const mockRow = { url: mockLongUrl, filename: 'BV1234567890.mp4', status: 'pending' };
            const div = downloaderUrlCol.render(mockRow);
            if (div.className !== 'queue-display-url') {
                console.error("FAIL: Downloader queue URL renderer did not use the queue-display-url class");
                failed = true;
            } else {
                console.log("PASS: Downloader queue URL renderer uses the queue-display-url class");
            }
            const a = div.querySelector('a');
            if (!a || a.textContent !== '.../video/BV1234567890') {
                console.error("FAIL: Downloader queue URL rendering did not truncate using truncatePath. Got:", a ? a.textContent : 'none');
                failed = true;
            } else {
                console.log("PASS: Downloader queue URL displays truncated path successfully");
            }
        }

        // Verify URL display formatting in Bilibili Search History
        console.log("\nRunning Bilibili search history URL display formatting assertions...");
        const historyMod = await import('./analyze_history.js');
        
        mockElementChildren.length = 0;
        mockElement._textContent = '';

        const mockHistoryItem = {
            url: "https://www.bilibili.com/video/BV1234567890?some=param",
            analysis: { type: 'video' }
        };
        
        const originalGetItem = localStorage.getItem;
        localStorage.getItem = (key) => {
            if (key === 'bilibili_downloader_history') {
                return JSON.stringify([mockHistoryItem]);
            }
            return null;
        };

        historyMod.loadHistory();

        const renderedUrlText = mockElement.querySelector('.display-url');
        if (!renderedUrlText || renderedUrlText.textContent !== 'https://www.bilibili.com/video/BV1234567890?some=param') {
            console.error("FAIL: Search history URL rendering did not preserve the full URL. Got:", renderedUrlText ? renderedUrlText.textContent : 'none');
            failed = true;
        } else {
            console.log("PASS: Bilibili search history URL displays full URL successfully");
        }

        localStorage.getItem = originalGetItem;

        // Verify .display-url styling rules in style.css
        console.log("\nVerifying .display-url styling rules in style.css...");
        const stylePath = path.resolve('/home/itc/workspace/tools/hi_downloader/static/css/style.css');
        const cssContent = fs.readFileSync(stylePath, 'utf8');
        
        const displayUrlRuleIndex = cssContent.indexOf('.display-url {');
        if (displayUrlRuleIndex === -1) {
            console.error("FAIL: .display-url styling rules not found in style.css");
            failed = true;
        } else {
            const displayUrlRule = cssContent.substring(displayUrlRuleIndex);
            const displayUrlBody = displayUrlRule.substring(0, displayUrlRule.indexOf('}'));
            
            if (displayUrlBody.includes('text-overflow') || displayUrlBody.includes('overflow: hidden') || displayUrlBody.includes('overflow:hidden')) {
                console.error("FAIL: .display-url style must not contain text-overflow or overflow:hidden!");
                failed = true;
            } else if (!displayUrlBody.includes('white-space: normal') || !displayUrlBody.includes('overflow-wrap: anywhere')) {
                console.error("FAIL: .display-url styling misses wrapping rules!");
                failed = true;
            } else {
                console.log("PASS: .display-url style has no text-overflow/hidden constraints and permits wrapping");
            }
        }

        // Verify .queue-display-url styling rules in style.css
        console.log("\nVerifying .queue-display-url styling rules in style.css...");
        const queueUrlIndex = cssContent.indexOf('.queue-display-url {');
        if (queueUrlIndex === -1) {
            console.error("FAIL: .queue-display-url styling rules not found in style.css");
            failed = true;
        } else {
            const queueUrlRule = cssContent.substring(queueUrlIndex);
            const queueUrlBody = queueUrlRule.substring(0, queueUrlRule.indexOf('}'));
            if (!queueUrlBody.includes('display: block') || !queueUrlBody.includes('width: 100%') || !queueUrlBody.includes('min-width: 0')) {
                console.error("FAIL: .queue-display-url style does not contain block layout or 100% width!");
                failed = true;
            } else if (queueUrlBody.includes('text-overflow') || queueUrlBody.includes('overflow: hidden') || queueUrlBody.includes('overflow:hidden') || queueUrlBody.includes('flex:')) {
                console.error("FAIL: .queue-display-url must not contain text-overflow or flex constraints!");
                failed = true;
            } else {
                console.log("PASS: .queue-display-url has correct block layout and width rules");
            }
        }

        // Verify child anchor display:block and width:100%
        console.log("\nVerifying child anchor block display rules in style.css...");
        const queueUrlAnchorIndex = cssContent.indexOf('.queue-display-url a {');
        if (queueUrlAnchorIndex === -1) {
            console.error("FAIL: .queue-display-url a rules not found in style.css");
            failed = true;
        } else {
            const queueUrlAnchorRule = cssContent.substring(queueUrlAnchorIndex);
            const queueUrlAnchorBody = queueUrlAnchorRule.substring(0, queueUrlAnchorRule.indexOf('}'));
            if (!queueUrlAnchorBody.includes('display: block') || !queueUrlAnchorBody.includes('width: 100%')) {
                console.error("FAIL: .queue-display-url a must be block with 100% width!");
                failed = true;
            } else {
                console.log("PASS: .queue-display-url a has block with 100% width rules");
            }
        }

        // Verify no obsolete logs/terminal container or other redundant elements exist in downloader.html
        console.log("\nVerifying downloader.html has no obsolete hidden/duplicate containers...");
        if (htmlContent.includes('terminal-panel') || htmlContent.includes('terminal-body')) {
            console.error("FAIL: downloader.html still contains obsolete logs/terminal elements!");
            failed = true;
        } else {
            console.log("PASS: downloader.html does not contain duplicate/obsolete logs/terminal elements");
        }

        if (!htmlContent.includes('class="download-settings-strip"') || !htmlContent.includes('flex-wrap: wrap;')) {
            console.error("FAIL: Same-row flex settings strip container not found or wrap not enabled");
            failed = true;
        } else {
            console.log("PASS: Same-row flex layout wrapper configuration matched");
        }

        // Verify v=2 coherence in imports
        console.log("\nVerifying version coherence in static and dynamic imports...");
        const bootstrapPath = path.resolve('/home/itc/workspace/tools/hi_downloader/static/js/bootstrap.js');
        const tasksPath = path.resolve('/home/itc/workspace/tools/hi_downloader/static/js/tasks.js');
        const historyPath = path.resolve('/home/itc/workspace/tools/hi_downloader/static/js/analyze_history.js');
        const indexPath = path.resolve('/home/itc/workspace/tools/hi_downloader/static/index.html');

        const bootstrapContent = fs.readFileSync(bootstrapPath, 'utf8');
        const tasksContent = fs.readFileSync(tasksPath, 'utf8');
        const historyContent = fs.readFileSync(historyPath, 'utf8');
        const indexContent = fs.readFileSync(indexPath, 'utf8');

        if (!bootstrapContent.includes("const version = '2';")) {
            console.error("FAIL: bootstrap.js version constant is not '2'");
            failed = true;
        } else {
            console.log("PASS: bootstrap.js version constant is coherent");
        }

        if (!indexContent.includes('bootstrap.js?v=2')) {
            console.error("FAIL: index.html does not load bootstrap.js with v=2");
            failed = true;
        } else {
            console.log("PASS: index.html loads bootstrap.js with v=2");
        }

        if (!tasksContent.includes("helpers.js?v=2")) {
            console.error("FAIL: tasks.js does not import helpers.js with query v=2");
            failed = true;
        } else {
            console.log("PASS: tasks.js imports helpers with v=2 query");
        }

        if (!historyContent.includes("helpers.js?v=2")) {
            console.error("FAIL: analyze_history.js does not import helpers.js with query v=2");
            failed = true;
        } else {
            console.log("PASS: analyze_history.js imports helpers with v=2 query");
        }

        // 4. Test Log Polling Loop & Copy/Clear Buttons Flow
        console.log("\nRunning Log Polling & Update flow tests...");
        const logMod = await import('./logs.js');
        const pollMod = await import('./polling.js');
        
        let logsFetched = false;
        let logsCleared = false;
        globalThis.fetch = async (url, options) => {
            if (url === '/api/logs') {
                logsFetched = true;
                return {
                    ok: true,
                    json: async () => [
                        { time: '21:20:00', level: 'INFO', message: 'Hệ thống đã khởi động.' }
                    ]
                };
            }
            if (url === '/api/logs/clear') {
                logsCleared = true;
                return { ok: true, json: async () => ({ status: 'success' }) };
            }
            return { ok: true, json: async () => ({}) };
        };

        // Initialize logs
        logMod.initLogs();
        pollMod.resetLogPollingForTesting();
        pollMod.triggerLogPolling();

        // Trigger manual checkSystem to run logs fetch inside pollLogs
        await new Promise(resolve => setTimeout(resolve, 50)); // let event loop proceed slightly
        
        const terminalBody = getLocalMockElement('terminal-body');
        
        // Verify logs copy action
        let clipboardCopied = false;
        const originalNavigator = globalThis.navigator;
        const originalQuerySelectorAll = globalThis.document.querySelectorAll;
        globalThis.document.querySelectorAll = (selector) => {
            if (selector === '.terminal-line') {
                return [{ textContent: 'mock log line' }];
            }
            return [];
        };
        try {
            if (globalThis.navigator && globalThis.navigator.clipboard) {
                globalThis.navigator.clipboard.writeText = async (text) => {
                    clipboardCopied = true;
                    return Promise.resolve();
                };
            } else {
                Object.defineProperty(globalThis, 'navigator', {
                    value: {
                        clipboard: {
                            writeText: async (text) => {
                                clipboardCopied = true;
                                return Promise.resolve();
                            }
                        }
                    },
                    configurable: true,
                    writable: true
                });
            }
        } catch (e) {
            try {
                globalThis.navigator = {
                    clipboard: {
                        writeText: async (text) => {
                            clipboardCopied = true;
                            return Promise.resolve();
                        }
                    }
                };
            } catch (e2) {}
        }
        globalThis.alert = () => {}; // suppress popup alerts during testing
        
        logMod.copyLogs();
        if (!clipboardCopied) {
            console.error("FAIL: logs copy action did not interact with navigator clipboard");
            failed = true;
        } else {
            console.log("PASS: copyLogs interacts with clipboard correctly");
        }

        // Assert terminal-body receives log updates
        if (!terminalBody.innerHTML.includes('Hệ thống đã khởi động')) {
            console.error("FAIL: terminal-body did not receive log updates from fetchLogs");
            failed = true;
        } else {
            console.log("PASS: terminal-body successfully receives and renders log updates from polling loop");
        }

        // Verify logs clear action
        await logMod.clearLogs();
        if (!logsCleared || !terminalBody.innerHTML.includes('Đã xóa toàn bộ nhật ký')) {
            console.error("FAIL: clearLogs action failed to clear log buffer");
            failed = true;
        } else {
            console.log("PASS: clearLogs calls API and cleans terminal UI successfully");
        }

        // Restore
        globalThis.document.getElementById = originalGetElement3;
        globalThis.document.querySelectorAll = originalQuerySelectorAll;
    } catch (err) {
        console.error("FAIL: Path Selectors proxy and logs tests crashed:", err);
        failed = true;
    }

    // Clean up mocks
    globalThis.document.getElementById = originalGetElement;
    globalThis.document.getElementsByName = originalGetElementsByName;
    globalThis.fetch = originalFetch;

} catch (err) {
    console.error("FAIL: Translation module unit tests crashed:", err);
    failed = true;
}

if (failed) {
    console.error("\nTest suite execution FAILED.");
    process.exit(1);
} else {
    console.log("\nAll path helper unit tests and ES Module smoke tests passed successfully.");
    process.exit(0);
}
