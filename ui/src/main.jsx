import { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Coffee, Download, ExternalLink, FileMusic, FolderOpen, Globe, Guitar, Plus, Power, RotateCw, Search, Server, SlidersHorizontal, Square, XCircle } from "lucide-react";
import { runConversionQueues, usesSharedRs1SongsAudio } from "./conversion-scheduler.mjs";
import SongsterrWorkspace from "./features/songsterr/SongsterrWorkspace.jsx";
import Home from "./features/Home.jsx";
import ConversionDialog from "./features/ConversionDialog.jsx";
import { importDestination } from "./import-navigation.mjs";
import feedForgeLogo from "../../assets/feedforge.png";
import "./workbench.css";

import { api, INSPECTION_WORKERS, AUTO_SETTING, DEFAULT_CONVERSION_WORKERS, DEFAULT_DEMUCS_STEM_JOBS, DEFAULT_DEMUCS_STEMS, DEMUCS_STEM_OPTIONS } from "./settings.mjs";
import { stemServerBadge, headerStemStatusClass, headerStemStatusLabel, stemServerTitle, stemServerActionText, StemSetupProgress, stemServerDetail, stemServerPortOwners, stemServerMatchesSelection, normalizeStemSelection, toggleStemSelection, stemSelectionSummary, stemSelectionWarning, StemSetupChecklist, pythonPrereqTitle, Metric, LibraryAuditPanel, ConversionProgress, FilterSelect, selectedDemucsModel, defaultDemucsDevices, selectedDemucsDevice, normalizeAutoNumberSetting, normalizeInitialStemJobs, resolveConversionWorkerCount, resolveStemJobCount, mergeDemucsDevices, deviceLabel, deviceHelpText, stemJobHelpText, stemJobSelectionLabel, resolvedDeviceLabel, modelStatusLabel, DropZone, itemDisplayTitle, itemProgressSubtitle, Queue, FeedPakTools, Inspector } from "./WorkspacePanels.jsx";
import { isSongPackage, fileType, isRs1SongsArchive, sortedOptions, arrangementTuningLabels, basename, reserveBatchOutputPaths, editedFeedpakPath, outputNameTemplateForFormat, commonAncestorDir, normalizePathKey, readSettings, normalizeAuditCriteria, writeSettings, parentDir } from "./workspace-utils.jsx";
function DiscordIcon({ size = 17 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
      className="discord-icon"
    >
      <path
        fill="currentColor"
        d="M20.32 4.37A19.8 19.8 0 0 0 15.36 3l-.24.47c-.1.2-.2.42-.28.64a18.4 18.4 0 0 0-5.68 0 8.6 8.6 0 0 0-.52-1.1c-1.73.3-3.4.77-4.96 1.36C.56 9.05-.29 13.6.14 18.08a19.9 19.9 0 0 0 6.08 3.08c.49-.66.92-1.36 1.29-2.1-.7-.26-1.36-.58-1.98-.95l.48-.38a14.2 14.2 0 0 0 11.98 0l.48.38c-.62.37-1.29.69-1.99.95.37.74.8 1.44 1.29 2.1a19.8 19.8 0 0 0 6.09-3.08c.5-5.2-.85-9.7-3.54-13.71ZM8.02 15.32c-1.18 0-2.14-1.08-2.14-2.4 0-1.33.95-2.4 2.14-2.4 1.2 0 2.16 1.08 2.14 2.4 0 1.32-.95 2.4-2.14 2.4Zm7.96 0c-1.18 0-2.14-1.08-2.14-2.4 0-1.33.95-2.4 2.14-2.4 1.2 0 2.16 1.08 2.14 2.4 0 1.32-.95 2.4-2.14 2.4Z"
      />
    </svg>
  );
}

function App() {
  const [conversionRequest, setConversionRequest] = useState(null);
  const conversionChoiceRef = useRef(null);

  async function requestConversion() {
    if (conversionChoiceRef.current) return null;
    const options = { demucsUrl: demucsUrl.trim() || "http://127.0.0.1:7865", demucsApiKey: demucsApiKey.trim(), demucsModel, demucsStems };
    // Reserve before the health request so repeated clicks cannot queue dialogs.
    conversionChoiceRef.current = () => {};
    let status;
    try { status = await api.checkStemServer({ url: demucsUrl, apiKey: demucsApiKey, model: demucsModel }); }
    catch (error) { status = { ready: false, error: error.message }; }
    return new Promise(resolve => {
      conversionChoiceRef.current = resolve;
      setConversionRequest({ enabled: separateStems, ready: status.ready, stems: demucsStems, error: status.error, options });
    });
  }

  function finishConversionChoice(choice) {
    const resolve = conversionChoiceRef.current;
    conversionChoiceRef.current = null;
    setConversionRequest(null);
    resolve?.(choice === null ? null : {
      ...conversionRequest.options, separateStems: choice
    });
  }

  const initialSettingsRef = useRef(null);
  if (initialSettingsRef.current === null) {
    initialSettingsRef.current = readSettings();
  }

  const [items, setItems] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [outputDir, setOutputDir] = useState(() => initialSettingsRef.current.outputDir || null);
  const [outputLayout, setOutputLayout] = useState(() => initialSettingsRef.current.outputLayout || "flat");
  const [outputNameFormat, setOutputNameFormat] = useState(() => initialSettingsRef.current.outputNameFormat || "source");
  const [outputNameTemplate, setOutputNameTemplate] = useState(() => initialSettingsRef.current.outputNameTemplate || "{artist} - {title}");
  const [lastSourcePath, setLastSourcePath] = useState(() => initialSettingsRef.current.lastSourcePath || null);
  const [overwrite, setOverwrite] = useState(false);
  const [separateStems, setSeparateStems] = useState(() => initialSettingsRef.current.separateStems === true);
  const [demucsUrl, setDemucsUrl] = useState(() => initialSettingsRef.current.demucsUrl || "");
  const [demucsApiKey, setDemucsApiKey] = useState("");
  const [demucsInstallDir, setDemucsInstallDir] = useState(() => initialSettingsRef.current.demucsInstallDir || "");
  const [pythonPath, setPythonPath] = useState(() => initialSettingsRef.current.pythonPath || "");
  const [demucsModel, setDemucsModel] = useState(() => initialSettingsRef.current.demucsModel || "htdemucs_6s");
  const [demucsDevice, setDemucsDevice] = useState(() => initialSettingsRef.current.demucsDevice || "auto");
  const [demucsStemJobs, setDemucsStemJobs] = useState(() => normalizeInitialStemJobs(initialSettingsRef.current));
  const [demucsStems, setDemucsStems] = useState(() => normalizeStemSelection(initialSettingsRef.current.demucsStems));
  const [demucsDevices, setDemucsDevices] = useState(defaultDemucsDevices());
  const [demucsModels, setDemucsModels] = useState([]);
  const [demucsModelRoot, setDemucsModelRoot] = useState("");
  const [demucsSetup, setDemucsSetup] = useState(null);
  const [stemServerStatus, setStemServerStatus] = useState({ url: "http://127.0.0.1:7865", running: false, starting: false, healthy: false });
  const [isStartingStemServer, setIsStartingStemServer] = useState(false);
  const [isFreeingStemPort, setIsFreeingStemPort] = useState(false);
  const [debugLogInfo, setDebugLogInfo] = useState(null);
  const [pythonInfo, setPythonInfo] = useState(null);
  const [isCheckingPython, setIsCheckingPython] = useState(false);
  const [updateInfo, setUpdateInfo] = useState(null);
  const [appVersion, setAppVersion] = useState("");
  const [auditFolder, setAuditFolder] = useState(() => initialSettingsRef.current.auditFolder || "");
  const [auditCriteria, setAuditCriteria] = useState(() => normalizeAuditCriteria(initialSettingsRef.current.auditCriteria));
  const [auditReport, setAuditReport] = useState(null);
  const [isAuditingLibrary, setIsAuditingLibrary] = useState(false);
  const [conversionWorkers, setConversionWorkers] = useState(() => normalizeAutoNumberSetting(initialSettingsRef.current.conversionWorkers, DEFAULT_CONVERSION_WORKERS));
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [artistFilter, setArtistFilter] = useState("all");
  const [albumFilter, setAlbumFilter] = useState("all");
  const [tuningFilter, setTuningFilter] = useState("all");
  const [activeView, setActiveView] = useState("home");
  const workspaceRef = useRef(null);
  useEffect(() => { workspaceRef.current?.scrollTo(0, 0); }, [activeView]);
  const [settingsSection, setSettingsSection] = useState("conversion");
  const [isConverting, setIsConverting] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const [conversionProgress, setConversionProgress] = useState({ total: 0, completed: 0, failed: 0, active: [], stopped: false });
  const itemsRef = useRef(items);
  const inspectionQueueRef = useRef([]);
  const activeInspectionsRef = useRef(0);
  const isConvertingRef = useRef(false);
  const stopRequestedRef = useRef(false);

  useEffect(() => {
    itemsRef.current = items;
  }, [items]);

  useEffect(() => {
    writeSettings({ bStandardTo7String: false, outputDir, outputLayout, outputNameFormat, outputNameTemplate, lastSourcePath, separateStems, conversionWorkers, demucsUrl, demucsInstallDir, pythonPath, demucsModel, demucsDevice, demucsStemJobs, demucsStems, auditFolder, auditCriteria, performanceSettingsVersion: 2 });
  }, [outputDir, outputLayout, outputNameFormat, outputNameTemplate, lastSourcePath, separateStems, conversionWorkers, demucsUrl, demucsInstallDir, pythonPath, demucsModel, demucsDevice, demucsStemJobs, demucsStems, auditFolder, auditCriteria]);

  useEffect(() => {
    let cancelled = false;
    async function loadVersion() {
      try {
        const version = await api.getAppVersion();
        if (!cancelled) {
          setAppVersion(version || "");
          if (version) document.title = `FeedForge ${version}`;
        }
      } catch {
        if (!cancelled) setAppVersion("");
      }
    }
    loadVersion();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (typeof api.onPlanningProgress !== "function") return undefined;
    return api.onPlanningProgress((progress) => {
      if (!isConvertingRef.current) return;
      setConversionProgress((current) => {
        if (current.phase !== "planning") return current;
        const total = Math.max(0, Number(progress?.total) || current.total || 0);
        return {
          ...current,
          total,
          completed: Math.min(total, Math.max(0, Number(progress?.completed) || 0)),
          planningCached: Math.max(0, Number(progress?.cached) || 0),
          planningWorkers: Math.max(1, Number(progress?.workers) || 1),
          planningStage: progress?.stage || "metadata"
        };
      });
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function check() {
      try {
        const result = await api.checkForUpdates();
        if (!cancelled) setUpdateInfo(result);
      } catch {
        if (!cancelled) setUpdateInfo(null);
      }
    }
    const timer = window.setTimeout(check, 3500);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function loadLogInfo() {
      try {
        const info = await api.getDebugLogInfo();
        if (!cancelled) setDebugLogInfo(info);
      } catch {
        if (!cancelled) setDebugLogInfo(null);
      }
    }
    loadLogInfo();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (activeView !== "stems" || !separateStems) return undefined;
    let cancelled = false;
    async function loadStemPrereqs(showSpinner = true) {
      try {
        if (showSpinner) setIsCheckingPython(true);
        const [result, python] = await Promise.all([
          api.getStemServerModels({ installDir: demucsInstallDir }),
          api.getPythonInfo({ installDir: demucsInstallDir, pythonPath }),
        ]);
        if (cancelled) return;
        setDemucsModels(result.models || []);
        setDemucsDevices(result.devices?.length ? result.devices : defaultDemucsDevices());
        setPythonInfo(python);
        setDemucsModelRoot(result.installRoot || result.defaultInstallDir || "");
        setDemucsSetup(result.setup || null);
        if (!demucsInstallDir && result.defaultInstallDir) {
          setDemucsInstallDir(result.defaultInstallDir);
        }
      } catch {
        // Model metadata is helpful but not required for conversion.
      } finally {
        if (!cancelled && showSpinner) setIsCheckingPython(false);
      }
    }
    loadStemPrereqs();
    const shouldTrackSetup = isStartingStemServer || stemServerStatus.processRunning || stemServerStatus.starting || stemServerStatus.phase === "downloading" || stemServerStatus.phase === "installing" || stemServerStatus.phase === "loading";
    const timer = window.setInterval(() => loadStemPrereqs(false), shouldTrackSetup ? 1500 : 8000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [activeView, separateStems, demucsInstallDir, pythonPath, demucsModel, isStartingStemServer, stemServerStatus.processRunning, stemServerStatus.starting, stemServerStatus.phase]);

  useEffect(() => {
    let cancelled = false;
    async function refresh() {
      try {
        const status = await api.getStemServerStatus();
        if (!cancelled) {
          setStemServerStatus(status);
          if (status.accelerators?.length) {
            setDemucsDevices((current) => mergeDemucsDevices(current, status.accelerators));
          }
        }
      } catch {
        if (!cancelled) setStemServerStatus((current) => ({ ...current, running: false, healthy: false }));
      }
    }
    const initialTimer = window.setTimeout(refresh, 800);
    const pollMs = (isStartingStemServer || stemServerStatus.starting || stemServerStatus.processRunning) && !stemServerStatus.healthy
      ? 1000
      : separateStems
        ? 5000
        : 12000;
    const timer = window.setInterval(refresh, pollMs);
    return () => {
      cancelled = true;
      window.clearTimeout(initialTimer);
      window.clearInterval(timer);
    };
  }, [separateStems, isStartingStemServer, stemServerStatus.starting, stemServerStatus.processRunning, stemServerStatus.healthy]);

  useEffect(() => {
    return api.onDroppedPaths(async (paths) => {
      const expanded = await api.expandPaths(paths);
      rememberSourcePath(paths[0]);
      addFiles(expanded);
    });
  }, []);

  const selected = items.find((item) => item.id === selectedId) || null;
  const workspaceItems = useMemo(() => items.filter((item) => item.sourceType !== "feedpak"), [items]);
  const feedpakItems = useMemo(() => items.filter((item) => item.sourceType === "feedpak"), [items]);
  const workspaceSelected = selected?.sourceType === "feedpak" ? null : selected || workspaceItems[0] || null;
  const feedpakSelected = selected?.sourceType === "feedpak" ? selected : feedpakItems[0] || null;
  const filterOptions = useMemo(() => {
    const artists = new Set();
    const albums = new Set();
    const tunings = new Set();
    for (const item of workspaceItems) {
      if (item.preview?.artist) artists.add(item.preview.artist);
      if (item.preview?.album) albums.add(item.preview.album);
      for (const label of arrangementTuningLabels(item.preview?.arrangements || [])) {
        tunings.add(label);
      }
    }
    return {
      artists: sortedOptions(artists),
      albums: sortedOptions(albums),
      tunings: sortedOptions(tunings)
    };
  }, [workspaceItems]);

  const filtered = workspaceItems.filter((item) => {
    const haystack = `${item.name || ""} ${item.path || ""} ${item.preview?.title || ""} ${item.preview?.artist || ""} ${item.preview?.album || ""}`.toLowerCase();
    const matchesQuery = haystack.includes(query.toLowerCase());
    const matchesFilter =
      filter === "all" ||
      (filter === "ready" && ["ready", "converted"].includes(item.status)) ||
      (filter === "issues" && ["failed", "needs-review"].includes(item.status)) ||
      (filter === "converted" && item.status === "converted");
    const matchesArtist = artistFilter === "all" || item.preview?.artist === artistFilter;
    const matchesAlbum = albumFilter === "all" || item.preview?.album === albumFilter;
    const itemTunings = arrangementTuningLabels(item.preview?.arrangements || []);
    const matchesTuning = tuningFilter === "all" || itemTunings.includes(tuningFilter);
    return matchesQuery && matchesFilter && matchesArtist && matchesAlbum && matchesTuning;
  });

  const stats = useMemo(() => ({
    total: workspaceItems.length,
    ready: workspaceItems.filter((item) => item.status === "ready" || item.status === "converted").length,
    converted: workspaceItems.filter((item) => item.status === "converted").length,
    failed: workspaceItems.filter((item) => item.status === "failed").length
  }), [workspaceItems]);
  const stemServerBusy = (isStartingStemServer || stemServerStatus.starting || stemServerStatus.processRunning) && !stemServerStatus.healthy;
  const selectedModel = selectedDemucsModel(demucsModels, demucsModel);
  const selectedDevice = selectedDemucsDevice(demucsDevices, demucsDevice);
  const effectiveDemucsStemJobs = resolveStemJobCount(demucsStemJobs, demucsDevice, demucsDevices);
  const effectiveConversionWorkers = resolveConversionWorkerCount(conversionWorkers, { separateStems, stemJobs: effectiveDemucsStemJobs });
  const stemServerMatchesSelectedConfig = stemServerMatchesSelection(stemServerStatus, demucsModel, demucsDevice, effectiveDemucsStemJobs);
  const stemServerReadyForSelection = stemServerStatus.healthy && stemServerMatchesSelectedConfig;

  async function addFiles(paths, sourceRoot = null, navigate = true) {
    const supported = paths.filter(isSongPackage);
    const destination = importDestination(supported, navigate);
    if (destination) {
      setActiveView(destination);
      const selectedPath = supported.find(path => fileType(path) === (destination === "feedpak" ? "feedpak" : "psarc"));
      const loaded = itemsRef.current.find(item => normalizePathKey(item.path) === normalizePathKey(selectedPath));
      if (loaded) setSelectedId(loaded.id);
    }
    const existing = new Set(itemsRef.current.map((item) => normalizePathKey(item.path)));
    const incoming = paths
      .filter((filePath) => isSongPackage(filePath))
      .filter((filePath) => {
        const key = normalizePathKey(filePath);
        if (existing.has(key)) return false;
        existing.add(key);
        return true;
      })
      .map((filePath) => ({
        id: crypto.randomUUID(),
        path: filePath,
        name: basename(filePath),
        sourceType: fileType(filePath),
        sourceRoot,
        status: "queued",
        preview: null,
        outputPath: null,
        outputPaths: [],
        message: null,
        warnings: [],
        error: null
    }));
    if (!incoming.length) return;
    rememberSourcePath(incoming[0].path);
    const nextItems = [...itemsRef.current, ...incoming];
    itemsRef.current = nextItems;
    setItems(nextItems);
    if (!selectedId) setSelectedId(incoming[0].id);
    inspectionQueueRef.current.push(...incoming.map((item) => item.id));
    pumpInspectionQueue();
  }

  function updateItem(id, patch) {
    const apply = (current) => current.map((entry) => {
      if (entry.id !== id) return entry;
      return typeof patch === "function" ? patch(entry) : { ...entry, ...patch };
    });
    itemsRef.current = apply(itemsRef.current);
    setItems((current) => apply(current));
  }

  function removeItem(id) {
    if (isConvertingRef.current) return;
    inspectionQueueRef.current = inspectionQueueRef.current.filter((queuedId) => queuedId !== id);
    const nextItems = itemsRef.current.filter((item) => item.id !== id);
    itemsRef.current = nextItems;
    setItems(nextItems);
    if (selectedId === id) {
      setSelectedId(nextItems[0]?.id || null);
    }
  }

  function pumpInspectionQueue() {
    if (isConvertingRef.current) return;
    while (activeInspectionsRef.current < INSPECTION_WORKERS && inspectionQueueRef.current.length > 0) {
      const id = inspectionQueueRef.current.shift();
      const item = itemsRef.current.find((entry) => entry.id === id);
      if (!item || item.status === "converted") continue;
      activeInspectionsRef.current += 1;
      inspectItem(item).finally(() => {
        activeInspectionsRef.current -= 1;
        pumpInspectionQueue();
      });
    }
  }

  async function inspectItem(item) {
    updateItem(item.id, { status: "inspecting" });
    const result = await api.inspect(item.path);
    if (!result.ok) {
      updateItem(item.id, (current) => {
        if (current.status === "converted" || current.status === "converting") return current;
        return { ...current, status: "failed", warnings: [], error: result.error };
      });
      return;
    }
    const preview = result.preview;
    updateItem(item.id, (current) => {
      if (current.status === "converted" || current.status === "converting") return current;
      return {
        ...current,
        status: preview.arrangements?.length ? "ready" : "needs-review",
        preview,
        warnings: Array.isArray(preview.warnings) ? preview.warnings.filter(Boolean) : [],
        error: null
      };
    });
  }

  async function chooseFiles() {
    const paths = await api.pickPsarc({ defaultPath: lastSourcePath || outputDir || undefined });
    rememberSourcePath(paths[0]);
    addFiles(paths);
  }

  async function chooseFolder(destination = null) {
    if (api.pickFolderWithRoot) {
      const result = await api.pickFolderWithRoot({ defaultPath: lastSourcePath || outputDir || undefined });
      if (!result.folder && !result.files?.length) return;
      rememberSourcePath(result.folder || result.files?.[0]);
      if (result.folder && destination) setActiveView(destination);
      addFiles(result.files || [], result.folder || null, destination || true);
      return;
    }
    const paths = await api.pickFolder({ defaultPath: lastSourcePath || outputDir || undefined });
    if (!paths.length) return;
    rememberSourcePath(paths[0]);
    addFiles(paths, null, destination || true);
  }

  async function chooseOutput() {
    const folder = await api.pickOutput({ defaultPath: outputDir || lastSourcePath || undefined });
    if (folder) setOutputDir(folder);
  }

  async function startLocalStemServer() {
    if (isStartingStemServer) return;
    setIsStartingStemServer(true);
    setStemServerStatus((current) => ({
      ...current,
      running: true,
      starting: true,
      healthy: false,
      phase: "starting",
      message: "Preparing local stem setup. The first run may download Python packages and the selected Demucs model.",
      log: [
        ...(current.log || []).slice(-12),
        "FeedForge: preparing local stem setup",
        `FeedForge: selected model ${demucsModel}`,
        `FeedForge: selected device ${demucsDevice}`,
        `FeedForge: stem jobs ${effectiveDemucsStemJobs}${demucsStemJobs === AUTO_SETTING ? " (auto)" : ""}`
      ]
    }));
    try {
      const status = await api.startStemServer({ installDir: demucsInstallDir, pythonPath, model: demucsModel, device: demucsDevice, concurrency: effectiveDemucsStemJobs });
      setStemServerStatus(status);
      if (status.url) setDemucsUrl(status.url);
      const result = await api.getStemServerModels({ installDir: demucsInstallDir });
      setDemucsModels(result.models || []);
      setDemucsDevices(result.devices?.length ? result.devices : defaultDemucsDevices());
      setDemucsModelRoot(result.installRoot || result.defaultInstallDir || "");
      setDemucsSetup(result.setup || null);
    } catch (error) {
      setStemServerStatus((current) => ({
        ...current,
        running: false,
        starting: false,
        healthy: false,
        phase: "error",
        message: error?.message || "Stem server setup failed. Open the debug log for details.",
        log: [...(current.log || []).slice(-16), `FeedForge: ${error?.message || "stem setup failed"}`]
      }));
    } finally {
      setIsStartingStemServer(false);
    }
  }

  async function recheckPython() {
    setIsCheckingPython(true);
    try {
      setPythonInfo(await api.getPythonInfo({ installDir: demucsInstallDir, pythonPath }));
    } finally {
      setIsCheckingPython(false);
    }
  }

  async function choosePythonExecutable() {
    const selected = await api.pickPythonExecutable({ defaultPath: pythonPath || "" });
    if (selected) {
      setPythonPath(selected);
      setIsCheckingPython(true);
      try {
        setPythonInfo(await api.getPythonInfo({ installDir: demucsInstallDir, pythonPath: selected }));
      } finally {
        setIsCheckingPython(false);
      }
    }
  }

  async function stopLocalStemServer() {
    const status = await api.stopStemServer();
    setStemServerStatus(status);
  }

  async function freeStemServerPort() {
    if (isFreeingStemPort) return;
    const owners = stemServerPortOwners(stemServerStatus);
    const detail = owners.length
      ? owners.map((owner) => `${owner.processName || "Process"} ${owner.pid || ""}`.trim()).join(", ")
      : "the process currently listening on port 7865";
    const ok = window.confirm(`Stop ${detail} so FeedForge can start the local stem server?`);
    if (!ok) return;
    setIsFreeingStemPort(true);
    try {
      const status = await api.freeStemServerPort();
      setStemServerStatus(status);
    } finally {
      setIsFreeingStemPort(false);
    }
  }

  async function chooseDemucsInstallDir() {
    const folder = await api.pickDemucsInstallDir({ defaultPath: demucsInstallDir || undefined });
    if (folder) setDemucsInstallDir(folder);
  }

  async function chooseAuditFolder() {
    const folder = await api.pickAuditFolder({ defaultPath: auditFolder || outputDir || lastSourcePath || undefined });
    if (folder) setAuditFolder(folder);
  }

  async function runLibraryAudit() {
    if (!auditFolder || isAuditingLibrary) return;
    setIsAuditingLibrary(true);
    setAuditReport(null);
    try {
      const report = await api.auditFeedpakLibrary({ root: auditFolder, criteria: auditCriteria, workers: 3 });
      setAuditReport(report);
    } catch (error) {
      setAuditReport({ ok: false, error: error?.message || "Library audit failed." });
    } finally {
      setIsAuditingLibrary(false);
    }
  }

  function updateAuditCriterion(key, value) {
    setAuditCriteria((current) => ({ ...current, [key]: value }));
  }

  function rememberSourcePath(filePath) {
    const sourcePath = parentDir(filePath);
    if (sourcePath) setLastSourcePath(sourcePath);
  }

  async function convertQueue() {
    if (!items.length || isConvertingRef.current) return;
    const pending = [];
    const pendingPaths = new Set();
    for (const item of itemsRef.current) {
      if (item.sourceType === "feedpak" || item.status === "converted" || item.status === "converting") continue;
      const key = normalizePathKey(item.path);
      if (pendingPaths.has(key)) continue;
      pendingPaths.add(key);
      pending.push(item);
    }
    if (!pending.length) return;
    const stemOptions = await requestConversion();
    if (!stemOptions) return;
    // A previously converted songs.psarc is still the shared audio source when
    // retrying a compatibility archive, so find it in the full queue.
    const rs1SongsItem = itemsRef.current.find((item) => isRs1SongsArchive(item.path)) || null;
    const rs1SongsPsarc = rs1SongsItem?.path || null;
    isConvertingRef.current = true;
    stopRequestedRef.current = false;
    setIsStopping(false);
    setIsConverting(true);
    const conversionPending = pending;
    setConversionProgress({ total: conversionPending.length, completed: 0, failed: 0, active: [], stopped: false, phase: "planning" });
    const batchSourceRoot = commonAncestorDir(conversionPending.map((item) => item.path));
    try {
      const planById = new Map();
      const planningFailures = new Set();
      const psarcItems = conversionPending.filter((item) => item.sourceType !== "feedpak");
      const feedpakItems = conversionPending.filter((item) => item.sourceType === "feedpak");
      const nameTemplate = outputNameTemplateForFormat(outputNameFormat, outputNameTemplate);

      function failPlanning(item, message) {
        if (planningFailures.has(item.id)) return;
        planningFailures.add(item.id);
        updateItem(item.id, { status: "failed", warnings: [], error: message || "Could not determine a safe output filename." });
      }

      if (psarcItems.length) {
        let result;
        try {
          result = await api.planConversions({
            items: psarcItems.map((item) => ({
              inputPath: item.path,
              sourceRoot: item.sourceRoot || batchSourceRoot || parentDir(item.path) || ""
            })),
            outputDir: outputDir || "",
            outputLayout,
            nameTemplate,
            overwrite,
            rs1SongsPsarc: rs1SongsPsarc || "",
            workers: effectiveConversionWorkers
          });
        } catch (error) {
          result = { ok: false, error: error?.message || "Output planning failed." };
        }
        if (result?.cancelled || stopRequestedRef.current) return;
        if (!result?.ok) {
          for (const item of psarcItems) failPlanning(item, result?.error || "Output planning failed.");
        } else {
          const itemByPath = new Map(psarcItems.map((item) => [normalizePathKey(item.path), item]));
          for (const planned of result.items || []) {
            const item = itemByPath.get(normalizePathKey(planned.inputPath || ""));
            if (!item) continue;
            if (!planned.ok || !Array.isArray(planned.outputs) || !planned.outputs.length) {
              failPlanning(item, planned.error || "No FeedPak output was planned for this PSARC.");
            } else {
              planById.set(item.id, planned);
            }
          }
          for (const item of psarcItems) {
            if (!planById.has(item.id) && !planningFailures.has(item.id)) {
              failPlanning(item, "The output planner did not return a result for this PSARC.");
            }
          }
        }
      }

      const feedpakReady = [];
      for (const item of feedpakItems) {
        let current = itemsRef.current.find((entry) => entry.id === item.id) || item;
        if (!current.preview) {
          try {
            const inspected = await api.inspect(item.path);
            if (!inspected?.ok || !inspected.preview) {
              failPlanning(item, inspected?.error || "FeedPak metadata inspection failed.");
              continue;
            }
            current = { ...current, preview: inspected.preview };
            updateItem(item.id, { preview: inspected.preview, status: inspected.preview.arrangements?.length ? "ready" : "needs-review", error: null });
          } catch (error) {
            failPlanning(item, error?.message || "FeedPak metadata inspection failed.");
            continue;
          }
        }
        feedpakReady.push(current);
      }

      if (stopRequestedRef.current) return;
      const plannedPsarcPaths = [...planById.values()].flatMap((plan) => plan.outputs.map((output) => output.path));
      const reservedOutputPaths = reserveBatchOutputPaths(
        feedpakReady,
        outputDir,
        outputLayout,
        batchSourceRoot,
        outputNameFormat,
        outputNameTemplate,
        plannedPsarcPaths
      );
      const feedpakById = new Map(feedpakReady.map((item) => [item.id, item]));
      const conversionReady = conversionPending
        .filter((item) => !planningFailures.has(item.id))
        .map((item) => feedpakById.get(item.id) || item);
      setConversionProgress((current) => ({
        ...current,
        completed: planningFailures.size,
        failed: planningFailures.size,
        phase: "converting"
      }));

      async function convertItem(item) {
        if (stopRequestedRef.current) return;
        const outputPlan = planById.get(item.id) || null;
        const plannedFirst = outputPlan?.outputs?.[0] || null;
        const outputPath = item.sourceType === "feedpak" ? (reservedOutputPaths.get(item.id) || null) : null;
        updateItem(item.id, { status: "converting", warnings: [], error: null, message: null });
        setConversionProgress((current) => ({
          ...current,
          active: [...current.active.filter((entry) => entry.id !== item.id), {
            id: item.id,
            name: plannedFirst?.title || item.preview?.title || item.name,
            artist: plannedFirst?.artist || item.preview?.artist || ""
          }]
        }));
        const payload = {
          inputPath: item.path,
          outputPath,
          outputPlan,
          overwrite,
          ...stemOptions
        };
        if (rs1SongsPsarc && usesSharedRs1SongsAudio(item.path) && !isRs1SongsArchive(item.path)) {
          payload.rs1SongsPsarc = rs1SongsPsarc;
        }
        let failed = false;
        try {
          const result = item.sourceType === "feedpak"
            ? await api.updateFeedpak(payload)
            : await api.convert(payload);
          if (!result.ok) {
            failed = true;
            updateItem(item.id, { status: "failed", warnings: [], error: result.error });
          } else {
            const warnings = Array.isArray(result.warnings) ? result.warnings.filter(Boolean) : [];
            const outputPaths = Array.isArray(result.outputPaths) ? result.outputPaths.filter(Boolean) : [];
            const outputCount = outputPaths.length || (result.outputPath ? 1 : 0);
            const outputFolder = outputPaths.length ? parentDir(outputPaths[0]) : "";
            updateItem(item.id, {
              status: "converted",
              outputPath: result.outputPath || outputPath || plannedFirst?.path || null,
              outputPaths,
              validation: result.validation || null,
              message: outputCount > 1
                ? `Created ${outputCount} FeedPaks${outputFolder ? ` in ${outputFolder}` : ""}.`
                : null,
              warnings,
              error: null
            });
          }
        } catch (error) {
          failed = true;
          updateItem(item.id, { status: "failed", warnings: [], error: error?.message || "Conversion failed." });
        } finally {
          setConversionProgress((current) => ({
            ...current,
            completed: Math.min(current.total, current.completed + 1),
            failed: current.failed + (failed ? 1 : 0),
            active: current.active.filter((entry) => entry.id !== item.id)
          }));
        }
      }

      const linkedItems = conversionReady.filter((item) => usesSharedRs1SongsAudio(item.path));
      const regularItems = conversionReady.filter((item) => !usesSharedRs1SongsAudio(item.path));
      await runConversionQueues({
        linkedItems,
        regularItems,
        workerLimit: effectiveConversionWorkers,
        runItem: convertItem,
        shouldStop: () => stopRequestedRef.current
      });
    } finally {
      const stopped = stopRequestedRef.current;
      isConvertingRef.current = false;
      stopRequestedRef.current = false;
      setIsStopping(false);
      setIsConverting(false);
      setConversionProgress((current) => ({ ...current, active: [], stopped }));
      pumpInspectionQueue();
    }
  }

  async function exportAudioQueue() {
    if (!items.length || isConverting) return;
    const pending = [];
    const pendingPaths = new Set();
    for (const item of itemsRef.current) {
      if (item.status === "converting") continue;
      const key = normalizePathKey(item.path);
      if (pendingPaths.has(key)) continue;
      pendingPaths.add(key);
      pending.push(item);
    }
    if (!pending.length) return;
    isConvertingRef.current = true;
    stopRequestedRef.current = false;
    setIsStopping(false);
    setIsConverting(true);
    setConversionProgress({ total: pending.length, completed: 0, failed: 0, active: [], stopped: false });
    const batchSourceRoot = commonAncestorDir(pending.map((item) => item.path));
    const nameTemplate = outputNameTemplateForFormat(outputNameFormat, outputNameTemplate);
    let index = 0;

    async function exportNext() {
      if (stopRequestedRef.current) return;
      const item = pending[index];
      index += 1;
      if (!item) return;
      updateItem(item.id, { status: "converting", warnings: [], error: null, message: null });
      setConversionProgress((current) => ({
        ...current,
        active: [...current.active.filter((entry) => entry.id !== item.id), { id: item.id, name: itemDisplayTitle(item), artist: itemProgressSubtitle(item) }]
      }));
      let failed = false;
      try {
        const result = await api.exportAudio({
          inputPath: item.path,
          outputPath: outputDir || null,
          overwrite,
          outputLayout,
          sourceRoot: item.sourceRoot || batchSourceRoot,
          nameTemplate
        });
        if (!result.ok) {
          failed = true;
          updateItem(item.id, { status: "failed", warnings: [], error: result.error });
        } else {
          const warnings = Array.isArray(result.warnings) ? result.warnings.filter(Boolean) : [];
          const outputPaths = Array.isArray(result.outputPaths) ? result.outputPaths.filter(Boolean) : [];
          const outputFolder = outputPaths.length ? parentDir(outputPaths[0]) : "";
          updateItem(item.id, {
            status: "converted",
            outputPath: result.outputPath || outputPaths[0] || null,
            outputPaths,
            message: outputPaths.length > 1
              ? `Exported ${outputPaths.length} audio files${outputFolder ? ` in ${outputFolder}` : ""}.`
              : "Exported audio.",
            warnings,
            error: null
          });
        }
      } catch (error) {
        failed = true;
        updateItem(item.id, { status: "failed", warnings: [], error: error?.message || "Audio export failed." });
      } finally {
        setConversionProgress((current) => ({
          ...current,
          completed: Math.min(current.total, current.completed + 1),
          failed: current.failed + (failed ? 1 : 0),
          active: current.active.filter((entry) => entry.id !== item.id)
        }));
      }
      if (stopRequestedRef.current) return;
      await exportNext();
    }

    try {
      const workerCount = Math.min(Math.max(1, effectiveConversionWorkers), pending.length);
      await Promise.all(Array.from({ length: workerCount }, () => exportNext()));
    } finally {
      const stopped = stopRequestedRef.current;
      isConvertingRef.current = false;
      stopRequestedRef.current = false;
      setIsStopping(false);
      setIsConverting(false);
      setConversionProgress((current) => ({ ...current, active: [], stopped }));
      pumpInspectionQueue();
    }
  }

  async function exportAudioItem(item) {
    if (!item || isConverting) return;
    isConvertingRef.current = true;
    stopRequestedRef.current = false;
    setIsStopping(false);
    setIsConverting(true);
    setConversionProgress({
      total: 1,
      completed: 0,
      failed: 0,
      active: [{ id: item.id, name: itemDisplayTitle(item), artist: itemProgressSubtitle(item) }],
      stopped: false
    });
    updateItem(item.id, { status: "converting", warnings: [], error: null, message: null });
    let failed = false;
    try {
      const nameTemplate = outputNameTemplateForFormat(outputNameFormat, outputNameTemplate);
      const result = await api.exportAudio({
        inputPath: item.path,
        outputPath: outputDir || null,
        overwrite,
        outputLayout,
        sourceRoot: item.sourceRoot || parentDir(item.path),
        nameTemplate
      });
      if (!result.ok) {
        failed = true;
        updateItem(item.id, { status: "failed", warnings: [], error: result.error });
      } else {
        const warnings = Array.isArray(result.warnings) ? result.warnings.filter(Boolean) : [];
        const outputPaths = Array.isArray(result.outputPaths) ? result.outputPaths.filter(Boolean) : [];
        updateItem(item.id, {
          status: "converted",
          outputPath: result.outputPath || outputPaths[0] || null,
          outputPaths,
          message: outputPaths.length > 1 ? `Exported ${outputPaths.length} audio files.` : "Exported audio.",
          warnings,
          error: null
        });
      }
    } catch (error) {
      failed = true;
      updateItem(item.id, { status: "failed", warnings: [], error: error?.message || "Audio export failed." });
    } finally {
      isConvertingRef.current = false;
      stopRequestedRef.current = false;
      setIsStopping(false);
      setIsConverting(false);
      setConversionProgress({ total: 1, completed: 1, failed: failed ? 1 : 0, active: [], stopped: false });
      pumpInspectionQueue();
    }
  }

  function stopConversion() {
    stopRequestedRef.current = true;
    setIsStopping(true);
    setConversionProgress((current) => ({ ...current, stopped: true }));
    if (conversionProgress.phase === "planning" && typeof api.cancelPlanning === "function") {
      Promise.resolve(api.cancelPlanning()).catch(() => {});
    }
  }

  async function saveFeedpakMetadata(item, metadata, authors, options = {}) {
    if (!item || item.sourceType !== "feedpak") return { ok: false, error: "Select a FeedPak first." };
    updateItem(item.id, { status: "converting", warnings: [], error: null });
    const overwriteOriginal = options.overwriteOriginal === true;
    const outputPath = overwriteOriginal ? null : editedFeedpakPath(item, outputDir);
    const result = await api.updateFeedpak({
      inputPath: item.path,
      outputPath,
      overwrite: overwriteOriginal,
      metadata,
      authors
    });
    if (!result.ok) {
      updateItem(item.id, { status: "failed", warnings: [], error: result.error });
      return result;
    }
    if (overwriteOriginal) {
      updateItem(item.id, { status: "queued", error: null });
      await inspectItem({ ...item, status: "queued" });
    } else {
      updateItem(item.id, {
        status: "converted",
        outputPath: result.outputPath || outputPath,
        validation: result.validation || null,
        warnings: Array.isArray(result.warnings) ? result.warnings.filter(Boolean) : [],
        error: null
      });
    }
    return result;
  }

  async function replaceFeedpakCover(item, options = {}) {
    if (!item || item.sourceType !== "feedpak") return;
    const coverPath = await api.pickCoverImage({ defaultPath: parentDir(item.path) || undefined });
    if (!coverPath) return;
    updateItem(item.id, { status: "converting", warnings: [], error: null });
    const overwriteOriginal = options.overwriteOriginal === true;
    const outputPath = overwriteOriginal ? null : editedFeedpakPath(item, outputDir);
    const result = await api.updateFeedpak({
      inputPath: item.path,
      outputPath,
      overwrite: overwriteOriginal,
      coverPath
    });
    if (!result.ok) {
      updateItem(item.id, { status: "failed", warnings: [], error: result.error });
      return;
    }
    if (overwriteOriginal) {
      updateItem(item.id, { status: "queued", error: null });
      await inspectItem({ ...item, status: "queued" });
    } else {
      updateItem(item.id, { status: "converted", outputPath: result.outputPath || outputPath, validation: result.validation || null, warnings: Array.isArray(result.warnings) ? result.warnings.filter(Boolean) : [], error: null });
    }
  }

  async function removeFeedpakCover(item, options = {}) {
    if (!item || item.sourceType !== "feedpak") return;
    updateItem(item.id, { status: "converting", warnings: [], error: null });
    const overwriteOriginal = options.overwriteOriginal === true;
    const outputPath = overwriteOriginal ? null : editedFeedpakPath(item, outputDir);
    const result = await api.updateFeedpak({
      inputPath: item.path,
      outputPath,
      overwrite: overwriteOriginal,
      removeCover: true
    });
    if (!result.ok) {
      updateItem(item.id, { status: "failed", warnings: [], error: result.error });
      return;
    }
    if (overwriteOriginal) {
      updateItem(item.id, { status: "queued", error: null });
      await inspectItem({ ...item, status: "queued" });
    } else {
      updateItem(item.id, { status: "converted", outputPath: result.outputPath || outputPath, validation: result.validation || null, warnings: Array.isArray(result.warnings) ? result.warnings.filter(Boolean) : [], error: null });
    }
  }

  async function replaceFeedpakStem(item, stemId, options = {}) {
    if (!item || item.sourceType !== "feedpak") return { ok: false, error: "Select a FeedPak first." };
    const audioPath = await api.pickAudioStem({ defaultPath: parentDir(item.path) || undefined });
    if (!audioPath) return { ok: false, cancelled: true };
    return updateFeedpakStems(item, [{ id: stemId, file: audioPath }], [], options);
  }

  async function removeFeedpakStem(item, stemId, options = {}) {
    if (!item || item.sourceType !== "feedpak") return { ok: false, error: "Select a FeedPak first." };
    return updateFeedpakStems(item, [], [stemId], options);
  }

  async function updateFeedpakStems(item, stemUpdates, removeStems, options = {}) {
    updateItem(item.id, { status: "converting", warnings: [], error: null });
    const overwriteOriginal = options.overwriteOriginal === true;
    const outputPath = overwriteOriginal ? null : editedFeedpakPath(item, outputDir);
    const result = await api.updateFeedpak({
      inputPath: item.path,
      outputPath,
      overwrite: overwriteOriginal,
      stemUpdates,
      removeStems
    });
    if (!result.ok) {
      updateItem(item.id, { status: "failed", warnings: [], error: result.error });
      return result;
    }
    if (overwriteOriginal) {
      updateItem(item.id, { status: "queued", error: null });
      await inspectItem({ ...item, status: "queued" });
    } else {
      updateItem(item.id, { status: "converted", outputPath: result.outputPath || outputPath, validation: result.validation || null, warnings: Array.isArray(result.warnings) ? result.warnings.filter(Boolean) : [], error: null });
    }
    return result;
  }

  async function reprocessFeedpakStems(item, options = {}) {
    if (!item || item.sourceType !== "feedpak") return { ok: false, error: "Select a FeedPak first." };
    if (!separateStems) return { ok: false, error: "Enable Separate stems in Settings first." };
    updateItem(item.id, { status: "converting", warnings: [], error: null });
    const overwriteOriginal = options.overwriteOriginal === true;
    const outputPath = overwriteOriginal ? null : editedFeedpakPath(item, outputDir);
    const result = await api.updateFeedpak({
      inputPath: item.path,
      outputPath,
      overwrite: overwriteOriginal,
      separateStems: true,
      demucsUrl,
      demucsApiKey,
      demucsModel,
      demucsStems
    });
    if (!result.ok) {
      updateItem(item.id, { status: "failed", warnings: [], error: result.error });
      return result;
    }
    if (overwriteOriginal) {
      updateItem(item.id, { status: "queued", error: null });
      await inspectItem({ ...item, status: "queued" });
    } else {
      updateItem(item.id, { status: "converted", outputPath: result.outputPath || outputPath, validation: result.validation || null, warnings: Array.isArray(result.warnings) ? result.warnings.filter(Boolean) : [], error: null });
    }
    return result;
  }

  async function reprocessLoadedFeedpakStems() {
    if (!feedpakItems.length) return { ok: false, error: "Add FeedPaks first." };
    if (!separateStems) return { ok: false, error: "Enable Separate stems in Settings first." };
    let failed = 0;
    for (const entry of feedpakItems) {
      const result = await reprocessFeedpakStems(entry, { overwriteOriginal: overwrite });
      if (!result?.ok) failed += 1;
    }
    return { ok: failed === 0, total: feedpakItems.length, failed };
  }

  async function organizeLoadedFeedpaksByArtist() {
    if (!feedpakItems.length) return { ok: false, error: "Add FeedPaks first." };
    let targetDir = outputDir;
    if (!targetDir) {
      targetDir = await api.pickOutput({ defaultPath: lastSourcePath || undefined });
      if (targetDir) setOutputDir(targetDir);
    }
    if (!targetDir) return { ok: false, cancelled: true };
    const result = await api.organizeFeedpaks({
      outputDir: targetDir,
      overwrite,
      items: feedpakItems.map((entry) => ({
        inputPath: entry.path,
        artist: entry.preview?.artist || "Unknown Artist"
      }))
    });
    if (result?.results?.length) {
      for (const row of result.results) {
        const match = feedpakItems.find((entry) => normalizePathKey(entry.path) === normalizePathKey(row.inputPath));
        if (!match) continue;
        updateItem(match.id, row.ok
          ? { status: "converted", outputPath: row.outputPath, error: null }
          : { status: "failed", error: row.error || "Organize failed." });
      }
    }
    return result;
  }

  function onDrop(event) {
    event.preventDefault();
  }

  const viewTitle = {
    songsterr: "From Songsterr", stems: "Stem splitting", settings: "Settings",
    feedpak: "Library & editor", workspace: "Convertor"
  }[activeView];

  return (
    <div className="app" onDragOver={(event) => event.preventDefault()} onDrop={onDrop}>
      {conversionRequest && <ConversionDialog request={conversionRequest} finish={finishConversionChoice} setup={() => {
        const ready = conversionRequest.ready;
        finishConversionChoice(null);
        if (ready) { setSettingsSection("conversion"); setActiveView("settings"); }
        else { setSeparateStems(true); setActiveView("stems"); }
      }} />}
      <aside className="app-sidebar">
        <div className="brand">
          <img className="brand-logo" src={feedForgeLogo} alt="" />
          <div>
            <strong>FeedForge</strong>{appVersion && <span className="version-badge">v{appVersion}</span>}
          </div>
        </div>
        <nav className="side-nav" aria-label="FeedForge sections">
          <button className={activeView === "home" ? "active" : ""} onClick={() => setActiveView("home")}><FolderOpen size={18}/><span>Home</span></button>
          <span className="nav-group-label">Create FeedPak</span>
          <button className={activeView === "workspace" ? "active" : ""} onClick={() => setActiveView("workspace")}>
            <Guitar size={18} />
            <span>Convertor</span>
          </button>
          <button className={activeView === "songsterr" ? "active" : ""} onClick={() => setActiveView("songsterr")}><FileMusic size={18}/><span>From Songsterr</span></button>
          <button className={activeView === "stems" ? "active" : ""} onClick={() => setActiveView("stems")}>
            <Server size={18} />
            <span>Tools · stems</span>
          </button>
          <button className={activeView === "feedpak" ? "active" : ""} onClick={() => setActiveView("feedpak")}>
            <FileMusic size={18} />
            <span>Library & editor</span>
          </button>
          <button className={activeView === "settings" ? "active" : ""} onClick={() => { setActiveView("settings"); if (settingsSection === "stems") setSettingsSection("conversion"); }}>
            <SlidersHorizontal size={18} />
            <span>Settings</span>
          </button>
        </nav>
        <div className="sidebar-links">
          <button className="support-link sidebar-support website" onClick={() => api.openWebsite()} title="Open FeedForge Hub">
            <Globe size={17} />
            Website
          </button>
          <button className="support-link sidebar-support discord" onClick={() => api.openDiscord()} title="Join the FeedForge Discord">
            <DiscordIcon size={17} />
            Discord
          </button>
          <button className="support-link sidebar-support kofi" onClick={() => api.openSupport()} title="Support FeedForge on Ko-fi">
            <Coffee size={17} />
            Support us on Ko-fi
          </button>
        </div>
      </aside>
      <main className="workspace" ref={workspaceRef}>
        {activeView !== "home" && <header className="topbar">
          <div className="title-group">
            <h1>{viewTitle}</h1>
          </div>
          <div className="header-actions">
            <button
              className={`stem-header-status ${headerStemStatusClass(separateStems, stemServerStatus, isStartingStemServer, stemServerMatchesSelectedConfig)}`}
              onClick={() => {
                setActiveView("stems");
              }}
              title="Open stem splitting settings"
            >
              <Server size={16} />
              <span>
                <strong>Stem server</strong>
                <small>{headerStemStatusLabel(separateStems, stemServerStatus, isStartingStemServer, stemServerMatchesSelectedConfig)}</small>
              </span>
            </button>
            {activeView === "workspace" && <button className="primary" onClick={convertQueue} disabled={!workspaceItems.length || isConverting}>
              {isConverting ? <RotateCw className="spin" size={18} /> : <Download size={18} />}
              Convert queue{isConverting ? ` (${effectiveConversionWorkers}x)` : ""}
            </button>}
            {isConverting && (
              <button className="danger" onClick={stopConversion} disabled={isStopping}>
                <Square size={17} />
                {isStopping ? "Stopping" : "Stop after current"}
              </button>
            )}
          </div>
        </header>}

        {["workspace", "feedpak"].includes(activeView) && <section className="toolbar">
          <div className="search">
            <Search size={17} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search title, artist, or album" />
          </div>
          <button onClick={chooseFiles}><Plus size={17} /> Add files</button>
          <button onClick={() => chooseFolder()}><FolderOpen size={17} /> Add folder</button>
          {activeView === "feedpak" && <button onClick={() => {setActiveView("settings"); setSettingsSection("diagnostics");}}>Audit library</button>}
        </section>}

        {updateInfo?.updateAvailable && (
          <section className="update-banner">
            <div>
              <strong>FeedForge {updateInfo.latestVersion} is available</strong>
              <span>You are using {updateInfo.currentVersion}. Download the latest release from GitHub.</span>
            </div>
            <button onClick={() => api.openLatestRelease(updateInfo.releaseUrl)}>
              <ExternalLink size={16} />
              Open GitHub
            </button>
          </section>
        )}

        {conversionProgress.total > 0 && (
          <ConversionProgress progress={conversionProgress} isConverting={isConverting} />
        )}

        <div hidden={activeView !== "songsterr"}>
          <SongsterrWorkspace requestConversion={requestConversion} outputDir={outputDir} setOutputDir={setOutputDir} onCreated={paths => addFiles(paths, null, false)} />
        </div>
        {activeView === "home" ? <Home navigate={setActiveView} chooseFiles={chooseFiles} chooseFolder={() => chooseFolder("feedpak")} items={items} selectItem={item => {setSelectedId(item.id); setActiveView(item.sourceType === "feedpak" ? "feedpak" : "workspace");}} /> : activeView === "songsterr" ? null : activeView === "settings" || activeView === "stems" ? (
          <section className={`settings-page ${activeView === "stems" ? "settings-page-full" : ""}`}>
            {activeView === "settings" && (
              <div className="settings-nav" aria-label="Settings sections">
                <button className={settingsSection === "conversion" ? "active" : ""} onClick={() => setSettingsSection("conversion")}>Conversion</button>
                <button className={settingsSection === "diagnostics" ? "active" : ""} onClick={() => setSettingsSection("diagnostics")}>Diagnostics</button>
              </div>
            )}

            {activeView === "settings" && settingsSection === "conversion" && (
            <div className="settings-card">
              <div className="settings-card-head">
                <div>
                  <h2>Conversion</h2>

                </div>
              </div>
              <div className="settings-grid">
                <button className="path-action wide" onClick={chooseOutput} title={outputDir || "Use source folders for output"}>
                  <FolderOpen size={17} />
                  <span>Output</span>
                  <b>{outputDir ? outputDir : "Source folder"}</b>
                </button>
                <label className="select-control">
                  Workers
                  <select value={conversionWorkers} onChange={(event) => setConversionWorkers(normalizeAutoNumberSetting(event.target.value, DEFAULT_CONVERSION_WORKERS))} disabled={isConverting}>
                    <option value={AUTO_SETTING}>{`Auto (${effectiveConversionWorkers})`}</option>
                    {[1, 2, 3, 4, 5, 6].map((value) => <option key={value} value={value}>{value}</option>)}
                  </select>
                </label>
                <label className="select-control output-layout-control">
                  Output layout
                  <select value={outputLayout} onChange={(event) => setOutputLayout(event.target.value)} disabled={isConverting}>
                    <option value="flat">Single folder</option>
                    <option value="preserve">Preserve source folders</option>
                    <option value="artist">Artist folders</option>
                  </select>
                </label>
                <label className="select-control">
                  File names
                  <select value={outputNameFormat} onChange={(event) => setOutputNameFormat(event.target.value)} disabled={isConverting}>
                    <option value="source">Source filename</option>
                    <option value="artist-title">Artist - Song</option>
                    <option value="title-artist">Song - Artist</option>
                    <option value="artist-album-title">Artist - Album - Song</option>
                    <option value="artist-title-parts">Artist - Song - Parts</option>
                    <option value="custom">Custom template</option>
                  </select>
                </label>
                {outputNameFormat === "custom" && (
                  <label className="text-control output-name-template">
                    Naming template
                    <input
                      value={outputNameTemplate}
                      onChange={(event) => setOutputNameTemplate(event.target.value)}
                      placeholder="{artist} - {title}"
                      disabled={isConverting}
                    />
                    <span>Available: {"{artist}"}, {"{title}"}, {"{album}"}, {"{year}"}, {"{source}"}, {"{parts}"}</span>
                  </label>
                )}
                <div className="option-grid">
                  <label className="toggle"><input type="checkbox" checked={overwrite} onChange={(event) => setOverwrite(event.target.checked)} /> Overwrite existing output</label>
                  <label className="toggle"><input type="checkbox" checked={separateStems} onChange={(event) => setSeparateStems(event.target.checked)} disabled={isConverting} /> Separate stems</label>
                </div>
              </div>
            </div>
            )}

            {activeView === "stems" && (
              <div className="settings-card">
                <div className="settings-card-head">
                  <div>
                    <h2>Configuration</h2>

                  </div>
                  <span className={`server-badge ${stemServerBadge(stemServerStatus, isStartingStemServer, stemServerMatchesSelectedConfig).toLowerCase().replace(/\s+/g, "-")}`}>{stemServerBadge(stemServerStatus, isStartingStemServer, stemServerMatchesSelectedConfig)}</span>
                </div>
                {!separateStems ? (
                  <div className="settings-empty">
                    <strong>Stem splitting is disabled</strong>
                    <span>Enable stems to configure local or remote splitting.</span>
                    <button onClick={() => setSeparateStems(true)}>Enable stems</button>
                  </div>
                ) : (
                <div className="stem-settings">
                  <div className="stem-summary">
                    <div>
                      <strong>{stemServerReadyForSelection ? "Ready" : "Setup managed by FeedForge"}</strong>
                      <span>{stemServerReadyForSelection ? stemServerDetail(stemServerStatus, demucsModel, selectedModel) : "Local splitting runs on this PC. A custom server URL runs splitting on that server."}</span>
                    </div>
                  </div>
                  <div className={`stem-prereq ${pythonInfo?.ok ? "ready" : pythonInfo?.found === false ? "missing" : ""}`}>
                    <div>
                      <strong>{pythonPrereqTitle(pythonInfo, isCheckingPython)}</strong>
                      <span>{pythonInfo?.message || "Local splitting needs Python 3.11+. FeedForge handles the stem environment after Python is available."}</span>
                      {pythonInfo?.executable && <em>{pythonInfo.executable}</em>}
                    </div>
                    <div className="prereq-actions">
                      <button className="ghost" onClick={recheckPython} disabled={isCheckingPython}>{isCheckingPython ? "Checking" : "Recheck"}</button>
                      {pythonInfo?.ok === false && <button onClick={() => api.openPythonDownload()}>Get Python</button>}
                    </div>
                  </div>
                  <label>
                    Python
                    <div className="path-row">
                      <input value={pythonPath} onChange={(event) => setPythonPath(event.target.value)} placeholder="Auto-detect or choose Python" disabled={isConverting || stemServerStatus.processRunning || stemServerBusy} />
                      <button onClick={choosePythonExecutable} disabled={isConverting || stemServerStatus.processRunning || stemServerBusy}>
                        <FolderOpen size={18} />
                        Browse
                      </button>
                    </div>
                  </label>
                  <label>
                    Model
                    <select value={demucsModel} onChange={(event) => setDemucsModel(event.target.value)} disabled={isConverting || stemServerBusy}>
                      {(demucsModels.length ? demucsModels : [{ id: "htdemucs_6s", name: "HTDemucs 6-source", size: "approx. 270 MB", description: "Best FeedForge default." }]).map((model) => (
                        <option key={model.id} value={model.id}>{model.name} ({model.size}) - {modelStatusLabel(model)}</option>
                      ))}
                    </select>
                  </label>
                  <div className="demucs-model-note">
                    <strong>{modelStatusLabel(selectedModel)} - {selectedModel?.size || "Model size varies"}</strong>
                    <span>
                      {selectedModel?.remoteOnly
                        ? "This model is requested from the configured remote FeedBack Demucs server during conversion."
                        : selectedModel?.installed
                          ? "Cached locally."
                          : "Downloads on first local start."}
                    </span>
                    <em>{selectedModel?.description || "Selected model."}</em>
                    {!selectedModel?.installed && !selectedModel?.remoteOnly && (
                      <button onClick={startLocalStemServer} disabled={isConverting || stemServerBusy || pythonInfo?.ok === false}>
                        {stemServerBusy ? <RotateCw className="spin" size={16} /> : <Download size={16} />}
                        Download/start this model
                      </button>
                    )}
                  </div>
                  <StemSetupChecklist
                    pythonInfo={pythonInfo}
                    setup={demucsSetup}
                    selectedModel={selectedModel}
                    status={stemServerStatus}
                    matchesSelection={stemServerMatchesSelectedConfig}
                  />
                  <div className="stem-picker">
                    <div className="stem-picker-head">
                      <div>
                        <strong>Stems to generate</strong>
                        <span>{stemSelectionSummary(demucsStems)}</span>
                      </div>
                      <div>
                        <button className="ghost" onClick={() => setDemucsStems(DEMUCS_STEM_OPTIONS.map((stem) => stem.id))} disabled={isConverting}>All</button>
                        <button className="ghost" onClick={() => setDemucsStems(DEFAULT_DEMUCS_STEMS)} disabled={isConverting}>Default</button>
                      </div>
                    </div>
                    <div className="stem-choice-grid" role="group" aria-label="Stems to generate">
                      {DEMUCS_STEM_OPTIONS.map((stem) => (
                        <label key={stem.id} className={`stem-choice ${demucsStems.includes(stem.id) ? "active" : ""}`}>
                          <input
                            type="checkbox"
                            checked={demucsStems.includes(stem.id)}
                            onChange={() => setDemucsStems((current) => toggleStemSelection(current, stem.id))}
                            disabled={isConverting}
                          />
                          <span>{stem.label}</span>
                        </label>
                      ))}
                    </div>
                    {stemSelectionWarning(demucsStems) && (
                      <p className="stem-selection-warning">{stemSelectionWarning(demucsStems)}</p>
                    )}
                  </div>
                  <label>
                    Processing device
                    <select value={demucsDevice} onChange={(event) => setDemucsDevice(event.target.value)} disabled={isConverting || stemServerBusy}>
                      {demucsDevices.map((device) => (
                        <option key={device.id} value={device.id} disabled={device.available === false}>
                          {deviceLabel(device)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="demucs-device-note">
                    <strong>{stemServerReadyForSelection ? `Active: ${resolvedDeviceLabel(stemServerStatus)}` : `Selected: ${selectedDevice?.name || demucsDevice}`}</strong>
                    <span>{deviceHelpText(selectedDevice, stemServerStatus)}</span>
                  </div>
                  <label>
                    Stem jobs
                    <select value={demucsStemJobs} onChange={(event) => setDemucsStemJobs(normalizeAutoNumberSetting(event.target.value, DEFAULT_DEMUCS_STEM_JOBS))} disabled={isConverting || stemServerBusy}>
                      <option value={AUTO_SETTING}>{`Auto (${effectiveDemucsStemJobs})`}</option>
                      {[1, 2, 3, 4].map((value) => <option key={value} value={value}>{value}</option>)}
                    </select>
                  </label>
                  <div className="demucs-device-note">
                    <strong>{stemServerReadyForSelection ? `Server allows ${stemServerStatus.concurrency || 1} stem job${Number(stemServerStatus.concurrency || 1) === 1 ? "" : "s"}` : stemJobSelectionLabel(demucsStemJobs, effectiveDemucsStemJobs)}</strong>
                    <span>{stemJobHelpText(effectiveDemucsStemJobs, stemServerStatus, demucsStemJobs === AUTO_SETTING)}</span>
                  </div>
                  <div className="demucs-install-row">
                    <label>
                      Install folder
                      <input value={demucsInstallDir} onChange={(event) => setDemucsInstallDir(event.target.value)} placeholder="Install folder" disabled={isConverting || stemServerBusy} />
                    </label>
                    <button onClick={chooseDemucsInstallDir} disabled={isConverting || stemServerBusy}>
                      <FolderOpen size={17} />
                      Browse
                    </button>
                  </div>
                  <label>
                    Demucs server
                    <input value={demucsUrl} onChange={(event) => setDemucsUrl(event.target.value)} placeholder="Local default or remote server URL" disabled={isConverting} />
                  </label>
                  <label>
                    API key
                    <input value={demucsApiKey} onChange={(event) => setDemucsApiKey(event.target.value)} placeholder="Optional" type="password" disabled={isConverting} />
                  </label>
                  <div className="local-stem-server">
                    <div className={`server-state ${stemServerReadyForSelection ? "ready" : stemServerStatus.healthy ? "changed" : stemServerBusy ? "starting" : stemServerStatus.phase === "error" ? "error" : ""}`}>
                      <Server size={17} />
                      <div>
                        <strong>{stemServerTitle(stemServerStatus, stemServerBusy, stemServerMatchesSelectedConfig)}</strong>
                        <span>{stemServerDetail(stemServerStatus, demucsModel, selectedModel, stemServerMatchesSelectedConfig)}</span>
                      </div>
                    </div>
                    <div className="server-actions">
                      {!stemServerReadyForSelection && !selectedModel?.remoteOnly && (
                        <button onClick={startLocalStemServer} disabled={isConverting || stemServerBusy || pythonInfo?.ok === false}>
                          {stemServerBusy ? <RotateCw className="spin" size={17} /> : <Download size={17} />}
                          {stemServerActionText(stemServerStatus, stemServerBusy, selectedModel)}
                        </button>
                      )}
                      {stemServerStatus.portBlocked && !stemServerBusy && (
                        <button className="danger" onClick={freeStemServerPort} disabled={isConverting || isFreeingStemPort}>
                          {isFreeingStemPort ? <RotateCw className="spin" size={17} /> : <XCircle size={17} />}
                          Free port 7865
                        </button>
                      )}
                      {(stemServerStatus.processRunning || stemServerBusy) && (
                        <button className="ghost" onClick={stopLocalStemServer} disabled={isConverting}>
                          <Power size={17} />
                          Stop
                        </button>
                      )}
                    </div>
                  </div>
                  {(stemServerBusy || stemServerStatus.phase === "error" || (stemServerStatus.log || []).length > 0) && (
                    <StemSetupProgress
                      status={stemServerStatus}
                      busy={stemServerBusy}
                      debugLogInfo={debugLogInfo}
                    />
                  )}
                </div>
                )}
              </div>
            )}

            {activeView === "settings" && settingsSection === "diagnostics" && (
              <div className="settings-card">
                <div className="settings-card-head">
                  <div>
                    <h2>Diagnostics</h2>

                  </div>
                </div>
                <LibraryAuditPanel
                  folder={auditFolder}
                  criteria={auditCriteria}
                  report={auditReport}
                  busy={isAuditingLibrary}
                  onChooseFolder={chooseAuditFolder}
                  onRun={runLibraryAudit}
                  onChangeCriterion={updateAuditCriterion}
                />
                <div className="diagnostics-panel standalone">
                  <div className="diagnostics-head">
                    <div>
                      <strong>Debug log</strong>
                      <span>{debugLogInfo?.path || "Debug log path will appear after app startup."}</span>
                    </div>
                    <div>
                      <button className="ghost" onClick={() => api.openDebugLog()} disabled={!debugLogInfo?.path}>Open log</button>
                      <button className="ghost" onClick={() => api.openDebugLogFolder()} disabled={!debugLogInfo?.folder}>Open folder</button>
                    </div>
                  </div>
                  <div className="stem-log">
                    {(stemServerStatus.log || []).length === 0 ? (
                      <span>No live stem server output yet. Open Stem splitting and start the local server to see setup progress here.</span>
                    ) : (
                      stemServerStatus.log.slice(-18).map((line, index) => <code key={`${line}-${index}`}>{line}</code>)
                    )}
                  </div>
                </div>
              </div>
            )}
          </section>
        ) : activeView === "feedpak" ? (
          <FeedPakTools
            item={feedpakSelected}
            feedpakItems={feedpakItems.filter(item => `${item.preview?.title || ""} ${item.preview?.artist || ""} ${item.preview?.album || ""} ${item.name}`.toLowerCase().includes(query.toLowerCase()))}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onAddFiles={chooseFiles}
            onSaveFeedpakMetadata={saveFeedpakMetadata}
            onReplaceFeedpakCover={replaceFeedpakCover}
            onRemoveFeedpakCover={removeFeedpakCover}
            onReplaceFeedpakStem={replaceFeedpakStem}
            onRemoveFeedpakStem={removeFeedpakStem}
            onReprocessFeedpakStems={reprocessFeedpakStems}
            onBatchReprocessFeedpakStems={reprocessLoadedFeedpakStems}
            onOrganizeByArtist={organizeLoadedFeedpaksByArtist}
            onChooseOutput={chooseOutput}
            onRemoveItem={removeItem}
            outputDir={outputDir}
            overwrite={overwrite}
            separateStems={separateStems}
            demucsStems={demucsStems}
          />
        ) : (
          <>
            <section className="filter-bar">
              <div className="filter-pills" aria-label="Queue status">
                <button className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>All</button>
                <button className={filter === "ready" ? "active" : ""} onClick={() => setFilter("ready")}>Ready</button>
                <button className={filter === "issues" ? "active" : ""} onClick={() => setFilter("issues")}>Issues</button>
                <button className={filter === "converted" ? "active" : ""} onClick={() => setFilter("converted")}>Converted</button>
              </div>
              <FilterSelect label="Artist" value={artistFilter} onChange={setArtistFilter} options={filterOptions.artists} />
              <FilterSelect label="Album" value={albumFilter} onChange={setAlbumFilter} options={filterOptions.albums} />
              <FilterSelect label="Tuning" value={tuningFilter} onChange={setTuningFilter} options={filterOptions.tunings} />
              {(artistFilter !== "all" || albumFilter !== "all" || tuningFilter !== "all" || filter !== "all" || query) && (
                <button className="ghost" onClick={() => {
                  setQuery("");
                  setFilter("all");
                  setArtistFilter("all");
                  setAlbumFilter("all");
                  setTuningFilter("all");
                }}>
                  Clear filters
                </button>
              )}
            </section>

            <section className="stats">
              <Metric label="Imported" value={stats.total} />
              <Metric label="Ready" value={stats.ready} tone="blue" />
              <Metric label="Converted" value={stats.converted} tone="green" />
              <Metric label="Issues" value={stats.failed} tone="red" />
            </section>

            <section className="content-grid">
              <div className="left-column">
                <DropZone onClick={chooseFiles} />
                <Queue
                  items={filtered}
                  selectedId={workspaceSelected?.id}
                  onSelect={setSelectedId}
                  onRemove={removeItem}
                  onExportAudio={exportAudioQueue}
                  onExportAudioItem={exportAudioItem}
                  canRemove={!isConverting}
                  canExportAudio={items.length > 0 && !isConverting}
                />
              </div>
              <Inspector
                item={workspaceSelected}
                onSaveFeedpakMetadata={saveFeedpakMetadata}
                onReplaceFeedpakCover={replaceFeedpakCover}
                onRemoveFeedpakCover={removeFeedpakCover}
              />
            </section>
          </>
        )}
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
