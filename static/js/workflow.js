import * as api from './api.js';
import { JobQueue } from './job_queue.js';
import { onTasksUpdated, triggerTaskPolling, triggerLogPolling } from './polling.js';
import { truncatePath } from './helpers.js';
import { workflowConfigRegistry, updateSummaryAndBindings } from './workflow_config.js?v=6';




export let sourceMode = 'url';
export let selectedVideo = '';
export let activeTaskId = '';
export let queue;

export function active(task) {
  return ['pending', 'processing', 'downloading', 'merging'].includes(task.status);
}

export function status(task) {
  if (task.status === 'completed') return 'done';
  if (active(task)) {
    return task.status === 'pending' ? 'waiting' : 'running';
  }
  return 'error';
}

export function canRetry(task) {
  return ['failed', 'canceled'].includes(task.status);
}

export function getVietnameseStatusLabel(task) {
  if (task.status === 'completed') return 'Hoàn thành';
  if (task.status === 'canceled') return 'Đã hủy';
  if (task.status === 'failed') return `Lỗi: ${task.error || 'Thao tác thất bại'}`;
  
  if (task.status === 'pending') return 'Đang chờ';
  if (task.status === 'downloading') return 'Đang tải video';
  if (task.status === 'merging') return 'Đang ghép video/âm thanh';
  
  if (task.filename) {
    let label = task.filename;
    label = label.replace(/Step (\d+)\/(\d+)/g, 'Bước $1/$2');
    label = label.replace(/: download/g, ': Tải video');
    label = label.replace(/: subtitle/g, ': Tạo phụ đề');
    label = label.replace(/: translate/g, ': Dịch phụ đề');
    label = label.replace(/ - preparing/g, ' - Đang chuẩn bị');
    label = label.replace(/ - downloading/g, ' - Đang tải');
    label = label.replace(/ - transcribing/g, ' - Đang nhận dạng');
    label = label.replace(/ - translating/g, ' - Đang dịch');
    label = label.replace(/ - formatting/g, ' - Đang định dạng');
    return label;
  }
  
  if (task.status === 'processing') return 'Đang xử lý';
  return task.status || '';
}

export function renderSource(task) {
  const div = document.createElement('div');
  div.style.fontWeight = '600';
  let text = task.source_key || task.filename || 'Không rõ';
  if (text.startsWith('file:')) {
    const path = text.substring(5);
    text = 'file:' + truncatePath(path);
  } else if (text.startsWith('url:')) {
    const url = text.substring(4);
    text = 'url:' + truncatePath(url);
  }
  div.textContent = text;
  div.title = task.source_key || task.filename || '';
  return div;
}

export function renderProgress(task) {
  const container = document.createElement('div');
  container.style.display = 'flex';
  container.style.flexDirection = 'column';
  container.style.gap = '4px';
  container.style.width = '100%';

  const track = document.createElement('div');
  track.className = 'progress-track';
  track.style.margin = '0';

  const bar = document.createElement('div');
  bar.className = 'progress-bar';

  let pct = 0;
  if (task.status === 'completed') pct = 100;
  else if (active(task)) pct = Math.round(task.progress || 0);

  bar.style.width = `${pct}%`;
  track.appendChild(bar);

  const text = document.createElement('span');
  text.style.fontSize = '0.68rem';
  text.style.fontWeight = '600';

  let statusColor = 'var(--text-muted)';
  if (task.status === 'completed') {
    statusColor = '#16a34a';
  } else if (active(task)) {
    statusColor = '#ca8a04';
  } else if (task.status === 'failed') {
    statusColor = '#dc2626';
  } else if (task.status === 'canceled') {
    statusColor = '#ef4444';
  }
  text.style.color = statusColor;
  text.textContent = getVietnameseStatusLabel(task);

  container.appendChild(track);
  container.appendChild(text);
  return container;
}

export function payload() {
  const steps = [];
  workflowConfigRegistry.forEach(def => {
    if (def.enabled()) {
      steps.push(def.buildStep());
    }
  });
  return {
    name: 'Video sang phụ đề',
    steps,
    initial_inputs: sourceMode === 'file' && selectedVideo ? [selectedVideo] : [],
    output_dir: sourceMode === 'url' ? document.getElementById('workflow-output-dir').value : null
  };
}

export function showErrors(errors) {
  document.getElementById('workflow-validation').textContent = errors.join(' ');
}

export function initWorkflow() {
  const run = document.getElementById('btn-workflow-run');
  if (!run) return;

  queue = new JobQueue(document.getElementById('workflow-queue'), {
    selectable: true,
    showSummaryInStatsBar: true,
    labels: {
      empty: "Hàng chờ trống. Vui lòng thiết lập cấu hình và nhấn nút chạy.",
      total: "Tổng",
      waiting: "Chờ",
      running: "Đang chạy",
      done: "Hoàn thành",
      error: "Lỗi/Hủy",
      elapsed: "Thời gian chạy"
    },
    getRowId: row => row.task_id,
    normalizeStatus: status,
    columns: [
      {
        key: 'source',
        label: 'Nguồn',
        width: '40%',
        render: renderSource
      },
      {
        key: 'progress',
        label: 'Trạng thái/Tiến trình',
        width: '45%',
        render: renderProgress
      },
      {
        key: 'actions',
        label: 'Thao tác',
        width: '15%',
        render: row => {
          const container = document.createElement('div');
          container.style.display = 'flex';
          container.style.justifyContent = 'center';
          container.style.gap = '8px';

          // 1. Folder Button
          const btnFolder = document.createElement('button');
          btnFolder.type = 'button';
          btnFolder.className = 'btn-row-action';
          btnFolder.setAttribute('aria-label', 'Mở thư mục');
          btnFolder.title = 'Mở thư mục';
          btnFolder.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2z"></path>
            </svg>
          `;
          if (!active(row)) {
            btnFolder.disabled = false;
            btnFolder.addEventListener('click', async (e) => {
              e.stopPropagation();
              btnFolder.disabled = true;
              try {
                const res = await api.openFolder(row.task_id);
                if (!res.ok) alert("Không thể mở vị trí thư mục.");
              } catch (err) {
                alert("Lỗi kết nối: " + err.message);
              } finally {
                btnFolder.disabled = false;
              }
            });
          } else {
            btnFolder.disabled = true;
          }

          // 2. Cancel Button
          const btnCancel = document.createElement('button');
          btnCancel.type = 'button';
          btnCancel.className = 'btn-row-action';
          btnCancel.setAttribute('aria-label', 'Hủy');
          btnCancel.title = 'Hủy';
          btnCancel.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          `;
          if (active(row)) {
            btnCancel.disabled = false;
            btnCancel.addEventListener('click', async (e) => {
              e.stopPropagation();
              btnCancel.disabled = true;
              try {
                await api.cancelTask(row.task_id);
                triggerTaskPolling();
              } catch (err) {
                alert("Lỗi: " + err.message);
              } finally {
                btnCancel.disabled = false;
              }
            });
          } else {
            btnCancel.disabled = true;
          }

          // 3. Retry Button
          const btnRetry = document.createElement('button');
          btnRetry.type = 'button';
          btnRetry.className = 'btn-row-action';
          btnRetry.setAttribute('aria-label', 'Chạy lại');
          btnRetry.title = 'Chạy lại';
          btnRetry.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M23 4v6h-6"></path>
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L20 8"></path>
            </svg>
          `;
          const isRetryable = canRetry(row);
          if (isRetryable) {
            btnRetry.disabled = false;
            btnRetry.addEventListener('click', async (e) => {
              e.stopPropagation();
              btnRetry.disabled = true;
              showErrors([]);
              try {
                const result = await api.retryWorkflow(row.task_id);
                activeTaskId = result.task_id;
                triggerTaskPolling();
              } catch (err) {
                showErrors([err.message]);
              } finally {
                btnRetry.disabled = false;
              }
            });
          } else {
            btnRetry.disabled = true;
          }

          container.appendChild(btnFolder);
          container.appendChild(btnCancel);
          container.appendChild(btnRetry);
          return container;
        }
      }
    ],
    selectionGroups: [
      { value: 'waiting', label: 'Chờ', matches: (r, norm) => norm === 'waiting' },
      { value: 'running', label: 'Đang chạy', matches: (r, norm) => norm === 'running' },
      { value: 'done', label: 'Hoàn thành', matches: (r, norm) => norm === 'done' },
      { value: 'error', label: 'Lỗi hoặc đã hủy', matches: (r, norm) => norm === 'error' }
    ],
    bulkActions: [
      {
        id: 'cancel',
        label: 'Hủy',
        eligible: r => active(r),
        onInvoke: async (ids) => {
          if (ids.length === 0) return;
          try {
            await Promise.all(ids.map(id => api.cancelTask(id)));
            triggerTaskPolling();
            if (queue) {
              queue.selectedRowIds.clear();
              queue.updateBulkActionsToolbar();
            }
          } catch (err) {
            alert("Lỗi khi hủy các tác vụ: " + err.message);
          }
        }
      },
      {
        id: 'retry',
        label: 'Chạy lại',
        eligible: canRetry,
        onInvoke: async (ids) => {
          if (ids.length === 0) return;
          showErrors([]);
          const errors = [];
          let lastStartedTaskId = null;
          for (const id of ids) {
            try {
              const result = await api.retryWorkflow(id);
              lastStartedTaskId = result.task_id;
            } catch (err) {
              errors.push(`${id}: ${err.message}`);
            }
          }
          if (lastStartedTaskId) {
            activeTaskId = lastStartedTaskId;
          }
          triggerTaskPolling();
          if (queue) {
            queue.selectedRowIds.clear();
            queue.updateBulkActionsToolbar();
          }
          if (errors.length > 0) {
            showErrors(errors);
          }
        }
      },
      {
        id: 'folder',
        label: 'Mở thư mục',
        eligible: r => !active(r),
        onInvoke: async (ids, rows) => {
          if (rows.length === 0) return;
          try {
            await Promise.all(rows.map(async r => {
              try {
                await api.openFolder(r.task_id);
              } catch (e) {
                console.error("Failed to open folder:", e);
              }
            }));
          } catch (err) {
            alert("Lỗi khi mở thư mục: " + err.message);
          }
        }
      }
    ],
    rowActions: [
      { id: 'cancel', label: 'Hủy', visible: active, onInvoke: t => api.cancelTask(t.task_id).then(triggerTaskPolling) },
      { id: 'folder', label: 'Mở thư mục', visible: t => !active(t), onInvoke: t => api.openFolder(t.task_id) },
      { id: 'retry', label: 'Chạy lại', visible: canRetry, onInvoke: t => api.retryWorkflow(t.task_id).then(r => { activeTaskId = r.task_id; triggerTaskPolling(); }).catch(e => showErrors([e.message])) }
    ]
  });

  // Call queue update with initial empty list
  queue.update({ rows: [] });

  onTasksUpdated(tasks => {
    const rows = tasks.filter(t => t.module_id === 'workflow');
    queue.update({ rows });
  });

  triggerTaskPolling();
  triggerLogPolling();

  document.querySelectorAll('[data-workflow-source]').forEach(button => {
    button.addEventListener('click', () => {
      sourceMode = button.dataset.workflowSource;
      document.querySelectorAll('[data-workflow-source]').forEach(b => b.classList.toggle('active', b === button));
      document.getElementById('workflow-url-source').hidden = sourceMode !== 'url';
      document.getElementById('workflow-file-source').hidden = sourceMode !== 'file';
      updateSummaryAndBindings();
    });
  });

  document.getElementById('btn-workflow-select-video').addEventListener('click', async () => {
    const res = await api.selectVideoFile();
    const data = await res.json();
    if (data.path) {
      selectedVideo = data.path;
      document.getElementById('workflow-video-label').textContent = data.path;
      updateSummaryAndBindings();
    }
  });

  document.getElementById('btn-workflow-select-dir').addEventListener('click', async () => {
    const res = await api.selectWorkflowOutputDirectory();
    const data = await res.json();
    if (data.path) {
      const outputDirInput = document.getElementById('workflow-output-dir');
      if (outputDirInput) {
        outputDirInput.value = data.path;
        outputDirInput.title = data.path;
      }
      updateSummaryAndBindings();
    }
  });


  // Bind change events to dynamic UI states updates
  const translateToggle = document.getElementById('workflow-translate-enabled');
  if (translateToggle) {
    translateToggle.addEventListener('click', () => {
      const enabled = translateToggle.getAttribute('aria-pressed') === 'true';
      translateToggle.setAttribute('aria-pressed', String(!enabled));
      translateToggle.classList.toggle('off', enabled);
      updateSummaryAndBindings();
    });
  }
  const timeConstraintCheckbox = document.getElementById('workflow-translate-time-constraint');
  if (timeConstraintCheckbox) {
    timeConstraintCheckbox.addEventListener('change', updateSummaryAndBindings);
  }


  run.addEventListener('click', async () => {
    // Run local validations for enabled modules
    const localErrors = [];
    workflowConfigRegistry.forEach(def => {
      if (def.enabled()) {
        localErrors.push(...def.validate());
      }
    });
    if (localErrors.length > 0) {
      return showErrors(localErrors);
    }

    const data = payload();
    const check = await api.validateWorkflow(data);
    if (!check.valid) return showErrors(check.errors);
    showErrors([]);
    try {
      const result = await api.runWorkflow(data);
      activeTaskId = result.task_id;
      triggerTaskPolling();
    } catch (error) {
      showErrors([error.message]);
    }
  });

  api.fetchTranslateProfiles().then(items => {
    const profiles = items.profiles || items;
    if (Array.isArray(profiles)) {
      const profileSelect = document.getElementById('workflow-translate-profile');
      if (profileSelect) {
        profileSelect.innerHTML = profiles.map(p => `<option value="${p.profile}">${p.label}</option>`).join('');
      }
    }
    updateSummaryAndBindings();
  });
}
