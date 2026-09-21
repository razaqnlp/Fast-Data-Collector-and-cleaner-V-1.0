(function () {
  "use strict";

  var shell = document.querySelector(".shell");

  /* ---------- step navigation ---------- */
  var navItems = document.querySelectorAll(".nav-item");
  var panels = document.querySelectorAll(".stage-panel, .source-panel");

  function activateStep(n) {
    navItems.forEach(function (item) {
      item.classList.toggle("is-active", item.dataset.step === String(n));
    });
    panels.forEach(function (panel) {
      panel.classList.toggle("is-active", panel.dataset.panel === String(n));
    });
  }

  navItems.forEach(function (item) {
    item.addEventListener("click", function () {
      if (item.dataset.unlocked === "false") return;
      activateStep(item.dataset.step);
    });
  });

  activateStep((shell && shell.dataset.defaultStep) || "1");

  /* ---------- collector source controls ---------- */
  var youtubeChoice = document.getElementById("youtubeChoice");
  var youtubeCollector = document.getElementById("youtubeCollector");
  if (youtubeChoice && youtubeCollector) {
    function toggleYoutubeCollector() {
      var shouldOpen = youtubeCollector.hidden;
      youtubeCollector.hidden = !shouldOpen;
      youtubeChoice.setAttribute("aria-expanded", String(shouldOpen));
      youtubeChoice.classList.toggle("is-open", shouldOpen);
      var chevron = youtubeChoice.querySelector(".source-chevron");
      if (chevron) chevron.textContent = shouldOpen ? "−" : "+";
    }
    youtubeChoice.addEventListener("click", toggleYoutubeCollector);
    youtubeChoice.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        toggleYoutubeCollector();
      }
    });
  }

  /* ---------- device import filename ---------- */
  var collectorCsvFile = document.getElementById("collector_csv_file");
  var collectorFilename = document.getElementById("collectorFilename");
  if (collectorCsvFile && collectorFilename) {
    collectorCsvFile.addEventListener("change", function () {
      collectorFilename.textContent = collectorCsvFile.files.length ? collectorCsvFile.files[0].name : "";
    });
  }

  /* ---------- YouTube collection state ---------- */
  var youtubeForm = document.getElementById("youtubeForm");
  var youtubeSubmit = document.getElementById("youtubeSubmit");
  var autoDownloadToggle = document.getElementById("autoDownloadToggle");
  var editFilenameToggle = document.getElementById("editFilenameToggle");
  var filenameEditor = document.getElementById("filenameEditor");
  var collectorLoadingStatus = document.getElementById("collectorLoadingStatus");
  var autoDownloadKey = "pul_auto_download";
  var editFilenameKey = "pul_edit_filename";
  if (autoDownloadToggle) {
    autoDownloadToggle.checked = localStorage.getItem(autoDownloadKey) === "true";
    autoDownloadToggle.addEventListener("change", function () {
      localStorage.setItem(autoDownloadKey, String(autoDownloadToggle.checked));
    });
  }
  function updateFilenameEditor() {
    if (filenameEditor && editFilenameToggle) filenameEditor.hidden = !editFilenameToggle.checked;
  }
  if (editFilenameToggle) {
    editFilenameToggle.checked = localStorage.getItem(editFilenameKey) === "true";
    updateFilenameEditor();
    editFilenameToggle.addEventListener("change", function () {
      localStorage.setItem(editFilenameKey, String(editFilenameToggle.checked));
      updateFilenameEditor();
    });
  }
  if (youtubeForm) {
    youtubeForm.addEventListener("submit", function () {
      if (youtubeSubmit) {
        youtubeSubmit.disabled = true;
        youtubeSubmit.querySelector(".button-label").textContent = "Collecting...";
      }
      if (collectorLoadingStatus) collectorLoadingStatus.hidden = false;
    });
  }
  document.querySelectorAll(".duplicate-force-form").forEach(function (form) {
    form.addEventListener("submit", function () {
      if (collectorLoadingStatus) collectorLoadingStatus.hidden = false;
    });
  });
  if (new URLSearchParams(window.location.search).get("collected") === "1" && autoDownloadToggle && autoDownloadToggle.checked) {
    var collectedDownload = document.querySelector('a[href*="/export/collected"]');
    if (collectedDownload) collectedDownload.click();
  }

  /* ---------- imported CSV information ---------- */
  var cleanCsvFile = document.getElementById("csv_file");
  var importInfoTitle = document.getElementById("importInfoTitle");
  var importInfoStatus = document.getElementById("importInfoStatus");
  var importFileSize = document.getElementById("importFileSize");
  var importRowCount = document.getElementById("importRowCount");
  var importColumnCount = document.getElementById("importColumnCount");
  var importCommentColumn = document.getElementById("importCommentColumn");
  var importColumns = document.getElementById("importColumns");

  function parsePreviewRows(text) {
    var lines = text.replace(/^\uFEFF/, "").split(/\r?\n/).filter(function (line) { return line.trim(); });
    return lines;
  }

  function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  function updateImportInfo(file) {
    if (!file || !importInfoTitle) return;
    importInfoTitle.textContent = file.name;
    importInfoStatus.textContent = "Ready to clean";
    importFileSize.textContent = formatFileSize(file.size);
    var reader = new FileReader();
    reader.onload = function () {
      var lines = parsePreviewRows(String(reader.result || ""));
      var headers = lines.length ? lines[0].split(",").map(function (value) { return value.trim().replace(/^"|"$/g, ""); }) : [];
      var commentIndex = headers.findIndex(function (header) { return /comment|text|sentence|message/i.test(header); });
      importRowCount.textContent = Math.max(lines.length - 1, 0).toLocaleString();
      importColumnCount.textContent = headers.length || "-";
      importCommentColumn.textContent = commentIndex >= 0 ? headers[commentIndex] : (headers[0] || "First column");
      importColumns.textContent = headers.length ? "Columns: " + headers.join(" · ") : "Could not read the CSV header.";
    };
    reader.readAsText(file);
  }

  if (cleanCsvFile) {
    cleanCsvFile.addEventListener("change", function () {
      updateImportInfo(cleanCsvFile.files[0]);
    });
  }

  /* ---------- generic tab groups ---------- */
  document.querySelectorAll(".tabs").forEach(function (group) {
    var tabs = group.querySelectorAll(".tab");
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        var target = tab.dataset.tab;
        var container = group.parentElement;
        tabs.forEach(function (t) {
          t.classList.toggle("is-active", t === tab);
          t.setAttribute("aria-selected", t === tab ? "true" : "false");
        });
        container.querySelectorAll(".tab-panel").forEach(function (p) {
          p.hidden = p.dataset.panel !== target;
          p.classList.toggle("is-active", p.dataset.panel === target);
        });
      });
    });
  });

  /* ---------- flash dismiss ---------- */
  document.querySelectorAll(".flash-close").forEach(function (btn) {
    btn.addEventListener("click", function () { btn.closest(".flash").remove(); });
  });

  /* ---------- CSV parsing ---------- */
  function parseCsv(raw) {
    if (!raw) return [];
    var rows = [], row = [], field = "", inQuotes = false;
    raw = raw.trim();
    for (var i = 0; i < raw.length; i++) {
      var c = raw[i];
      if (inQuotes) {
        if (c === '"') { if (raw[i + 1] === '"') { field += '"'; i++; } else inQuotes = false; }
        else field += c;
      } else {
        if (c === '"') inQuotes = true;
        else if (c === ",") { row.push(field); field = ""; }
        else if (c === "\n" || c === "\r") {
          if (c === "\r" && raw[i + 1] === "\n") i++;
          row.push(field); field = ""; rows.push(row); row = [];
        } else field += c;
      }
    }
    if (field.length || row.length) { row.push(field); rows.push(row); }
    if (rows.length && /sentence/i.test(rows[0][0] || "")) rows.shift();
    return rows.filter(function (r) { return r.length && r[0] !== ""; });
  }

  function normalizeLabel(label) {
    label = (label || "").trim().toLowerCase();
    if (label.indexOf("pos") === 0) return "positive";
    if (label.indexOf("neg") === 0) return "negative";
    return "neutral";
  }

  /* ---------- sentiment results table ---------- */
  var csvTemplate = document.getElementById("resultCsvData");
  var resultsBody = document.getElementById("resultsBody");
  var editedRows = {};

  if (csvTemplate && resultsBody) {
    var rows = parseCsv(csvTemplate.content.textContent);
    resultsBody.innerHTML = "";

    rows.forEach(function (r, idx) {
      var sentence = r[0] || "";
      var label = normalizeLabel(r[1]);

      var tr = document.createElement("tr");
      tr.dataset.index = idx;
      tr.dataset.label = label;

      var tdSentence = document.createElement("td");
      tdSentence.textContent = sentence;

      var tdLabel = document.createElement("td");
      var select = document.createElement("select");
      select.className = "label-select " + label;
      ["positive", "negative", "neutral"].forEach(function (opt) {
        var o = document.createElement("option");
        o.value = opt;
        o.textContent = opt.charAt(0).toUpperCase() + opt.slice(1);
        if (opt === label) o.selected = true;
        select.appendChild(o);
      });
      select.addEventListener("change", function () {
        tr.dataset.label = select.value;
        select.className = "label-select " + select.value;
        editedRows[idx] = { sentence: sentence, label: select.value };
        var saveBtn = document.getElementById("saveCorrections");
        if (saveBtn) saveBtn.hidden = false;
        renderDistribution();
      });
      tdLabel.appendChild(select);

      tr.appendChild(tdSentence);
      tr.appendChild(tdLabel);
      resultsBody.appendChild(tr);
    });

    renderDistribution();

    var search = document.getElementById("resultSearch");
    var filter = document.getElementById("resultFilter");
    function applyFilters() {
      var q = (search && search.value || "").toLowerCase();
      var f = (filter && filter.value) || "all";
      resultsBody.querySelectorAll("tr").forEach(function (tr) {
        var matchesText = tr.children[0].textContent.toLowerCase().indexOf(q) !== -1;
        var matchesLabel = f === "all" || tr.dataset.label === f;
        tr.hidden = !(matchesText && matchesLabel);
      });
    }
    if (search) search.addEventListener("input", applyFilters);
    if (filter) filter.addEventListener("change", applyFilters);

    var saveBtn = document.getElementById("saveCorrections");
    if (saveBtn) {
      saveBtn.addEventListener("click", function () {
        var payload = Object.keys(editedRows).map(function (k) { return editedRows[k]; });
        fetch("/save-corrections", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ corrections: payload })
        })
          .then(function (res) {
            if (!res.ok) throw new Error("unavailable");
            saveBtn.textContent = "Saved";
            setTimeout(function () { saveBtn.hidden = true; saveBtn.textContent = "Save"; }, 1400);
          })
          .catch(function () {
            saveBtn.textContent = "Unavailable";
            setTimeout(function () { saveBtn.textContent = "Save"; }, 1400);
          });
      });
    }
  }

  function currentCounts() {
    var counts = { positive: 0, negative: 0, neutral: 0 };
    if (!resultsBody) return counts;
    resultsBody.querySelectorAll("tr").forEach(function (tr) {
      counts[tr.dataset.label] = (counts[tr.dataset.label] || 0) + 1;
    });
    return counts;
  }

  function segHtml(name, count, total) {
    if (!count) return "";
    var pct = (count / total * 100).toFixed(2);
    return '<div class="dist-seg-' + name + '" style="width:' + pct + '%"></div>';
  }

  /* ---------- right rail: distribution + funnel ---------- */
  function renderDistribution() {
    var counts = currentCounts();
    var total = counts.positive + counts.negative + counts.neutral;

    var bar = document.getElementById("distBar");
    if (bar) bar.innerHTML = total
      ? segHtml("positive", counts.positive, total) + segHtml("negative", counts.negative, total) + segHtml("neutral", counts.neutral, total)
      : "";

    var cntPos = document.getElementById("cntPositive");
    var cntNeg = document.getElementById("cntNegative");
    var cntNeu = document.getElementById("cntNeutral");
    if (cntPos) cntPos.textContent = counts.positive;
    if (cntNeg) cntNeg.textContent = counts.negative;
    if (cntNeu) cntNeu.textContent = counts.neutral;

    var funnelFill = document.getElementById("funnelClassified");
    var funnelCount = document.getElementById("funnelClassifiedCount");
    if (funnelCount) funnelCount.textContent = total;
    if (funnelFill) {
      var row = funnelFill.closest(".funnel-row");
      var keptRow = row ? row.previousElementSibling : null;
      var kept = keptRow ? parseInt(keptRow.querySelector("b").textContent, 10) : total;
      funnelFill.style.width = (kept ? (total / kept * 100) : 0) + "%";
    }
  }

  renderDistribution();
})();
