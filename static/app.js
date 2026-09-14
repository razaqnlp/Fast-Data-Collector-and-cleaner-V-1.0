(function () {
  "use strict";
  var shell = document.querySelector('.shell');
  var stepItems = document.querySelectorAll('.step-item');
  var stepPanels = document.querySelectorAll('.step-panel');

  function activateStep(step) {
    stepItems.forEach(function (item) { item.classList.toggle('is-active', item.dataset.step === String(step)); });
    stepPanels.forEach(function (panel) { panel.classList.toggle('is-active', panel.dataset.panel === String(step)); });
  }
  stepItems.forEach(function (item) {
    item.addEventListener('click', function () {
      if (item.dataset.unlocked !== 'false') activateStep(item.dataset.step);
    });
  });
  activateStep((shell && shell.dataset.defaultStep) || '1');

  var panel = document.getElementById('settingsPanel');
  var scrim = document.getElementById('scrim');
  var openSettings = document.getElementById('openSettings');
  var closeSettings = document.getElementById('closeSettings');
  function openPanel() { panel.classList.add('is-open'); scrim.classList.add('is-open'); panel.setAttribute('aria-hidden', 'false'); }
  function closePanel() { panel.classList.remove('is-open'); scrim.classList.remove('is-open'); panel.setAttribute('aria-hidden', 'true'); }
  if (openSettings) openSettings.addEventListener('click', openPanel);
  if (closeSettings) closeSettings.addEventListener('click', closePanel);
  if (scrim) scrim.addEventListener('click', closePanel);
  document.addEventListener('keydown', function (event) { if (event.key === 'Escape') closePanel(); });

  var modeYoutube = document.getElementById('mode-youtube');
  var modeUpload = document.getElementById('mode-upload');
  var panelYoutube = document.getElementById('panel-youtube');
  var panelUpload = document.getElementById('panel-upload');
  var videoId = document.getElementById('video_id');
  var csvFile = document.getElementById('csv_file');
  function syncMode() {
    var upload = modeUpload && modeUpload.checked;
    if (panelYoutube) panelYoutube.hidden = upload;
    if (panelUpload) panelUpload.hidden = !upload;
    if (videoId) videoId.required = !upload;
    if (csvFile) csvFile.required = !!upload;
  }
  if (modeYoutube) modeYoutube.addEventListener('change', syncMode);
  if (modeUpload) modeUpload.addEventListener('change', syncMode);
  syncMode();

  var dropzone = document.getElementById('dropzone');
  var filename = document.getElementById('dzFilename');
  if (csvFile) csvFile.addEventListener('change', function () { filename.textContent = csvFile.files.length ? csvFile.files[0].name : ''; });
  if (dropzone) dropzone.addEventListener('drop', function (event) { event.preventDefault(); if (event.dataTransfer.files.length) { csvFile.files = event.dataTransfer.files; filename.textContent = event.dataTransfer.files[0].name; } });
  if (dropzone) ['dragenter', 'dragover'].forEach(function (name) { dropzone.addEventListener(name, function (event) { event.preventDefault(); dropzone.classList.add('is-dragover'); }); });
  if (dropzone) ['dragleave', 'drop'].forEach(function (name) { dropzone.addEventListener(name, function (event) { event.preventDefault(); dropzone.classList.remove('is-dragover'); }); });

  var mainForm = document.getElementById('mainForm');
  var submitBtn = document.getElementById('submitBtn');
  if (mainForm) mainForm.addEventListener('submit', function (event) {
    if (modeUpload && modeUpload.checked && (!csvFile.files || !csvFile.files.length)) { event.preventDefault(); filename.textContent = 'Choose a CSV file before continuing.'; return; }
    if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = 'Cleaning...'; }
  });

  document.querySelectorAll('.tab').forEach(function (tab) { tab.addEventListener('click', function () { var target = tab.dataset.tab; var parent = tab.closest('.step-panel'); parent.querySelectorAll('.tab').forEach(function (item) { item.classList.toggle('is-active', item === tab); }); parent.querySelectorAll('.tab-panel').forEach(function (panel) { panel.hidden = panel.dataset.panel !== target; }); }); });
  document.querySelectorAll('[data-flash] .flash-close').forEach(function (button) { button.addEventListener('click', function () { button.closest('[data-flash]').remove(); }); });

  var template = document.getElementById('resultCsvData');
  var body = document.getElementById('resultsBody');
  function parseCsv(raw) {
    var rows = [], row = [], field = '', quoted = false;
    for (var i = 0; i < raw.length; i += 1) { var c = raw[i]; if (quoted) { if (c === '"' && raw[i + 1] === '"') { field += '"'; i += 1; } else if (c === '"') quoted = false; else field += c; } else if (c === '"') quoted = true; else if (c === ',') { row.push(field); field = ''; } else if (c === '\n' || c === '\r') { if (c === '\r' && raw[i + 1] === '\n') i += 1; row.push(field); if (row.length) rows.push(row); row = []; field = ''; } else field += c; }
    if (field || row.length) { row.push(field); rows.push(row); } return rows.filter(function (item) { return item[0]; });
  }
  function labelClass(label) {
    var value = (label || '').toLowerCase();
    return value.indexOf('pos') === 0 ? 'pill-positive' : value.indexOf('neg') === 0 ? 'pill-negative' : 'pill-neutral';
  }
  if (template && body) { parseCsv(template.textContent.trim()).forEach(function (cols) { var tr = document.createElement('tr'); var sentence = document.createElement('td'); sentence.textContent = cols[0]; var sentiment = document.createElement('td'); var badge = document.createElement('span'); badge.className = 'pill ' + labelClass(cols[1]); badge.textContent = cols[1] || 'neutral'; sentiment.appendChild(badge); tr.appendChild(sentence); tr.appendChild(sentiment); body.appendChild(tr); }); }
})();
