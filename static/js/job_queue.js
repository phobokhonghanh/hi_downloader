export class JobQueue {
    constructor(root, options) {
        if (!root) throw new Error("Root element is required for JobQueue");
        this.root = root;
        this.options = {
            labels: {
                empty: "Hàng chờ trống",
                total: "Tổng",
                waiting: "Chờ",
                running: "Đang chạy",
                done: "Hoàn thành",
                error: "Lỗi/Hủy",
                elapsed: "Thời gian chạy"
            },
            selectable: false,
            showSummaryInStatsBar: true,
            getRowId: (row) => row.id,
            normalizeStatus: (row) => "waiting", // returns 'waiting'|'running'|'done'|'error'
            columns: [], // { key, label, width, render(row) }
            selectionGroups: [], // { value, label, matches(row, normalizedStatus) }
            bulkActions: [], // { id, label, eligible(row), onInvoke(ids, rows) }
            rowActions: [], // { id, label, visible(row), onInvoke(row) }
            onRowClick: null,
            ...options
        };

        this.selectedRowIds = new Set();
        this.rows = [];
        this.elapsedSeconds = 0;
        this.summaryText = "";
        this.summaryTone = "info";

        this.container = null;
        this.initDOM();
        this.bindEvents();
    }

    initDOM() {
        this.root.innerHTML = '';
        
        // Main container
        this.container = document.createElement('div');
        this.container.className = 'shared-queue-container';

        // Stats summary bar
        const statsBar = document.createElement('div');
        statsBar.className = 'shared-queue-stats-bar';
        this.container.appendChild(statsBar);

        // Filter / Toolbar bar
        const toolbarBar = document.createElement('div');
        toolbarBar.className = 'shared-queue-toolbar-bar';
        this.container.appendChild(toolbarBar);

        // Table container
        const tableContainer = document.createElement('div');
        tableContainer.className = 'shared-queue-table-container';

        const table = document.createElement('table');
        table.className = 'shared-queue-table';
        tableContainer.appendChild(table);

        // Header
        const thead = document.createElement('thead');
        const headerTr = document.createElement('tr');

        if (this.options.selectable) {
            const thSelect = document.createElement('th');
            thSelect.className = 'shared-queue-th-select';
            const chkAll = document.createElement('input');
            chkAll.type = 'checkbox';
            chkAll.className = 'shared-queue-select-all';
            thSelect.appendChild(chkAll);
            headerTr.appendChild(thSelect);
        }

        this.options.columns.forEach(col => {
            const th = document.createElement('th');
            if (col.width) th.style.width = col.width;
            th.textContent = col.label;
            headerTr.appendChild(th);
        });

        thead.appendChild(headerTr);
        table.appendChild(thead);

        // Body
        const tbody = document.createElement('tbody');
        tbody.className = 'shared-queue-body';
        table.appendChild(tbody);

        this.container.appendChild(tableContainer);
        this.root.appendChild(this.container);
        this.renderTableBody();
    }

    bindEvents() {
        this.container.addEventListener('change', (e) => {
            if (e.target.classList.contains('shared-queue-select-all')) {
                const checked = e.target.checked;
                const checkboxes = this.container.querySelectorAll('.shared-queue-row-checkbox');
                checkboxes.forEach(cb => {
                    cb.checked = checked;
                    const id = String(cb.dataset.id);
                    if (checked) {
                        this.selectedRowIds.add(id);
                    } else {
                        this.selectedRowIds.delete(id);
                    }
                });
                if (this.options.onSelectionChange) {
                    this.options.onSelectionChange(Array.from(this.selectedRowIds));
                }
                this.updateBulkActionsToolbar();
            } else if (e.target.classList.contains('shared-queue-row-checkbox')) {
                const checked = e.target.checked;
                const id = String(e.target.dataset.id);
                if (checked) {
                    this.selectedRowIds.add(id);
                } else {
                    this.selectedRowIds.delete(id);
                }

                const chkAll = this.container.querySelector('.shared-queue-select-all');
                if (chkAll) {
                    const rowCheckboxes = this.container.querySelectorAll('.shared-queue-row-checkbox');
                    const checkedRowCheckboxes = this.container.querySelectorAll('.shared-queue-row-checkbox:checked');
                    chkAll.checked = rowCheckboxes.length > 0 && rowCheckboxes.length === checkedRowCheckboxes.length;
                }

                if (this.options.onSelectionChange) {
                    this.options.onSelectionChange(Array.from(this.selectedRowIds));
                }
                this.updateBulkActionsToolbar();
            }
        });

        this.container.addEventListener('change', (e) => {
            if (e.target.classList.contains('shared-queue-select-filter')) {
                const filterVal = e.target.value;
                this.applySelectionFilter(filterVal);
            }
        });
    }

    applySelectionFilter(filterVal) {
        if (!this.options.selectable) return;
        
        const checkboxes = this.container.querySelectorAll('.shared-queue-row-checkbox');
        checkboxes.forEach(cb => {
            const id = String(cb.dataset.id);
            const row = this.rows.find(r => String(this.options.getRowId(r)) === id);
            if (!row) return;

            const normalizedStatus = this.options.normalizeStatus(row);
            let match = false;

            if (filterVal === 'all') {
                match = true;
            } else {
                const group = this.options.selectionGroups.find(g => g.value === filterVal);
                if (group) {
                    match = group.matches(row, normalizedStatus);
                } else {
                    match = (normalizedStatus === filterVal);
                }
            }

            cb.checked = match;
            if (match) {
                this.selectedRowIds.add(id);
            } else {
                this.selectedRowIds.delete(id);
            }
        });

        const chkAll = this.container.querySelector('.shared-queue-select-all');
        if (chkAll) {
            const rowCheckboxes = this.container.querySelectorAll('.shared-queue-row-checkbox');
            const checkedRowCheckboxes = this.container.querySelectorAll('.shared-queue-row-checkbox:checked');
            chkAll.checked = rowCheckboxes.length > 0 && rowCheckboxes.length === checkedRowCheckboxes.length;
        }

        if (this.options.onSelectionChange) {
            this.options.onSelectionChange(Array.from(this.selectedRowIds));
        }
        this.updateBulkActionsToolbar();
    }

    updateBulkActionsToolbar() {
        this.options.bulkActions.forEach(action => {
            const btn = this.container.querySelector(`.shared-queue-btn-bulk-${action.id}`);
            if (btn) {
                const anyEligible = Array.from(this.selectedRowIds).some(id => {
                    const row = this.rows.find(r => String(this.options.getRowId(r)) === String(id));
                    return row && (!action.eligible || action.eligible(row));
                });
                btn.disabled = !anyEligible || this.selectedRowIds.size === 0;
            }
        });
    }

    update({ rows = [], elapsedSeconds = 0, summaryText = "", summaryTone = "info" }) {
        this.rows = rows;
        this.elapsedSeconds = elapsedSeconds;
        this.summaryText = summaryText;
        this.summaryTone = summaryTone;

        const currentIds = new Set(rows.map(r => String(this.options.getRowId(r))));
        for (const id of this.selectedRowIds) {
            if (!currentIds.has(String(id))) {
                this.selectedRowIds.delete(id);
            }
        }

        this.renderStats();
        this.renderToolbar();
        this.renderTableBody();
        this.updateBulkActionsToolbar();
    }

    renderStats() {
        const statsBar = this.container.querySelector('.shared-queue-stats-bar');
        if (!statsBar) return;

        const counts = countStatuses(this.rows, this.options.normalizeStatus);

        statsBar.innerHTML = '';

        const leftDiv = document.createElement('div');
        leftDiv.className = 'shared-queue-stats-left';

        const spanTotal = document.createElement('span');
        spanTotal.className = 'shared-queue-stat-total';
        spanTotal.textContent = `${this.options.labels.total}: ${this.rows.length}`;
        leftDiv.appendChild(spanTotal);

        const spanWaiting = document.createElement('span');
        spanWaiting.className = 'shared-queue-stat-waiting';
        spanWaiting.textContent = `${this.options.labels.waiting}: ${counts.waiting}`;
        leftDiv.appendChild(spanWaiting);

        const spanRunning = document.createElement('span');
        spanRunning.className = 'shared-queue-stat-running';
        spanRunning.textContent = `${this.options.labels.running}: ${counts.running}`;
        leftDiv.appendChild(spanRunning);

        const spanDone = document.createElement('span');
        spanDone.className = 'shared-queue-stat-done';
        spanDone.textContent = `${this.options.labels.done}: ${counts.done}`;
        leftDiv.appendChild(spanDone);

        const spanError = document.createElement('span');
        spanError.className = 'shared-queue-stat-error';
        spanError.textContent = `${this.options.labels.error}: ${counts.error}`;
        leftDiv.appendChild(spanError);

        statsBar.appendChild(leftDiv);

        const rightDiv = document.createElement('div');
        rightDiv.className = 'shared-queue-stats-right';

        if (this.summaryText && this.options.showSummaryInStatsBar) {
            const summarySpan = document.createElement('span');
            summarySpan.className = `shared-queue-summary-text tone-${this.summaryTone}`;
            summarySpan.textContent = this.summaryText;
            rightDiv.appendChild(summarySpan);
        }

        const elapsedSpan = document.createElement('span');
        elapsedSpan.className = 'shared-queue-elapsed-time';
        elapsedSpan.textContent = `${this.options.labels.elapsed}: ${this.elapsedSeconds}s`;
        rightDiv.appendChild(elapsedSpan);

        statsBar.appendChild(rightDiv);
    }

    renderToolbar() {
        const toolbarBar = this.container.querySelector('.shared-queue-toolbar-bar');
        if (!toolbarBar) return;

        const hasFilters = this.options.selectable && this.options.selectionGroups.length > 0;
        const hasBulk = this.options.selectable && this.options.bulkActions.length > 0;

        if (!hasFilters && !hasBulk) {
            toolbarBar.style.display = 'none';
            return;
        }
        toolbarBar.style.display = 'flex';
        toolbarBar.innerHTML = '';

        if (hasFilters) {
            const filterGroup = document.createElement('div');
            filterGroup.className = 'shared-queue-filter-group';

            const select = document.createElement('select');
            select.className = 'shared-queue-select-filter';
            select.title = 'Lọc theo trạng thái';
            select.setAttribute('aria-label', 'Lọc theo trạng thái');

            const defOption = document.createElement('option');
            defOption.value = '';
            defOption.textContent = '-- Chọn trạng thái --';
            select.appendChild(defOption);

            const allOption = document.createElement('option');
            allOption.value = 'all';
            allOption.textContent = 'Tất cả';
            select.appendChild(allOption);

            this.options.selectionGroups.forEach(g => {
                const opt = document.createElement('option');
                opt.value = g.value;
                opt.textContent = g.label;
                select.appendChild(opt);
            });

            filterGroup.appendChild(select);
            toolbarBar.appendChild(filterGroup);
        }

        if (hasBulk) {
            const bulkGroup = document.createElement('div');
            bulkGroup.className = 'shared-queue-bulk-group';

            const getIconSvg = (actionId) => {
                if (actionId === 'save') {
                    return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>`;
                }
                if (actionId === 'cancel') {
                    return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`;
                }
                if (actionId === 'retry') {
                    return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M23 4v6h-6"></path><path d="M20.49 15a9 9 0 1 1-2.12-9.36L20 8"></path></svg>`;
                }
                return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="1"></circle><circle cx="19" cy="12" r="1"></circle><circle cx="5" cy="12" r="1"></circle></svg>`;
            };

            this.options.bulkActions.forEach(action => {
                const btn = document.createElement('button');
                btn.type = 'button';
                const actClass = ['save', 'cancel', 'retry'].includes(action.id) ? action.id : 'unknown';
                btn.className = `shared-queue-btn-bulk-icon action-${actClass} shared-queue-btn-bulk-${action.id}`;
                btn.title = action.label;
                btn.setAttribute('aria-label', action.label);
                btn.innerHTML = getIconSvg(action.id);
                btn.disabled = true;
                btn.addEventListener('click', () => {
                    const ids = Array.from(this.selectedRowIds);
                    const selectedRows = this.rows.filter(r => ids.includes(String(this.options.getRowId(r))));
                    action.onInvoke(ids, selectedRows);
                });
                bulkGroup.appendChild(btn);
            });

            toolbarBar.appendChild(bulkGroup);
        }
    }

    renderTableBody() {
        const tbody = this.container.querySelector('.shared-queue-body');
        const chkAll = this.container.querySelector('.shared-queue-select-all');

        if (!tbody) return;

        tbody.innerHTML = '';

        if (this.rows.length === 0) {
            if (chkAll) {
                chkAll.checked = false;
                chkAll.disabled = true;
            }

            const tr = document.createElement('tr');
            tr.className = 'shared-queue-row-empty';

            const td = document.createElement('td');
            const totalCols = this.options.columns.length + (this.options.selectable ? 1 : 0);
            td.setAttribute('colspan', totalCols);
            td.style.textAlign = 'center';
            td.style.padding = '32px 16px';

            const emptyState = document.createElement('div');
            emptyState.className = 'shared-queue-empty-state';
            emptyState.textContent = this.options.labels.empty;
            td.appendChild(emptyState);

            tr.appendChild(td);
            tbody.appendChild(tr);
            return;
        }

        if (chkAll) {
            chkAll.disabled = false;
        }

        this.rows.forEach(row => {
            const rowId = String(this.options.getRowId(row));
            const tr = document.createElement('tr');
            tr.className = `shared-queue-row shared-queue-row-status-${this.options.normalizeStatus(row)}`;
            tr.dataset.id = rowId;

            if (this.options.onRowClick) {
                tr.style.cursor = 'pointer';
                tr.addEventListener('click', (e) => {
                    if (e.target.tagName === 'INPUT' || e.target.tagName === 'BUTTON' || e.target.tagName === 'A' || e.target.closest('button') || e.target.closest('svg')) {
                        return;
                    }
                    this.options.onRowClick(row);
                });
            }

            if (this.options.selectable) {
                const tdCheck = document.createElement('td');
                tdCheck.className = 'shared-queue-td-check';
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.className = 'shared-queue-row-checkbox';
                cb.dataset.id = rowId;
                cb.checked = this.selectedRowIds.has(rowId);
                tdCheck.appendChild(cb);
                tr.appendChild(tdCheck);
            }

            this.options.columns.forEach(col => {
                const td = document.createElement('td');
                
                const rendered = col.render(row);
                const isNode = (typeof Node !== 'undefined') ? (rendered instanceof Node) : (rendered && typeof rendered.nodeType === 'number');
                if (isNode) {
                    td.appendChild(rendered);
                } else {
                    td.textContent = rendered !== null && rendered !== undefined ? String(rendered) : '';
                }
                tr.appendChild(td);
            });

            tbody.appendChild(tr);
        });

        if (chkAll) {
            const rowCheckboxes = this.container.querySelectorAll('.shared-queue-row-checkbox');
            const checkedRowCheckboxes = this.container.querySelectorAll('.shared-queue-row-checkbox:checked');
            chkAll.checked = rowCheckboxes.length > 0 && rowCheckboxes.length === checkedRowCheckboxes.length;
        }
    }

    destroy() {
        this.selectedRowIds.clear();
        this.rows = [];
        if (this.root) {
            this.root.innerHTML = '';
        }
    }
}

export function countStatuses(rows, normalizeStatus) {
    const counts = { waiting: 0, running: 0, done: 0, error: 0 };
    rows.forEach(r => {
        const norm = normalizeStatus(r);
        if (counts.hasOwnProperty(norm)) {
            counts[norm]++;
        }
    });
    return counts;
}

export function filterEligibleIds(rows, getRowId, eligibleFunc, selectedIds) {
    const ids = selectedIds ? new Set(selectedIds.map(id => String(id))) : null;
    return rows
        .filter(r => (!ids || ids.has(String(getRowId(r)))) && eligibleFunc(r))
        .map(r => getRowId(r));
}
