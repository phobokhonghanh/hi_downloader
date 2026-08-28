export const workflowConfigRegistry = [
  {
    module_id: 'downloader',
    required: false,
    enabled: () => {
      const activeTab = document.querySelector('[data-workflow-source].active');
      return activeTab && activeTab.dataset.workflowSource === 'url';
    },
    validate: () => {
      const urlInput = document.getElementById('workflow-url');
      const dirInput = document.getElementById('workflow-output-dir');
      const url = urlInput ? urlInput.value.trim() : '';
      const dir = dirInput ? dirInput.value.trim() : '';
      
      const errors = [];
      if (!url) {
        errors.push("URL Bilibili không được để trống.");
      }
      if (!dir) {
        errors.push("Thư mục lưu video không được để trống.");
      }
      return errors;
    },
    buildStep: () => {
      const urlInput = document.getElementById('workflow-url');
      return {
        step_id: 'download',
        module_id: 'downloader',
        params: {
          action: 'download',
          url: urlInput ? urlInput.value.trim() : '',
          quality: 'best'
        }
      };
    },
    bindUI: () => {}
  },
  {
    module_id: 'subtitle',
    required: true,
    enabled: () => true,
    validate: () => {
      const activeTab = document.querySelector('[data-workflow-source].active');
      const isFileMode = activeTab && activeTab.dataset.workflowSource === 'file';
      const errors = [];
      if (isFileMode) {
        const videoLabel = document.getElementById('workflow-video-label');
        const text = videoLabel ? videoLabel.textContent.trim() : '';
        if (!text || text === 'Chưa chọn video') {
          errors.push("Vui lòng chọn video nguồn.");
        }
      }
      const modelInput = document.getElementById('workflow-whisper-model');
      if (!modelInput || !modelInput.value.trim()) {
        errors.push("Vui lòng chọn mô hình Whisper.");
      }
      return errors;
    },
    buildStep: () => {
      const modelInput = document.getElementById('workflow-whisper-model');
      const langInput = document.getElementById('workflow-whisper-language');
      return {
        step_id: 'subtitle',
        module_id: 'subtitle',
        params: {
          action: 'generate_whisper',
          use_input_file: true,
          model: modelInput ? modelInput.value.trim() : 'base',
          language: langInput ? langInput.value.trim() : ''
        }
      };
    },
    bindUI: () => {}
  },
  {
    module_id: 'translate',
    required: false,
    enabled: () => {
      const toggle = document.getElementById('workflow-translate-enabled');
      return toggle && toggle.getAttribute('aria-pressed') === 'true';
    },
    validate: () => {
      const errors = [];
      const langInput = document.getElementById('workflow-target-language');
      const profileInput = document.getElementById('workflow-translate-profile');
      if (!langInput || !langInput.value.trim()) {
        errors.push("Vui lòng chọn ngôn ngữ đích.");
      }
      if (!profileInput || !profileInput.value.trim()) {
        errors.push("Vui lòng cấu hình dịch.");
      }
      const wpsInput = document.getElementById('workflow-translate-target-wps');
      const constraintInput = document.getElementById('workflow-translate-time-constraint');
      const isConstraintChecked = constraintInput ? constraintInput.checked : true;
      if (wpsInput && isConstraintChecked) {
        const val = parseFloat(wpsInput.value);
        if (isNaN(val) || val < 2.0 || val > 6.0) {
          errors.push("Tốc độ nói mục tiêu phải nằm trong khoảng từ 2.0 đến 6.0.");
        }
      }
      return errors;
    },
    buildStep: () => {
      const langInput = document.getElementById('workflow-target-language');
      const profileInput = document.getElementById('workflow-translate-profile');
      const constraintInput = document.getElementById('workflow-translate-time-constraint');
      const wpsInput = document.getElementById('workflow-translate-target-wps');
      return {
        step_id: 'translate',
        module_id: 'translate',
        params: {
          target_language: langInput ? langInput.value.trim() : 'vi',
          profile: profileInput ? profileInput.value.trim() : 'balanced',
          enable_time_constraint: constraintInput ? constraintInput.checked : true,
          target_wps: wpsInput ? parseFloat(wpsInput.value) : 4.2
        }
      };
    },
    bindUI: () => {
      const enabled = document.getElementById('workflow-translate-enabled')?.getAttribute('aria-pressed') === 'true';
      
      const langSelect = document.getElementById('workflow-target-language');
      const profileSelect = document.getElementById('workflow-translate-profile');
      const constraintCheckbox = document.getElementById('workflow-translate-time-constraint');
      const wpsInput = document.getElementById('workflow-translate-target-wps');
      
      if (langSelect) langSelect.disabled = !enabled;
      if (profileSelect) profileSelect.disabled = !enabled;
      if (constraintCheckbox) constraintCheckbox.disabled = !enabled;
      
      if (wpsInput) {
        const timeConstraintChecked = constraintCheckbox ? constraintCheckbox.checked : true;
        wpsInput.disabled = !enabled || !timeConstraintChecked;
      }

      const bodyEl = document.getElementById('workflow-translate-options');
      if (bodyEl) {
        bodyEl.hidden = !enabled;
      }
    }
  }
];

export function updateSummaryAndBindings() {
  workflowConfigRegistry.forEach(def => {
    if (typeof def.bindUI === 'function') {
      def.bindUI();
    }
  });

  const translateEnabled = document.getElementById('workflow-translate-enabled')?.getAttribute('aria-pressed') === 'true';

  const stepCountEl = document.getElementById('workflow-step-count');
  if (stepCountEl) {
    stepCountEl.textContent = translateEnabled ? "2 bước" : "1 bước";
  }

  const summaryEl = document.getElementById('workflow-summary');
  if (summaryEl) {
    if (translateEnabled) {
      summaryEl.textContent = "Dự kiến tạo 2 file SRT";
    } else {
      summaryEl.textContent = "Dự kiến tạo 1 file SRT";
    }
  }
}


