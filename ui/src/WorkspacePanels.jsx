import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Check, FileMusic, FolderOpen, Guitar, ImageIcon, Info, Plus, RotateCw, UploadCloud, XCircle } from "lucide-react";
import { api, QUEUE_RENDER_LIMIT, AUTO_SETTING, DEFAULT_DEMUCS_STEM_JOBS, DEFAULT_DEMUCS_STEMS, DEMUCS_STEM_OPTIONS, AUDIT_CRITERIA_OPTIONS } from "./settings.mjs";
import { parseAuthors, formatBytes, countToneDefinitions, countToneChanges, toneTimelineDuration, ReadyLine, StatusIcon, statusText, basename, duration, parentDir } from "./workspace-utils.jsx";
export function stemServerBadge(status, isStarting, matchesSelection = true) {
  if (status.healthy && matchesSelection) return "Running";
  if (status.healthy && !matchesSelection) return "Config changed";
  if (status.starting || status.processRunning || isStarting) return "Starting";
  if (status.running) return "Unhealthy";
  return "Stopped";
}

export function headerStemStatusClass(separateStems, status, isStarting, matchesSelection = true) {
  if (!separateStems && status.healthy) return "ready muted";
  if (!separateStems) return "off";
  if (status.healthy && matchesSelection) return "ready";
  if (status.healthy && !matchesSelection) return "changed";
  if (status.starting || status.processRunning || isStarting) return "starting";
  if (status.running || status.phase === "error") return "error";
  return "off";
}

export function headerStemStatusLabel(separateStems, status, isStarting, matchesSelection = true) {
  if (!separateStems && status.healthy) return "Ready, stems off";
  if (!separateStems) return "Stems off";
  if (status.healthy && matchesSelection) return "Ready";
  if (status.healthy && !matchesSelection) return "Config changed";
  if (status.starting || status.processRunning || isStarting) return "Starting";
  if (status.running || status.phase === "error") return "Needs attention";
  return "Not running";
}

export function stemServerTitle(status, busy, matchesSelection = true) {
  if (status.healthy && !matchesSelection) return "Selected stem setup is not active";
  if (status.healthy) return "Local stem server ready";
  if (status.phase === "downloading") return "Downloading runtime";
  if (status.phase === "installing") return "Installing runtime";
  if (status.phase === "loading") return "Loading Demucs";
  if (status.phase === "error") return "Stem server error";
  if (busy || status.starting) return "Installing or starting stem server";
  if (status.running) return "Stem server reachable, Demucs not ready";
  return "Local stem server not running";
}

export function stemServerActionText(status, busy, selectedModel = null) {
  if (!busy) {
    if (status.healthy) return selectedModel?.installed ? "Apply selected model" : "Download/start selected model";
    return status.running ? "Restart local stem server" : "Install/start local stem server";
  }
  if (status.phase === "downloading") return "Downloading...";
  if (status.phase === "installing") return "Installing...";
  if (status.phase === "loading") return "Loading model...";
  return "Starting...";
}

export function stemPhasePercent(status) {
  if (status.healthy || status.phase === "ready") return 100;
  if (status.phase === "loading") return 78;
  if (status.phase === "installing") return 50;
  if (status.phase === "downloading") return 30;
  if (status.phase === "starting") return 14;
  if (status.phase === "error") return 100;
  return 0;
}

export function stemPhaseLabel(status, busy) {
  if (status.healthy) return "Ready";
  if (status.phase === "error") return "Error";
  if (status.phase === "downloading") return "Downloading";
  if (status.phase === "installing") return "Installing";
  if (status.phase === "loading") return "Loading";
  if (busy || status.starting) return "Starting";
  return "Idle";
}

export function StemSetupProgress({ status, busy, debugLogInfo }) {
  const percent = stemPhasePercent(status);
  const latestLog = (status.log || []).slice(-8);
  return (
    <div className={`stem-progress ${status.phase === "error" ? "error" : status.healthy ? "ready" : busy ? "active" : ""}`}>
      <div className="stem-progress-head">
        <div>
          <strong>{stemPhaseLabel(status, busy)}</strong>
          <span>{stemServerDetail(status)}</span>
        </div>
        <div className="stem-progress-actions">
          <button className="ghost" onClick={() => api.openDebugLog()} disabled={!debugLogInfo?.path}>Open log</button>
          <button className="ghost" onClick={() => api.openDebugLogFolder()} disabled={!debugLogInfo?.folder}>Open folder</button>
        </div>
      </div>
      <div className="progress-track" aria-hidden="true">
        <span style={{ width: `${percent}%` }} />
      </div>
      <div className="stem-progress-log">
        {latestLog.length ? latestLog.map((line, index) => <code key={`${line}-${index}`}>{line}</code>) : <span>Waiting for setup output...</span>}
      </div>
    </div>
  );
}

export function stemServerDetail(status, demucsModel, selectedModel, matchesSelection = true) {
  if (selectedModel?.remoteOnly) {
    return `${selectedModel.name} is requested during conversion through the configured remote Demucs server. The local FeedForge server cannot start this model.`;
  }
  if (status?.portBlocked) {
    const owners = stemServerPortOwners(status);
    const ownerText = owners.length
      ? ` Used by ${owners.map((owner) => `${owner.processName || "process"} ${owner.pid || ""}`.trim()).join(", ")}.`
      : "";
    return `Port 7865 is already in use.${ownerText} Free the port, then start the local server.`;
  }
  if (status.healthy && !matchesSelection) {
    const selected = selectedModel?.name || demucsModel;
    return `Current server is ${status.model || "another model"}. Start the selected setup to use ${selected}.`;
  }
  if (status.healthy) {
    const storage = status.storageDir ? ` Storage: ${status.storageDir}` : "";
    return `${status.url} - ${status.model || demucsModel} on ${resolvedDeviceLabel(status)} is ready for conversions.${storage}`;
  }
  if (status.message) return status.message;
  if (status.running) return "The port is reachable, but health did not pass. Open the debug log if this stays unresolved.";
  if (selectedModel?.installed) return "Installed locally.";
  return "First local start installs dependencies and downloads the selected model.";
}

export function stemServerPortOwners(status) {
  return Array.isArray(status?.portOwners) ? status.portOwners.filter((owner) => owner?.pid) : [];
}

export function stemServerMatchesSelection(status, model, device, jobs) {
  if (!status?.healthy) return false;
  const modelMatches = !status.model || status.model === model;
  const requestedDevice = String(status.requestedDevice || status.device || "").toLowerCase();
  const selectedDevice = String(device || "auto").toLowerCase();
  const runningDevice = String(status.device || "").toLowerCase();
  const deviceMatches =
    !requestedDevice ||
    requestedDevice === selectedDevice ||
    (selectedDevice === "auto" && (requestedDevice === "auto" || runningDevice.startsWith("cuda"))) ||
    (selectedDevice === "cuda" && runningDevice.startsWith("cuda"));
  const jobMatches = !status.concurrency || Number(status.concurrency) === Number(jobs || 1);
  return modelMatches && deviceMatches && jobMatches;
}

export function normalizeStemSelection(value) {
  const allowed = new Set(DEMUCS_STEM_OPTIONS.map((stem) => stem.id));
  const selected = Array.isArray(value) ? value : DEFAULT_DEMUCS_STEMS;
  const normalized = [];
  for (const stem of selected) {
    const id = String(stem || "").trim().toLowerCase();
    if (allowed.has(id) && !normalized.includes(id)) normalized.push(id);
  }
  return normalized.length ? normalized : DEFAULT_DEMUCS_STEMS;
}

export function toggleStemSelection(current, stemId) {
  const selected = normalizeStemSelection(current);
  if (selected.includes(stemId)) {
    const next = selected.filter((stem) => stem !== stemId);
    return next.length ? next : selected;
  }
  return normalizeStemSelection([...selected, stemId]);
}

export function stemSelectionSummary(stems) {
  const selected = normalizeStemSelection(stems);
  if (selected.length === DEMUCS_STEM_OPTIONS.length) return "All supported stems will be requested. Full mix is always included.";
  const labels = selected
    .map((id) => DEMUCS_STEM_OPTIONS.find((stem) => stem.id === id)?.label || id)
    .join(", ");
  return `${labels} will be requested. Full mix is always included.`;
}

export function stemSelectionWarning(stems) {
  const selected = normalizeStemSelection(stems);
  if (selected.length >= DEMUCS_STEM_OPTIONS.length) return "";
  return "For full mixer control in FeedBack, include every stem you want to hear separately. Full mix is kept for fallback, not as a backing track.";
}

export function StemSetupChecklist({ pythonInfo, setup, selectedModel, status, matchesSelection }) {
  const rows = [
    {
      label: "Python",
      state: pythonInfo?.ok ? "ready" : pythonInfo?.found === false ? "missing" : "pending",
      text: pythonInfo?.ok ? `Ready ${pythonInfo.version || ""}` : "Python 3.11+ required"
    },
    {
      label: "Local environment",
      state: setup?.environmentInstalled ? "ready" : "missing",
      text: setup?.environmentInstalled ? "Created" : "Created on first start"
    },
    {
      label: "Dependencies",
      state: setup?.dependenciesInstalled ? "ready" : "missing",
      text: setup?.dependenciesInstalled ? "Installed" : "Installed on first start"
    },
    {
      label: "Selected model",
      state: selectedModel?.installed ? "ready" : selectedModel?.partial ? "pending" : "missing",
      text: selectedModel?.installed ? "Downloaded" : selectedModel?.partial ? "Partially downloaded" : "Download needed"
    },
    {
      label: "Active server",
      state: status?.healthy && matchesSelection ? "ready" : status?.healthy ? "pending" : "missing",
      text: status?.healthy && matchesSelection ? "Matches selection" : status?.healthy ? `Running ${status.model || "another model"}` : "Not running"
    }
  ];
  return (
    <div className="setup-checklist">
      {rows.map((row) => (
        <div key={row.label} className={`setup-check ${row.state}`}>
          <span>{row.label}</span>
          <strong>{row.text}</strong>
        </div>
      ))}
    </div>
  );
}

export function pythonPrereqTitle(info, checking) {
  if (checking) return "Checking Python";
  if (info?.ok) return `Python ${info.version} ready`;
  if (info?.found) return "Python version unsupported";
  if (info?.found === false) return "Python not found";
  return "Python requirement";
}

export function Metric({ label, value, tone = "" }) {
  return (
    <div className={`metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function LibraryAuditPanel({ folder, criteria, report, busy, onChooseFolder, onRun, onChangeCriterion }) {
  const [selectedDuplicatePaths, setSelectedDuplicatePaths] = useState([]);
  const [deleteMessage, setDeleteMessage] = useState("");
  const [isDeletingDuplicates, setIsDeletingDuplicates] = useState(false);
  const failedRows = (report?.rows || []).filter((row) => row.status !== "pass");
  const previewRows = failedRows.slice(0, 8);
  const duplicateGroups = report?.duplicates || [];
  const selectedSet = new Set(selectedDuplicatePaths);

  useEffect(() => {
    setSelectedDuplicatePaths([]);
    setDeleteMessage("");
  }, [report?.jsonPath]);

  function toggleDuplicatePath(filePath, checked) {
    setSelectedDuplicatePaths((current) => {
      const next = new Set(current);
      if (checked) next.add(filePath);
      else next.delete(filePath);
      return [...next];
    });
  }

  async function deleteSelectedDuplicates() {
    if (!selectedDuplicatePaths.length || isDeletingDuplicates) return;
    const ok = window.confirm(`Move ${selectedDuplicatePaths.length} selected FeedPak file${selectedDuplicatePaths.length === 1 ? "" : "s"} to the Recycle Bin?`);
    if (!ok) return;
    setIsDeletingDuplicates(true);
    setDeleteMessage("");
    try {
      const result = await api.deleteFiles(selectedDuplicatePaths);
      setDeleteMessage(result.ok ? `Moved ${result.deleted || 0} file${result.deleted === 1 ? "" : "s"} to the Recycle Bin.` : result.error || "Some files could not be deleted.");
      if (result.ok) setSelectedDuplicatePaths([]);
    } catch (error) {
      setDeleteMessage(error?.message || "Delete failed.");
    } finally {
      setIsDeletingDuplicates(false);
    }
  }

  return (
    <div className="diagnostics-panel audit-panel">
      <div className="diagnostics-head">
        <div>
          <strong>Library audit</strong>
          <span>{folder || "Choose a folder of FeedPak files to scan recursively."}</span>
        </div>
        <div>
          <button className="ghost" onClick={onChooseFolder} disabled={busy}><FolderOpen size={16} /> Folder</button>
          <button onClick={onRun} disabled={busy || !folder}>
            {busy ? <RotateCw className="spin" size={16} /> : <Check size={16} />}
            {busy ? "Scanning" : "Run audit"}
          </button>
        </div>
      </div>

      <div className="audit-body">
        <div className="audit-criteria">
          {AUDIT_CRITERIA_OPTIONS.map((option) => (
            <label key={option.key} className={`audit-criterion ${criteria[option.key] ? "active" : ""}`}>
              <input
                type="checkbox"
                checked={!!criteria[option.key]}
                onChange={(event) => onChangeCriterion(option.key, event.target.checked)}
                disabled={busy}
              />
              <span>{option.label}</span>
            </label>
          ))}
        </div>

        {report?.ok === false && <div className="error-box"><AlertTriangle size={17} /> {report.error || "Library audit failed."}</div>}

        {report?.ok && (
          <>
            <div className="audit-summary">
              <Metric label="FeedPaks scanned" value={report.total || 0} />
              <Metric label="Passed" value={report.passed || 0} />
              <Metric label="Needs work" value={report.needsWork || 0} />
              <Metric label="Duplicate groups" value={report.duplicateGroups || 0} tone={report.duplicateGroups ? "warn" : ""} />
            </div>
            <div className="audit-actions">
              <span>{report.csvPath ? `Report saved: ${basename(report.csvPath)}` : "Report saved after scan."}</span>
              <div>
                <button className="ghost" onClick={() => api.openAuditReport(report.csvPath)} disabled={!report.csvPath}>Open CSV</button>
                <button className="ghost" onClick={() => api.openAuditReport(report.jsonPath)} disabled={!report.jsonPath}>Open JSON</button>
              </div>
            </div>
            <div className="audit-results">
              {failedRows.length === 0 ? (
                <div className="empty compact">No missing items found for the selected criteria.</div>
              ) : (
                previewRows.map((row) => (
                  <div className="audit-row" key={row.filePath}>
                    <div>
                      <strong>{row.title || basename(row.filePath)}</strong>
                      <span>{row.artist || "Unknown Artist"} / {row.relativePath}</span>
                    </div>
                    <div className="audit-missing">
                      {(row.missing || []).map((issue) => <b key={issue}>{issue}</b>)}
                    </div>
                  </div>
                ))
              )}
              {failedRows.length > previewRows.length && <span className="muted-text">Showing first {previewRows.length} of {failedRows.length}. Open the CSV for the full report.</span>}
            </div>
            {criteria.checkDuplicates && (
              <div className="duplicate-results">
                <div className="duplicate-head">
                  <div>
                    <strong>Duplicate songs</strong>
                    <span>{duplicateGroups.length ? `${duplicateGroups.length} group${duplicateGroups.length === 1 ? "" : "s"} found. FeedForge recommends one file per group, but you decide what to keep.` : "No duplicates found by metadata."}</span>
                  </div>
                  <button className="danger" onClick={deleteSelectedDuplicates} disabled={!selectedDuplicatePaths.length || isDeletingDuplicates}>
                    {isDeletingDuplicates ? <RotateCw className="spin" size={16} /> : <XCircle size={16} />}
                    Move selected to Recycle Bin
                  </button>
                </div>
                {deleteMessage && <div className="info-box"><Info size={16} /> {deleteMessage}</div>}
                {duplicateGroups.map((group) => (
                  <div className="duplicate-group" key={group.key}>
                    <div className="duplicate-title">
                      <strong>{group.artist || "Unknown Artist"} - {group.title || "Untitled"}</strong>
                      <span>{group.album || "No album"} {group.year ? ` / ${group.year}` : ""}</span>
                    </div>
                    <div className="duplicate-files">
                      {group.files.map((file) => (
                        <label className={`duplicate-file ${file.recommended ? "recommended" : ""}`} key={file.filePath}>
                          <input
                            type="checkbox"
                            checked={selectedSet.has(file.filePath)}
                            onChange={(event) => toggleDuplicatePath(file.filePath, event.target.checked)}
                            disabled={file.recommended}
                          />
                          <div>
                            <strong>{basename(file.filePath)} {file.recommended && <b>Recommended keep</b>}</strong>
                            <span>{file.relativePath}</span>
                          </div>
                          <div className="duplicate-stats">
                            <span>{file.arrangements || 0} arrangements</span>
                            <span>{file.stems || 0} stems</span>
                            <span>{formatBytes(file.size || 0)}</span>
                          </div>
                          <button type="button" className="ghost" onClick={(event) => { event.preventDefault(); api.showFileInFolder(file.filePath); }}>
                            <FolderOpen size={15} /> Folder
                          </button>
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export function ConversionProgress({ progress, isConverting }) {
  const total = Math.max(0, progress.total || 0);
  const completed = Math.min(total, Math.max(0, progress.completed || 0));
  const failed = Math.max(0, progress.failed || 0);
  const remaining = Math.max(0, total - completed);
  const percent = total ? Math.round((completed / total) * 100) : 0;
  const isPlanning = isConverting && progress.phase === "planning";
  const status = progress.stopped
    ? "Stopped"
    : isConverting
      ? isPlanning
        ? progress.planningStage === "reserving" ? "Finalizing collision-safe names" : "Reading PSARC metadata"
        : "Converting"
      : completed >= total
        ? "Complete"
        : "Waiting";

  return (
    <section className={`conversion-progress ${isConverting ? "active" : progress.stopped ? "stopped" : "complete"}`}>
      <div className="conversion-progress-head">
        <div>
          <strong>{status}</strong>
          <span>
            {completed} of {total} {isPlanning ? "checked" : "processed"}
            {remaining ? `, ${remaining} remaining` : ""}
            {failed ? `, ${failed} failed` : ""}
            {isPlanning && progress.planningCached ? `, ${progress.planningCached} cached` : ""}
            {isPlanning && progress.planningWorkers ? `, ${progress.planningWorkers} workers` : ""}
          </span>
        </div>
        <b>{percent}%</b>
      </div>
      <div className="progress-track conversion-progress-track" aria-label={`Conversion progress ${percent}%`}>
        <span style={{ width: `${Math.max(2, percent)}%` }} />
      </div>
      {progress.active?.length > 0 && (
        <div className="active-conversions">
          {progress.active.map((item) => (
            <div className="active-conversion-row" key={item.id}>
              <RotateCw className="spin" size={15} />
              <div>
                <strong>{item.name}</strong>
                {item.artist && <span>{item.artist}</span>}
              </div>
              <div className="active-file-track" aria-hidden="true">
                <span />
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export function FilterSelect({ label, value, onChange, options }) {
  return (
    <label className="filter-select">
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value)} disabled={!options.length}>
        <option value="all">All</option>
        {options.map((option) => <option key={option} value={option}>{option}</option>)}
      </select>
    </label>
  );
}

export function selectedDemucsModel(models, modelId) {
  return (models || []).find((model) => model.id === modelId) || null;
}

export function defaultDemucsDevices() {
  return [
    {
      id: "auto",
      name: "Auto",
      detail: "Installs and uses CUDA PyTorch when an NVIDIA GPU is detected, otherwise CPU.",
      available: true,
      recommended: true
    },
    {
      id: "cpu",
      name: "CPU",
      detail: "Compatible with every PC, but slow for stem splitting.",
      available: true
    }
  ];
}

export function selectedDemucsDevice(devices, deviceId) {
  return (devices || []).find((device) => device.id === deviceId) || defaultDemucsDevices()[0];
}

export function normalizeAutoNumberSetting(value, fallback = AUTO_SETTING) {
  if (value === AUTO_SETTING || value === undefined || value === null || value === "") {
    return fallback;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(1, Math.floor(parsed));
}

export function normalizeInitialStemJobs(settings) {
  const normalized = normalizeAutoNumberSetting(settings?.demucsStemJobs, DEFAULT_DEMUCS_STEM_JOBS);
  if ((settings?.performanceSettingsVersion || 0) < 2 && normalized === 1) {
    return AUTO_SETTING;
  }
  return normalized;
}

export function hostCpuCount() {
  return Math.max(2, Number(window.navigator?.hardwareConcurrency) || 4);
}

export function resolveConversionWorkerCount(setting, options = {}) {
  const manual = normalizeAutoNumberSetting(setting, AUTO_SETTING);
  if (manual !== AUTO_SETTING) return Math.max(1, Math.min(Number(manual), 8));

  const cores = hostCpuCount();
  const base = cores >= 16 ? 6 : cores >= 10 ? 5 : cores >= 6 ? 4 : 2;
  if (!options.separateStems) return base;

  const stemJobs = Math.max(1, Number(options.stemJobs || 1));
  return Math.max(2, Math.min(base, stemJobs + 1, 4));
}

export function resolveStemJobCount(setting, deviceId, devices) {
  const manual = normalizeAutoNumberSetting(setting, AUTO_SETTING);
  if (manual !== AUTO_SETTING) return Math.max(1, Math.min(Number(manual), 4));

  const device = autoResolvedStemDevice(deviceId, devices);
  const id = String(device?.id || deviceId || "").toLowerCase();
  const memoryGb = deviceMemoryGb(device);
  if (id === "cpu" || device?.kind === "cpu") return 1;
  if ((device?.kind === "cuda" || id.startsWith("cuda")) && memoryGb >= 16) return 2;
  return 1;
}

export function autoResolvedStemDevice(deviceId, devices) {
  const list = Array.isArray(devices) ? devices : [];
  if (deviceId && deviceId !== AUTO_SETTING) {
    return selectedDemucsDevice(list, deviceId);
  }
  return list.find((device) => device.kind === "cuda" && device.recommended)
    || list.find((device) => String(device.id || "").startsWith("cuda"))
    || selectedDemucsDevice(list, AUTO_SETTING);
}

export function deviceMemoryGb(device) {
  const direct = Number(device?.memory_gb);
  if (Number.isFinite(direct) && direct > 0) return direct;
  const detailMatch = String(device?.detail || "").match(/([\d.]+)\s*GB/i);
  return detailMatch ? Number(detailMatch[1]) || 0 : 0;
}

export function mergeDemucsDevices(current, accelerators) {
  const byId = new Map();
  for (const device of [...defaultDemucsDevices(), ...(current || [])]) {
    if (device?.id) byId.set(device.id, device);
  }
  for (const device of accelerators || []) {
    if (!device?.id) continue;
    const detail = device.kind === "cuda"
      ? `CUDA GPU, ${device.memory_gb || "unknown"} GB VRAM.`
      : device.detail || "Detected by the running stem server.";
    byId.set(device.id, {
      ...device,
      detail,
      recommended: device.kind === "cuda" && device.id === "cuda:0"
    });
  }
  return Array.from(byId.values());
}

export function deviceLabel(device) {
  const suffix = device.recommended ? " - recommended" : "";
  const disabled = device.available === false ? " - unavailable" : "";
  return `${device.name || device.id}${device.id && device.name !== device.id ? ` (${device.id})` : ""}${suffix}${disabled}`;
}

export function deviceHelpText(device, status) {
  if (status?.healthy) {
    return `The running server reports ${resolvedDeviceLabel(status)}. GPU acceleration depends on the PyTorch build installed in the selected Demucs folder.`;
  }
  if (!device) return "Auto mode will use CUDA when available, otherwise CPU.";
  if (device.id === "auto") return device.detail || "Auto mode will install and use CUDA PyTorch when an NVIDIA GPU is detected, otherwise CPU.";
  if (device.kind === "cuda" || String(device.id || "").startsWith("cuda")) {
    return device.detail || "Uses GPU acceleration when the local PyTorch runtime supports it.";
  }
  if (device.id === "cpu") return device.detail || "Reliable, but slower than GPU.";
  return device.detail || "Reported by the local stem environment.";
}

export function stemJobHelpText(value, status) {
  const active = Number(status?.concurrency || value || 1);
  if (active <= 1) {
    return "Safest. One stem split at a time.";
  }
  if (active === 2) {
    return "Faster on strong GPUs, higher VRAM use.";
  }
  return "High VRAM use. May be slower or fail on smaller GPUs.";
}

export function stemJobSelectionLabel(setting, effectiveJobs) {
  const jobs = Number(effectiveJobs || 1);
  if (setting === AUTO_SETTING) {
    return `Auto selected ${jobs} stem job${jobs === 1 ? "" : "s"}`;
  }
  return `Selected: ${jobs} stem job${jobs === 1 ? "" : "s"}`;
}

export function resolvedDeviceLabel(status) {
  const id = status?.device || "";
  const match = (status?.accelerators || []).find((device) => device.id === id);
  if (!match) return id || "an unknown device";
  const memory = match.memory_gb ? `, ${match.memory_gb} GB VRAM` : "";
  return `${match.name || id} (${id}${memory})`;
}

export function modelStatusLabel(model) {
  if (!model) return "Unknown";
  if (model.remoteOnly) return "Remote only";
  if (model.installed) return "Installed";
  if (model.partial) return `Partial ${model.installedCount || 0}/${model.requiredCount || 0}`;
  return "Download needed";
}

export function DropZone({ onClick }) {
  return (
    <button className="drop-zone" onClick={onClick}>
      <UploadCloud size={30} />
      <strong>Drop PSARC or FeedPak files here</strong>
      <span>Or use Add files.</span>
    </button>
  );
}

export function isMultiSongPackage(item) {
  return item?.sourceType !== "feedpak"
    && Boolean(item?.preview?.is_multi_song || Number(item?.preview?.song_count) > 1);
}

export function firstSongLabel(preview) {
  const title = String(preview?.title || "").trim();
  const artist = String(preview?.artist || "").trim();
  if (title && artist) return `${title} — ${artist}`;
  return title || artist;
}

export function itemDisplayTitle(item) {
  return isMultiSongPackage(item)
    ? item?.name || item?.preview?.title || "Unknown archive"
    : item?.preview?.title || item?.name || "Unknown file";
}

export function itemDisplaySubtitle(item) {
  if (!isMultiSongPackage(item)) return item?.preview?.artist || item?.path || "";
  const count = Number(item?.preview?.song_count) || 0;
  const previewLabel = firstSongLabel(item?.preview);
  const archiveLabel = count ? `${count} songs` : "Multi-song archive";
  return previewLabel ? `${archiveLabel} • First song: ${previewLabel}` : archiveLabel;
}

export function itemProgressSubtitle(item) {
  const count = Number(item?.preview?.song_count) || 0;
  if (!isMultiSongPackage(item) && count <= 1) return item?.preview?.artist || "";
  return count ? `${count} songs` : "Multi-song archive";
}

export function Queue({ items, selectedId, onSelect, onRemove, onExportAudio, onExportAudioItem, canRemove, canExportAudio }) {
  const visibleItems = items.slice(0, QUEUE_RENDER_LIMIT);
  const hiddenCount = Math.max(0, items.length - visibleItems.length);
  return (
    <section className="panel queue-panel">
      <div className="panel-title">
        <h2>Import queue</h2>
        <div className="panel-title-actions">
          <span>{items.length} file{items.length === 1 ? "" : "s"}</span>
          <button className="compact-action" onClick={onExportAudio} disabled={!canExportAudio}>
            <FileMusic size={16} />
            Export audio
          </button>
        </div>
      </div>
      <div className="queue">
        {items.length === 0 && <div className="empty">No song packages imported yet.</div>}
        {visibleItems.map((item) => (
          <button
            key={item.id}
            className={`queue-row ${selectedId === item.id ? "selected" : ""}`}
            onClick={() => onSelect(item.id)}
          >
            <StatusIcon status={item.status} />
            <div className="queue-main">
              <strong>{itemDisplayTitle(item)}</strong>
              <span>{itemDisplaySubtitle(item)}</span>
              {item.preview?.is_multi_song && item.status !== "converted" && (
                <em>{item.preview.song_count} songs will export as separate FeedPaks</em>
              )}
              {item.message && <em>{item.message}</em>}
            </div>
            <div className="queue-meta">
              <span>{item.sourceType === "feedpak" ? "FeedPak" : "PSARC"}</span>
              <span>{item.preview ? duration(item.preview.duration) : "-"}</span>
              <b>{statusText(item.status)}</b>
            </div>
            {item.status !== "converting" && (
              <span
                className="queue-export"
                role="button"
                tabIndex={0}
                title="Export audio for this file"
                onClick={(event) => {
                  event.stopPropagation();
                  onExportAudioItem(item);
                }}
                onKeyDown={(event) => {
                  if (event.key !== "Enter" && event.key !== " ") return;
                  event.preventDefault();
                  event.stopPropagation();
                  onExportAudioItem(item);
                }}
              >
                <FileMusic size={17} />
              </span>
            )}
            {canRemove && item.status !== "converting" && (
              <span
                className="queue-remove"
                role="button"
                tabIndex={0}
                title="Remove from queue"
                onClick={(event) => {
                  event.stopPropagation();
                  onRemove(item.id);
                }}
                onKeyDown={(event) => {
                  if (event.key !== "Enter" && event.key !== " ") return;
                  event.preventDefault();
                  event.stopPropagation();
                  onRemove(item.id);
                }}
              >
                <XCircle size={17} />
              </span>
            )}
          </button>
        ))}
        {hiddenCount > 0 && <div className="queue-limit">Showing first {QUEUE_RENDER_LIMIT} matches. Use search or filters to narrow {hiddenCount} more.</div>}
      </div>
    </section>
  );
}

export function FeedPakTools({
  item,
  feedpakItems,
  selectedId,
  onSelect,
  onAddFiles,
  onSaveFeedpakMetadata,
  onReplaceFeedpakCover,
  onRemoveFeedpakCover,
  onReplaceFeedpakStem,
  onRemoveFeedpakStem,
  onReprocessFeedpakStems,
  onBatchReprocessFeedpakStems,
  onOrganizeByArtist,
  onChooseOutput,
  onRemoveItem,
  outputDir,
  overwrite,
  separateStems,
  demucsStems
}) {
  const [organizeMessage, setOrganizeMessage] = useState("");
  const [batchStemMessage, setBatchStemMessage] = useState("");

  async function organizeByArtist() {
    setOrganizeMessage("Organizing...");
    const result = await onOrganizeByArtist();
    if (result?.cancelled) {
      setOrganizeMessage("");
      return;
    }
    setOrganizeMessage(result?.ok
      ? `Copied ${result.copied || 0} FeedPak${result.copied === 1 ? "" : "s"}`
      : result?.error || "Organize failed");
  }

  async function batchReprocessStems() {
    setBatchStemMessage("Reprocessing...");
    const result = await onBatchReprocessFeedpakStems();
    setBatchStemMessage(result?.ok
      ? `Reprocessed ${result.total || 0} FeedPak${result.total === 1 ? "" : "s"}`
      : result?.error || `Reprocessed with ${result?.failed || 0} failure${result?.failed === 1 ? "" : "s"}`);
  }

  return (
    <section className="feedpak-tools-page">
      <div className="tools-head">
        <div className="feedpak-command-copy">
          <strong>{feedpakItems.length ? `${feedpakItems.length} package${feedpakItems.length === 1 ? "" : "s"} loaded` : "No package loaded"}</strong>
          <span>{outputDir ? `Output: ${outputDir}` : "Choose an output folder for organized copies."}</span>
        </div>
        <div className="tools-actions">
          <button onClick={onAddFiles}><Plus size={17} /> Add FeedPaks</button>
          <button className="ghost" onClick={onChooseOutput}><FolderOpen size={17} /> Output</button>
          <button onClick={organizeByArtist} disabled={!feedpakItems.length}>
            <FolderOpen size={17} /> Artist folders
          </button>
          <button onClick={batchReprocessStems} disabled={!feedpakItems.length || !separateStems}>
            <RotateCw size={17} /> Reprocess all
          </button>
        </div>
      </div>
      <div className="feedpak-organize-note">
        <span>{batchStemMessage || organizeMessage || "Artist folders keep original filenames."}</span>
        <b>{overwrite ? "Overwrite on" : "Overwrite off"}</b>
      </div>

      {feedpakItems.length > 0 && (
        <div className="feedpak-picker">
          <span>Loaded</span>
          <div className="feedpak-strip" aria-label="Imported FeedPaks">
            {feedpakItems.map((entry) => (
              <div
                key={entry.id}
                className={`feedpak-chip ${selectedId === entry.id ? "active" : ""}`}
                title={entry.path}
              >
                <button className="feedpak-chip-main" onClick={() => onSelect(entry.id)}>
                  <strong>{entry.preview?.title || entry.name}</strong>
                  <span>{entry.preview?.artist || "Unknown artist"}</span>
                </button>
                <button
                  className="feedpak-chip-remove"
                  onClick={() => onRemoveItem(entry.id)}
                  title={`Close ${entry.preview?.title || entry.name}`}
                  aria-label={`Close ${entry.preview?.title || entry.name}`}
                >
                  <XCircle size={15} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {!item ? (
        <div className="tools-empty">
          <FileMusic size={38} />
          <strong>No FeedPak selected</strong>
          <span>Add or select a FeedPak package to inspect and edit it.</span>
          <button className="primary" onClick={onAddFiles}><Plus size={17} /> Add FeedPaks</button>
        </div>
      ) : (
        <div className="feedpak-tools-grid">
          <Inspector
            item={item}
            onSaveFeedpakMetadata={onSaveFeedpakMetadata}
            onReplaceFeedpakCover={onReplaceFeedpakCover}
            onRemoveFeedpakCover={onRemoveFeedpakCover}
            onReplaceFeedpakStem={onReplaceFeedpakStem}
            onRemoveFeedpakStem={onRemoveFeedpakStem}
            onReprocessFeedpakStems={onReprocessFeedpakStems}
            separateStems={separateStems}
            demucsStems={demucsStems}
          />
        </div>
      )}
    </section>
  );
}

export function FeedPakMetric({ label, value }) {
  return (
    <div className="metric-card">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

export function Inspector({
  item,
  onSaveFeedpakMetadata,
  onReplaceFeedpakCover,
  onRemoveFeedpakCover,
  onReplaceFeedpakStem,
  onRemoveFeedpakStem,
  onReprocessFeedpakStems,
  separateStems = false,
  demucsStems = []
}) {
  const [tab, setTab] = useState("overview");
  useEffect(() => setTab("overview"), [item?.id]);
  const [editMetadata, setEditMetadata] = useState(null);
  const [authorsText, setAuthorsText] = useState("");
  const [saveMessage, setSaveMessage] = useState("");
  const [stemMessage, setStemMessage] = useState("");
  const [stemEditId, setStemEditId] = useState("guitar");
  const [overwriteOriginal, setOverwriteOriginal] = useState(false);
  const preview = item?.preview;
  const cover = preview?.cover_path ? `file:///${preview.cover_path.replaceAll("\\", "/")}` : null;
  const arrangements = preview?.arrangements || [];
  const tones = preview?.tones || [];
  const authors = preview?.authors || [];
  const stems = preview?.stems || [];
  const validation = item?.validation || preview?.validation;
  const itemWarnings = Array.isArray(item?.warnings)
    ? item.warnings.filter(Boolean)
    : Array.isArray(preview?.warnings) ? preview.warnings.filter(Boolean) : [];
  const isFeedpak = item?.sourceType === "feedpak" || preview?.source_type === "feedpak";
  const isMultiSong = !isFeedpak && isMultiSongPackage(item);
  const outputCount = Array.isArray(item?.outputPaths) ? item.outputPaths.length : 0;

  useEffect(() => {
    if (!preview || !isFeedpak) {
      setEditMetadata(null);
      setAuthorsText("");
      setSaveMessage("");
      setStemMessage("");
      setStemEditId("guitar");
      setOverwriteOriginal(false);
      return;
    }
    setEditMetadata({
      title: preview.title || "",
      artist: preview.artist || "",
      album: preview.album || "",
      year: preview.year || "",
      language: preview.language || ""
    });
    setAuthorsText((preview.authors || []).map((author) => `${author.name}${author.role ? ` | ${author.role}` : ""}`).join("\n"));
    setSaveMessage("");
    setStemMessage("");
    setStemEditId("guitar");
    setOverwriteOriginal(false);
  }, [item?.id, preview?.title, preview?.artist, isFeedpak]);

  async function saveFeedpak() {
    if (!editMetadata) return;
    setSaveMessage("Saving...");
    const result = await onSaveFeedpakMetadata(item, editMetadata, parseAuthors(authorsText), { overwriteOriginal });
    setSaveMessage(result.ok
      ? overwriteOriginal ? "Saved original" : `Saved copy: ${basename(result.outputPath || "")}`
      : result.error || "Save failed");
  }

  async function replaceStem(stemId) {
    setStemMessage(`Choosing audio for ${stemId}...`);
    const result = await onReplaceFeedpakStem(item, stemId, { overwriteOriginal });
    if (result?.cancelled) {
      setStemMessage("");
      return;
    }
    setStemMessage(result?.ok
      ? overwriteOriginal ? `Replaced ${stemId}` : `Saved copy with ${stemId}`
      : result?.error || "Stem update failed");
  }

  async function addStem() {
    const stemId = stemEditId.trim();
    if (!stemId) {
      setStemMessage("Enter a stem name first.");
      return;
    }
    await replaceStem(stemId);
  }

  async function removeStem(stemId) {
    setStemMessage(`Removing ${stemId}...`);
    const result = await onRemoveFeedpakStem(item, stemId, { overwriteOriginal });
    setStemMessage(result?.ok
      ? overwriteOriginal ? `Removed ${stemId}` : `Saved copy without ${stemId}`
      : result?.error || "Stem removal failed");
  }

  async function reprocessStems() {
    if (!separateStems) {
      setStemMessage("Enable Separate stems in Settings first.");
      return;
    }
    setStemMessage("Reprocessing stems...");
    const result = await onReprocessFeedpakStems(item, { overwriteOriginal });
    setStemMessage(result?.ok
      ? overwriteOriginal ? "Reprocessed original stems" : `Saved reprocessed copy: ${basename(result.outputPath || "")}`
      : result?.error || "Stem reprocess failed");
  }

  if (!item) return (
    <aside className="inspector inspector-empty">
      <FileMusic size={26} />
      <h2>No file selected</h2>
      <p>Select a file from the queue.</p>
    </aside>
  );

  return (
    <aside className={isFeedpak ? "inspector feedpak-inspector" : "inspector convert-inspector"}>
      <div className="inspector-rail">
        <section className="song-hero">
          <div className="cover">{cover ? <img src={cover} alt="" /> : <ImageIcon size={44} />}</div>
          <div className="song-copy">
            <span className="eyebrow">{isFeedpak ? "FeedPak package" : isMultiSong ? "Selected archive" : "Selected song"}</span>
            <h2>{itemDisplayTitle(item) || "No song selected"}</h2>
            <p>{isMultiSong
              ? firstSongLabel(preview) ? `First song preview: ${firstSongLabel(preview)}` : "Multi-song PSARC archive"
              : preview?.artist || "Add PSARC or FeedPak files to inspect package details."}</p>
            <div className="chips">
              {!isMultiSong && preview?.album && <span>{preview.album}</span>}
              {!isMultiSong && preview?.year && <span>{preview.year}</span>}
              {!isMultiSong && preview?.duration && <span>{duration(preview.duration)}</span>}
              {isMultiSong && <span>{preview.song_count} songs</span>}
              {authors.length > 0 && <span>{authors.length} credit{authors.length === 1 ? "" : "s"}</span>}
            </div>
          </div>
        </section>

        <div className="inspector-tabs">
          <button className={tab === "overview" ? "active" : ""} onClick={() => setTab("overview")}>Overview</button>
          {isFeedpak && <button className={tab === "metadata" ? "active" : ""} onClick={() => setTab("metadata")}>Metadata</button>}
          {isFeedpak && <button className={tab === "stems" ? "active" : ""} onClick={() => setTab("stems")}>Stems</button>}
          {countToneDefinitions(tones) > 0 && <button className={tab === "tones" ? "active" : ""} onClick={() => setTab("tones")}>Tones</button>}
        </div>
      </div>

      <div className="inspector-content">
      {tab === "overview" ? (
        <>
          <section className="panel">
            <div className="panel-title">
              <h2>Package Overview</h2>
              <span>{item ? statusText(item.status) : "Waiting"}</span>
            </div>
            {item?.error && <div className="error-box"><AlertTriangle size={17} /> {item.error}</div>}
            {itemWarnings.length > 0 && (
              <div className="warning-box"><AlertTriangle size={17} /> <span>{itemWarnings.join("\n")}</span></div>
            )}
            <div className="overview-metrics">
              <FeedPakMetric label={preview?.is_multi_song ? "Songs" : "Arrangements"} value={preview?.is_multi_song ? preview.song_count : arrangements.length} />
              <FeedPakMetric label={preview?.is_multi_song ? "Preview arrangements" : "Stems"} value={preview?.is_multi_song ? arrangements.length : stems.length} />
              <FeedPakMetric label={preview?.is_multi_song ? "Preview tone rigs" : "Tone rigs"} value={countToneDefinitions(tones)} />
              <FeedPakMetric label="Credits" value={authors.length} />
            </div>
            <ul className="readiness readiness-grid">
              <ReadyLine ok={!!cover} text={cover ? "Cover image detected" : "No cover image"} muted={!cover} />
              <ReadyLine ok={arrangements.length > 0} text={`${arrangements.length || 0} ${isMultiSong ? "first-song preview " : ""}arrangement${arrangements.length === 1 ? "" : "s"}`} />
              {isFeedpak && <ReadyLine ok={stems.some((stem) => String(stem.id || "").toLowerCase() === "full")} text="Full mix present" />}
              <ReadyLine ok={!!preview?.lyrics} text={preview?.lyrics ? `${preview.lyrics} lyric timing events` : "No lyric timing"} muted={!preview?.lyrics} />
              <ReadyLine ok={authors.length > 0} text={authors.length ? `${authors.length} credit${authors.length === 1 ? "" : "s"}` : "No embedded credit"} muted={!authors.length} />
              {isFeedpak && validation && <ReadyLine ok={!!validation.ok} text={validation.ok ? "Spec validation passed" : "Spec validation failed"} />}
            </ul>
            {preview?.is_multi_song && !outputCount && (
              <div className="info-box"><Info size={17} /> This multi-song PSARC will create {preview.song_count} separate FeedPaks when converted.</div>
            )}
            {outputCount > 1 && (
              <div className="info-box success"><Check size={17} /> Created {outputCount} separate FeedPaks{item.outputPaths?.[0] ? ` in ${parentDir(item.outputPaths[0])}` : ""}.</div>
            )}
            {isFeedpak && validation && !validation.ok && (
              <div className="error-box">
                <AlertTriangle size={17} />
                <div>
                  {(validation.errors || []).slice(0, 4).map((error, index) => <p key={`${error}-${index}`}>{error}</p>)}
                  {(validation.errors || []).length > 4 && <p>+{validation.errors.length - 4} more validation issue{validation.errors.length - 4 === 1 ? "" : "s"}</p>}
                </div>
              </div>
            )}
          </section>

          {authors.length > 0 && (
            <section className="panel">
              <div className="panel-title">
                <h2>Credits</h2>
                <span>Source credits</span>
              </div>
              <div className="credit-list">
                {authors.map((author, index) => (
                  <div className="credit-row" key={`${author.name}-${author.role || "credit"}-${index}`}>
                    <strong>{author.name}</strong>
                    <span>{author.role || "contributor"}</span>
                  </div>
                ))}
              </div>
            </section>
          )}

          <section className="panel">
            <div className="panel-title">
              <h2>{isMultiSong ? "First-song arrangements" : "Arrangements"}</h2>
              <Guitar size={18} />
            </div>
            <div className="arrangements">
              {arrangements.length === 0 && <div className="empty compact">No arrangements inspected yet.</div>}
              {arrangements.map((arrangement) => (
                <div className="arrangement" key={arrangement.id}>
                  <strong>{arrangement.name}</strong>
                  {arrangement.type !== "drums" && <span>{arrangement.difficulties} levels</span>}
                  <span>{arrangement.note_count || arrangement.notes + arrangement.chords} {arrangement.type === "drums" ? "hits" : "notes"}</span>
                </div>
              ))}
            </div>
          </section>
        </>
      ) : tab === "metadata" && isFeedpak ? (
        <section className="panel feedpak-editor">
          <div className="panel-title">
            <h2>Edit FeedPak</h2>
            <span>{saveMessage || (overwriteOriginal ? "Editing original package" : "Saves a copy by default")}</span>
          </div>
          <div className="editor-grid">
            <label>Title<input value={editMetadata?.title || ""} onChange={(event) => setEditMetadata((current) => ({ ...current, title: event.target.value }))} /></label>
            <label>Artist<input value={editMetadata?.artist || ""} onChange={(event) => setEditMetadata((current) => ({ ...current, artist: event.target.value }))} /></label>
            <label>Album<input value={editMetadata?.album || ""} onChange={(event) => setEditMetadata((current) => ({ ...current, album: event.target.value }))} /></label>
            <label>Year<input value={editMetadata?.year || ""} onChange={(event) => setEditMetadata((current) => ({ ...current, year: event.target.value }))} /></label>
            <label>Language<input value={editMetadata?.language || ""} onChange={(event) => setEditMetadata((current) => ({ ...current, language: event.target.value }))} /></label>
            <label className="wide">Charters / credits<textarea value={authorsText} onChange={(event) => setAuthorsText(event.target.value)} placeholder="Name | charter" rows={5} /></label>
          </div>
          <label className="toggle editor-overwrite">
            <input type="checkbox" checked={overwriteOriginal} onChange={(event) => setOverwriteOriginal(event.target.checked)} />
            Overwrite original FeedPak
          </label>
          <div className="editor-actions">
            <button className="primary" onClick={saveFeedpak}><Check size={16} /> {overwriteOriginal ? "Save original" : "Save copy"}</button>
            <button onClick={() => onReplaceFeedpakCover(item, { overwriteOriginal })}><ImageIcon size={16} /> Replace cover</button>
            <button className="ghost" onClick={() => onRemoveFeedpakCover(item, { overwriteOriginal })}><XCircle size={16} /> Remove cover</button>
          </div>
        </section>
      ) : tab === "stems" && isFeedpak ? (
        <section className="panel feedpak-editor stem-editor-panel">
          <div className="panel-title">
            <h2>Stems</h2>
            <span>{stemMessage || `${stems.length} audio file${stems.length === 1 ? "" : "s"}`}</span>
          </div>
          <div className="stem-editor-callout">
            <strong>Full mix stays protected</strong>
            <span>Split-stem packages keep the full mix for fallback playback.</span>
          </div>
          <div className="stem-reprocess-card">
            <div>
              <strong>Reprocess this FeedPak</strong>
              <span>{separateStems ? `${stemSelectionSummary(demucsStems)} Existing stems will be refreshed from full.ogg.` : "Turn on Separate stems in Settings to split or refresh stems from full.ogg."}</span>
              {separateStems && stemSelectionWarning(demucsStems) && (
                <em>{stemSelectionWarning(demucsStems)}</em>
              )}
            </div>
            <button className="primary" onClick={reprocessStems} disabled={!separateStems}>
              <RotateCw size={16} /> Reprocess stems
            </button>
          </div>
          <div className="stem-editor-toolbar">
            <label>
              Stem name
              <input
                list="feedforge-stem-ids"
                value={stemEditId}
                onChange={(event) => setStemEditId(event.target.value)}
                placeholder="guitar, bass, vocals, custom"
              />
            </label>
            <button className="primary" onClick={addStem}><Plus size={16} /> Add / replace</button>
            <label className="toggle editor-overwrite">
              <input type="checkbox" checked={overwriteOriginal} onChange={(event) => setOverwriteOriginal(event.target.checked)} />
              Overwrite original
            </label>
          </div>
          <datalist id="feedforge-stem-ids">
            {["full", "guitar", "bass", "drums", "vocals", "piano", "other"].map((id) => <option key={id} value={id} />)}
          </datalist>
          <div className="stem-list editable">
            {stems.length === 0 && <div className="empty compact">No stems listed in manifest.</div>}
            {stems.map((stem) => {
              const stemId = String(stem.id || "").toLowerCase();
              return (
                <div className="stem-row editable" key={`${stem.id}-${stem.file}`}>
                  <div>
                    <strong>{stem.id}</strong>
                    <span>{stem.file}</span>
                  </div>
                  <span>{stem.codec || "audio"} - {formatBytes(stem.size)}</span>
                  {stem.default && <b>default</b>}
                  <button onClick={() => replaceStem(stem.id)}><FileMusic size={15} /> Replace</button>
                  <button
                    className="ghost"
                    onClick={() => removeStem(stem.id)}
                    disabled={stemId === "full"}
                    title={stemId === "full" ? "The full mix is required by the FeedPak spec." : `Remove ${stem.id}`}
                  >
                    <XCircle size={15} /> Remove
                  </button>
                </div>
              );
            })}
          </div>
        </section>
      ) : (
        <ToneInspector arrangements={arrangements} tones={tones} />
      )}
      </div>
    </aside>
  );
}

export function ToneInspector({ arrangements, tones, expanded = false }) {
  const rows = useMemo(() => (arrangements?.length ? arrangements : tones || []).map((arrangement) => {
    const id = arrangement.id || arrangement.arrangement_id;
    const tone = (tones || []).find((candidate) => candidate.arrangement_id === id);
    return {
      id,
      name: arrangement.name || arrangement.arrangement_name || id,
      type: arrangement.type || "guitar",
      tone
    };
  }), [arrangements, tones]);
  const [activeArrangement, setActiveArrangement] = useState(rows[0]?.id || "");
  const activeRow = rows.find((arrangement) => arrangement.id === activeArrangement) || rows[0] || null;
  const active = activeRow?.tone || null;
  const activeChanges = active?.changes || [];
  const visibleChanges = expanded ? activeChanges : activeChanges.slice(0, 16);
  const timelineDuration = toneTimelineDuration(activeChanges);
  useEffect(() => {
    if (rows.length && !rows.some((arrangement) => arrangement.id === activeArrangement)) {
      setActiveArrangement(rows[0].id);
    }
  }, [rows, activeArrangement]);

  return (
    <section className={`panel tone-panel ${expanded ? "expanded" : ""}`}>
      <div className="panel-title">
        <h2>Tone Data</h2>
        <span>{countToneDefinitions(tones)} definitions / {countToneChanges(tones)} changes</span>
      </div>
      {rows.length === 0 && (
        <div className="empty compact">No playable arrangements were detected for this song.</div>
      )}
      {rows.length > 0 && (
        <div className="arrangement-tabs">
          {rows.map((arrangement) => (
            <button
              key={arrangement.id}
              className={activeRow?.id === arrangement.id ? "active" : ""}
              onClick={() => setActiveArrangement(arrangement.id)}
            >
              {arrangement.name}
              <span>{arrangement.tone?.definitions?.length || 0}</span>
            </button>
          ))}
        </div>
      )}
      {activeRow && !active && (
        <div className="empty compact">
          No tone data was detected for {activeRow.name}. The arrangement will still be exported.
        </div>
      )}
      {active && (
        <div className="tone-arrangement" key={active.arrangement_id}>
          <div className="tone-arrangement-head">
            <div>
              <strong>{active.arrangement_name}</strong>
              <span>Base: {active.base || "Not set"}</span>
            </div>
            <code>{active.base_rig || "no-rig"}</code>
          </div>

          <div className="tone-section">
            <h3>FeedPak Timeline</h3>
            {activeChanges.length > 0 && (
              <div className="tone-timeline-track" aria-label="Tone change timeline">
                {activeChanges.map((change, index) => (
                  <span
                    className="tone-marker"
                    key={`${change.time}-${change.name}-${index}-marker`}
                    style={{ left: `${Math.max(0, Math.min(100, (Number(change.time || 0) / timelineDuration) * 100))}%` }}
                    title={`${duration(change.time)} ${change.name}`}
                  />
                ))}
              </div>
            )}
            <div className="tone-changes">
              {(active.changes || []).length === 0 && <span className="muted-text">No tone changes. Base tone is used for the whole song.</span>}
              {visibleChanges.map((change, index) => (
                <div className="tone-change" key={`${change.time}-${change.name}-${index}`}>
                  <b>{duration(change.time)}</b>
                  <span>{change.name}</span>
                  <code>{change.rig}</code>
                </div>
              ))}
              {!expanded && activeChanges.length > 16 && <span className="muted-text">Showing first 16 of {activeChanges.length} tone changes.</span>}
            </div>
          </div>

          <div className="tone-section">
            <h3>Source Tone Definitions</h3>
            <div className="tone-definitions">
              {(active.definitions || []).map((definition) => (
                <div className="tone-definition" key={definition.key || definition.name}>
                  <div className="tone-definition-head">
                    <div>
                      <strong>{definition.name || "Unnamed tone"}</strong>
                      <span>PSARC key: {definition.key || "no-key"}</span>
                    </div>
                  </div>
                  <div className="gear-list">
                    {(definition.gear || []).length === 0 && <span className="muted-text">No gear chain found.</span>}
                    {(definition.gear || []).map((gear) => (
                      <div className={`gear-chip ${gearClassName(gear)}`} key={`${definition.key}-${gear.slot}-${gear.key}`}>
                        <div className="gear-visual">
                          <span className="gear-role">{gearRoleLabel(gear)}</span>
                          {gear.asset_path ? (
                            <img src={`file:///${gear.asset_path.replaceAll("\\", "/")}`} alt="" />
                          ) : (
                            <div className="gear-face">
                              <b>{gearInitials(gear)}</b>
                              <i />
                              <i />
                              <i />
                            </div>
                          )}
                        </div>
                        <span>{gear.slot}</span>
                        <strong>{gear.key || gear.type || "Unknown gear"}</strong>
                        <small>{gear.category || gear.type || "source gear"} / {gear.knobs} knobs</small>
                        <KnobValues values={gear.knob_values} />
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

export function KnobValues({ values }) {
  const entries = Object.entries(values || {}).slice(0, 6);
  if (!entries.length) return null;
  return (
    <div className="knob-values">
      {entries.map(([key, value]) => (
        <span key={key} title={`${shortKnob(key)} ${formatKnob(value)}`}>
          <b>{shortKnob(key)}</b>
          <i><em style={{ width: `${knobPercent(value)}%` }} /></i>
          <small>{formatKnob(value)}</small>
        </span>
      ))}
    </div>
  );
}

export function gearClassName(gear) {
  const text = `${gear?.slot || ""} ${gear?.category || ""} ${gear?.key || ""} ${gear?.type || ""}`.toLowerCase();
  if (text.includes("cab")) return "gear-cab";
  if (text.includes("amp")) return "gear-amp";
  if (text.includes("delay") || text.includes("reverb") || text.includes("rack")) return "gear-rack";
  if (text.includes("dist") || text.includes("drive") || text.includes("fuzz") || text.includes("pedal")) return "gear-pedal";
  return "gear-effect";
}

export function gearRoleLabel(gear) {
  const slot = String(gear?.slot || "").toLowerCase();
  if (slot.includes("cabinet")) return "Cab";
  if (slot.includes("amp")) return "Amp";
  if (slot.includes("rack")) return "Rack";
  if (slot.includes("pre")) return "Pre";
  if (slot.includes("post")) return "Post";
  return "FX";
}

export function gearInitials(gear) {
  const source = String(gear?.key || gear?.type || gear?.slot || "FX").replace(/^(Amp|Cab|Pedal|Rack|Bass_Cab|Cabinet)_/i, "");
  const tokens = source.split(/[_\s-]+/).filter(Boolean);
  return (tokens.length > 1 ? `${tokens[0][0]}${tokens[1][0]}` : source.slice(0, 2)).toUpperCase();
}

export function knobPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 0;
  if (number >= 0 && number <= 1) return Math.round(number * 100);
  return Math.max(0, Math.min(100, Math.round(number)));
}

export function shortKnob(value) {
  return String(value).replace(/^[A-Za-z0-9]+_/, "");
}

export function formatKnob(value) {
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  return String(value);
}
