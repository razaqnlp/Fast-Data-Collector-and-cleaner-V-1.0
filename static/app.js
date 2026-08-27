(function () {
  "use strict";

  var openBtn = document.getElementById("openSettings");
  var closeBtn = document.getElementById("closeSettings");
  var panel = document.getElementById("settingsPanel");
  var scrim = document.getElementById("scrim");

  function openPanel() {
    panel.classList.add("is-open");
    scrim.classList.add("is-open");
    panel.setAttribute("aria-hidden", "false");
    openBtn.setAttribute("aria-expanded", "true");
  }
  function closePanel() {
    panel.classList.remove("is-open");
    scrim.classList.remove("is-open");
    panel.setAttribute("aria-hidden", "true");
    openBtn.setAttribute("aria-expanded", "false");
  }
  if (openBtn) openBtn.addEventListener("click", openPanel);
  var openSecondary = document.getElementById("openSettingsSecondary");
  if (openSecondary) openSecondary.addEventListener("click", openPanel);
  if (closeBtn) closeBtn.addEventListener("click", closePanel);
  if (scrim) scrim.addEventListener("click", closePanel);
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") closePanel();
  });

  var modeRadios = document.querySelectorAll('input[name="mode"]');
  var panelYoutube = document.getElementById("panel-youtube");
  var panelUpload = document.getElementById("panel-upload");
  function syncMode() {
    var checked = document.querySelector('input[name="mode"]:checked');
    var mode = checked ? checked.value : "youtube";
    if (panelYoutube) panelYoutube.hidden = mode !== "youtube";
    if (panelUpload) panelUpload.hidden = mode !== "upload";
  }
  modeRadios.forEach(function (radio) { radio.addEventListener("change", syncMode); });
  syncMode();

  var dropzone = document.getElementById("dropzone");
  var fileInput = document.getElementById("csv_file");
  var dzFilename = document.getElementById("dzFilename");
  function showFilename() {
    if (fileInput.files && fileInput.files.length) {
      dzFilename.textContent = fileInput.files[0].name;
    } else {
      dzFilename.textContent = "";
    }
  }
  if (dropzone && fileInput) {
    ["dragenter", "dragover"].forEach(function (eventName) {
      dropzone.addEventListener(eventName, function (event) {
        event.preventDefault();
        dropzone.classList.add("is-dragover");
      });
    });
    ["dragleave", "drop"].forEach(function (eventName) {
      dropzone.addEventListener(eventName, function (event) {
        event.preventDefault();
        dropzone.classList.remove("is-dragover");
      });
    });
    dropzone.addEventListener("drop", function (event) {
      if (event.dataTransfer.files.length) {
        fileInput.files = event.dataTransfer.files;
        showFilename();
      }
    });
    fileInput.addEventListener("change", showFilename);
  }

  document.querySelectorAll(".tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      var target = tab.getAttribute("data-tab");
      document.querySelectorAll(".tab").forEach(function (item) {
        item.classList.toggle("is-active", item === tab);
        item.setAttribute("aria-selected", item === tab ? "true" : "false");
      });
      document.querySelectorAll(".tab-panel").forEach(function (item) {
        item.hidden = item.getAttribute("data-panel") !== target;
      });
    });
  });

  document.querySelectorAll(".flash-close").forEach(function (button) {
    button.addEventListener("click", function () {
      var flash = button.closest(".flash");
      if (flash) flash.remove();
    });
  });

  var form = document.getElementById("mainForm");
  var submitBtn = document.getElementById("submitBtn");
  if (form && submitBtn) {
    form.addEventListener("submit", function () {
      submitBtn.disabled = true;
      submitBtn.querySelector(".btn-label").textContent = "Analyzing...";
    });
  }

  var csvTemplate = document.getElementById("resultCsvData");
  var resultsBody = document.getElementById("resultsBody");
  function parseCsvLine(line) {
    var result = [], current = "", inQuotes = false;
    for (var i = 0; i < line.length; i += 1) {
      var character = line[i];
      if (character === '"') inQuotes = !inQuotes;
      else if (character === "," && !inQuotes) { result.push(current); current = ""; }
      else current += character;
    }
    result.push(current);
    return result;
  }
  function sentimentClass(label) {
    var value = (label || "").trim().toLowerCase();
    if (value.indexOf("pos") === 0) return "pill-positive";
    if (value.indexOf("neg") === 0) return "pill-negative";
    return "pill-neutral";
  }
  if (csvTemplate && resultsBody) {
    var lines = csvTemplate.textContent.trim().split(/\r?\n/).filter(function (line) { return line.trim(); });
    var fragment = document.createDocumentFragment();
    lines.forEach(function (line) {
      var parts = parseCsvLine(line);
      if (parts.length < 2) return;
      var row = document.createElement("tr");
      var sentenceCell = document.createElement("td");
      sentenceCell.textContent = parts.slice(0, -1).join(",").trim();
      var sentimentCell = document.createElement("td");
      var pill = document.createElement("span");
      pill.className = "pill " + sentimentClass(parts[parts.length - 1]);
      pill.textContent = parts[parts.length - 1].trim();
      sentimentCell.appendChild(pill);
      row.appendChild(sentenceCell);
      row.appendChild(sentimentCell);
      fragment.appendChild(row);
    });
    resultsBody.appendChild(fragment);
  }
})();
