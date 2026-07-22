import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertTriangle,
  Check,
  Coffee,
  Download,
  ExternalLink,
  FileMusic,
  FolderOpen,
  Globe,
  Guitar,
  ImageIcon,
  Info,
  Play,
  Plus,
  Power,
  RotateCw,
  Search,
  Server,
  Square,
  UploadCloud,
  XCircle
} from "lucide-react";
import "./styles.css";

const api = window.feedbackConverter;
const INSPECTION_WORKERS = 2;
const QUEUE_RENDER_LIMIT = 500;
const AUTO_SETTING = "auto";
const DEFAULT_CONVERSION_WORKERS = AUTO_SETTING;
const DEFAULT_DEMUCS_STEM_JOBS = AUTO_SETTING;
const SETTINGS_KEY = "feedforge:desktop-settings";
const DEFAULT_DEMUCS_STEMS = ["guitar", "bass", "drums", "vocals", "other"];
const DEMUCS_STEM_OPTIONS = [
  { id: "guitar", label: "Guitar" },
  { id: "bass", label: "Bass" },
  { id: "drums", label: "Drums" },
  { id: "vocals", label: "Vocals" },
  { id: "piano", label: "Piano" },
  { id: "other", label: "Other" }
];
const DEFAULT_AUDIT_CRITERIA = {
  requireSpecValidation: true,
  requireCover: true,
  requireFullStem: true,
  requireSplitStems: false,
  requireBass: false,
  requireGuitar: false,
  requireLyrics: false,
  requireAuthors: false,
  requireTones: false,
  checkDuplicates: false
};
const AUDIT_CRITERIA_OPTIONS = [
  { key: "requireSpecValidation", label: "Spec valid" },
  { key: "requireCover", label: "Cover" },
  { key: "requireFullStem", label: "Full mix" },
  { key: "requireSplitStems", label: "Split stems" },
  { key: "requireBass", label: "Bass" },
  { key: "requireGuitar", label: "Guitar" },
  { key: "requireLyrics", label: "Lyrics" },
  { key: "requireAuthors", label: "Credits" },
  { key: "requireTones", label: "Tones" },
  { key: "checkDuplicates", label: "Duplicates" }
];

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
  const [bStandardTo7String, setBStandardTo7String] = useState(() => initialSettingsRef.current.bStandardTo7String === true);
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
  const [activeView, setActiveView] = useState("workspace");
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
    writeSettings({ outputDir, outputLayout, outputNameFormat, outputNameTemplate, lastSourcePath, bStandardTo7String, separateStems, conversionWorkers, demucsUrl, demucsInstallDir, pythonPath, demucsModel, demucsDevice, demucsStemJobs, demucsStems, auditFolder, auditCriteria, performanceSettingsVersion: 2 });
  }, [outputDir, outputLayout, outputNameFormat, outputNameTemplate, lastSourcePath, bStandardTo7String, separateStems, conversionWorkers, demucsUrl, demucsInstallDir, pythonPath, demucsModel, demucsDevice, demucsStemJobs, demucsStems, auditFolder, auditCriteria]);

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
    if (activeView !== "settings" || settingsSection !== "stems" || !separateStems) return undefined;
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
  }, [activeView, settingsSection, separateStems, demucsInstallDir, pythonPath, demucsModel, isStartingStemServer, stemServerStatus.processRunning, stemServerStatus.starting, stemServerStatus.phase]);

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
    const haystack = `${item.preview?.title || item.name} ${item.preview?.artist || ""} ${item.preview?.album || ""}`.toLowerCase();
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

  async function addFiles(paths, sourceRoot = null) {
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
        error: null
    }));
    if (!incoming.length) return;
    rememberSourcePath(incoming[0].path);
    const nextItems = [...itemsRef.current, ...incoming];
    itemsRef.current = nextItems;
    setItems(nextItems);
    if (!selectedId) setSelectedId(incoming[0].id);
    if (incoming.every((item) => item.sourceType === "feedpak")) {
      setActiveView("feedpak");
    }
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
        return { ...current, status: "failed", error: result.error };
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
        error: null
      };
    });
  }

  async function chooseFiles() {
    const paths = await api.pickPsarc({ defaultPath: lastSourcePath || outputDir || undefined });
    rememberSourcePath(paths[0]);
    addFiles(paths);
  }

  async function chooseFolder() {
    if (api.pickFolderWithRoot) {
      const result = await api.pickFolderWithRoot({ defaultPath: lastSourcePath || outputDir || undefined });
      rememberSourcePath(result.folder || result.files?.[0]);
      addFiles(result.files || [], result.folder || null);
      return;
    }
    const paths = await api.pickFolder({ defaultPath: lastSourcePath || outputDir || undefined });
    rememberSourcePath(paths[0]);
    addFiles(paths);
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
    const selected = await api.pickPythonExecutable({ defaultPath: pythonPath || "C:\\Program Files\\Python313\\python.exe" });
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
    if (!items.length || isConverting) return;
    const pending = [];
    const pendingPaths = new Set();
    for (const item of itemsRef.current) {
      if (item.status === "converted" || item.status === "converting") continue;
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
    const stopManagedStemServerAfterQueue = separateStems && stemServerStatus.processRunning;
    const batchSourceRoot = commonAncestorDir(pending.map((item) => item.path));
    const reservedOutputPaths = reserveBatchOutputPaths(pending, outputDir, outputLayout, batchSourceRoot, outputNameFormat, outputNameTemplate);
    let index = 0;

    async function convertNext() {
      if (stopRequestedRef.current) return;
      const item = pending[index];
      index += 1;
      if (!item) return;
      updateItem(item.id, { status: "converting", error: null, message: null });
      setConversionProgress((current) => ({
        ...current,
        active: [...current.active.filter((entry) => entry.id !== item.id), { id: item.id, name: item.preview?.title || item.name, artist: item.preview?.artist || "" }]
      }));
      const outputPath = reservedOutputPaths.get(item.id) || null;
      const payload = {
        inputPath: item.path,
        outputPath,
        overwrite,
        separateStems,
        demucsUrl: demucsUrl.trim(),
        demucsApiKey: demucsApiKey.trim(),
        demucsModel,
        demucsStems
      };
      let failed = false;
      try {
        const result = item.sourceType === "feedpak"
          ? await api.updateFeedpak(payload)
          : await api.convert({ ...payload, bStandardTo7String });
        if (!result.ok) {
          failed = true;
          updateItem(item.id, { status: "failed", error: result.error });
        } else {
          const warnings = Array.isArray(result.warnings) ? result.warnings.filter(Boolean) : [];
          const outputPaths = Array.isArray(result.outputPaths) ? result.outputPaths.filter(Boolean) : [];
          const outputCount = outputPaths.length || (result.outputPath ? 1 : 0);
          const outputFolder = outputPaths.length ? parentDir(outputPaths[0]) : "";
          updateItem(item.id, {
            status: "converted",
            outputPath: result.outputPath || outputPath,
            outputPaths,
            validation: result.validation || null,
            message: outputCount > 1
              ? `Created ${outputCount} FeedPaks${outputFolder ? ` in ${outputFolder}` : ""}.`
              : null,
            error: warnings.length ? warnings.join("\n") : null
          });
        }
      } catch (error) {
        failed = true;
        updateItem(item.id, { status: "failed", error: error?.message || "Conversion failed." });
      } finally {
        setConversionProgress((current) => ({
          ...current,
          completed: Math.min(current.total, current.completed + 1),
          failed: current.failed + (failed ? 1 : 0),
          active: current.active.filter((entry) => entry.id !== item.id)
        }));
      }
      if (stopRequestedRef.current) return;
      await convertNext();
    }

    try {
      const workerCount = Math.min(Math.max(1, effectiveConversionWorkers), pending.length);
      await Promise.all(Array.from({ length: workerCount }, () => convertNext()));
    } finally {
      const stopped = stopRequestedRef.current;
      isConvertingRef.current = false;
      stopRequestedRef.current = false;
      setIsStopping(false);
      setIsConverting(false);
      setConversionProgress((current) => ({ ...current, active: [], stopped }));
      if (stopManagedStemServerAfterQueue) {
        stopLocalStemServer();
      }
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
      updateItem(item.id, { status: "converting", error: null, message: null });
      setConversionProgress((current) => ({
        ...current,
        active: [...current.active.filter((entry) => entry.id !== item.id), { id: item.id, name: item.preview?.title || item.name, artist: item.preview?.artist || "" }]
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
          updateItem(item.id, { status: "failed", error: result.error });
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
            error: warnings.length ? warnings.join("\n") : null
          });
        }
      } catch (error) {
        failed = true;
        updateItem(item.id, { status: "failed", error: error?.message || "Audio export failed." });
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
      active: [{ id: item.id, name: item.preview?.title || item.name, artist: item.preview?.artist || "" }],
      stopped: false
    });
    updateItem(item.id, { status: "converting", error: null, message: null });
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
        updateItem(item.id, { status: "failed", error: result.error });
      } else {
        const warnings = Array.isArray(result.warnings) ? result.warnings.filter(Boolean) : [];
        const outputPaths = Array.isArray(result.outputPaths) ? result.outputPaths.filter(Boolean) : [];
        updateItem(item.id, {
          status: "converted",
          outputPath: result.outputPath || outputPaths[0] || null,
          outputPaths,
          message: outputPaths.length > 1 ? `Exported ${outputPaths.length} audio files.` : "Exported audio.",
          error: warnings.length ? warnings.join("\n") : null
        });
      }
    } catch (error) {
      failed = true;
      updateItem(item.id, { status: "failed", error: error?.message || "Audio export failed." });
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
  }

  async function saveFeedpakMetadata(item, metadata, authors, options = {}) {
    if (!item || item.sourceType !== "feedpak") return { ok: false, error: "Select a FeedPak first." };
    updateItem(item.id, { status: "converting", error: null });
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
      updateItem(item.id, { status: "failed", error: result.error });
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
        error: null
      });
    }
    return result;
  }

  async function replaceFeedpakCover(item, options = {}) {
    if (!item || item.sourceType !== "feedpak") return;
    const coverPath = await api.pickCoverImage({ defaultPath: parentDir(item.path) || undefined });
    if (!coverPath) return;
    updateItem(item.id, { status: "converting", error: null });
    const overwriteOriginal = options.overwriteOriginal === true;
    const outputPath = overwriteOriginal ? null : editedFeedpakPath(item, outputDir);
    const result = await api.updateFeedpak({
      inputPath: item.path,
      outputPath,
      overwrite: overwriteOriginal,
      coverPath
    });
    if (!result.ok) {
      updateItem(item.id, { status: "failed", error: result.error });
      return;
    }
    if (overwriteOriginal) {
      updateItem(item.id, { status: "queued", error: null });
      await inspectItem({ ...item, status: "queued" });
    } else {
      updateItem(item.id, { status: "converted", outputPath: result.outputPath || outputPath, validation: result.validation || null, error: null });
    }
  }

  async function removeFeedpakCover(item, options = {}) {
    if (!item || item.sourceType !== "feedpak") return;
    updateItem(item.id, { status: "converting", error: null });
    const overwriteOriginal = options.overwriteOriginal === true;
    const outputPath = overwriteOriginal ? null : editedFeedpakPath(item, outputDir);
    const result = await api.updateFeedpak({
      inputPath: item.path,
      outputPath,
      overwrite: overwriteOriginal,
      removeCover: true
    });
    if (!result.ok) {
      updateItem(item.id, { status: "failed", error: result.error });
      return;
    }
    if (overwriteOriginal) {
      updateItem(item.id, { status: "queued", error: null });
      await inspectItem({ ...item, status: "queued" });
    } else {
      updateItem(item.id, { status: "converted", outputPath: result.outputPath || outputPath, validation: result.validation || null, error: null });
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
    updateItem(item.id, { status: "converting", error: null });
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
      updateItem(item.id, { status: "failed", error: result.error });
      return result;
    }
    if (overwriteOriginal) {
      updateItem(item.id, { status: "queued", error: null });
      await inspectItem({ ...item, status: "queued" });
    } else {
      updateItem(item.id, { status: "converted", outputPath: result.outputPath || outputPath, validation: result.validation || null, error: null });
    }
    return result;
  }

  async function reprocessFeedpakStems(item, options = {}) {
    if (!item || item.sourceType !== "feedpak") return { ok: false, error: "Select a FeedPak first." };
    if (!separateStems) return { ok: false, error: "Enable Separate stems in Settings first." };
    updateItem(item.id, { status: "converting", error: null });
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
      updateItem(item.id, { status: "failed", error: result.error });
      return result;
    }
    if (overwriteOriginal) {
      updateItem(item.id, { status: "queued", error: null });
      await inspectItem({ ...item, status: "queued" });
    } else {
      updateItem(item.id, { status: "converted", outputPath: result.outputPath || outputPath, validation: result.validation || null, error: null });
    }
    return result;
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

  const viewMeta = activeView === "settings"
    ? { title: "Settings", description: "Conversion defaults, stem splitting, and diagnostics." }
    : activeView === "feedpak"
      ? { title: "Edit FeedPaks", description: "Inspect packages, update metadata, manage stems, and organize files." }
      : { title: "Convert", description: "Build FeedBack-ready packages from CDLC files." };

  return (
    <div className="app" onDragOver={(event) => event.preventDefault()} onDrop={onDrop}>
      <aside className="app-sidebar">
        <div className="brand">
          <span className="brand-mark">FF</span>
          <div>
            <strong>FeedForge {appVersion && <span className="version-badge">v{appVersion}</span>}</strong>
            <small>FeedBack song toolkit</small>
          </div>
        </div>
        <nav className="side-nav" aria-label="FeedForge sections">
          <button className={activeView === "workspace" ? "active" : ""} onClick={() => setActiveView("workspace")}>
            <Guitar size={18} />
            <span>Convert</span>
          </button>
          <button className={activeView === "settings" ? "active" : ""} onClick={() => setActiveView("settings")}>
            <Server size={18} />
            <span>Settings</span>
          </button>
          <button className={activeView === "feedpak" ? "active" : ""} onClick={() => setActiveView("feedpak")}>
            <FileMusic size={18} />
            <span>Edit FeedPaks</span>
          </button>
        </nav>
        <div className="sidebar-links">
          <button className="support-link sidebar-support" onClick={() => api.openWebsite()} title="Open FeedForge Hub">
            <Globe size={17} />
            Website
          </button>
          <button className="support-link sidebar-support" onClick={() => api.openDiscord()} title="Join the FeedForge Discord">
            <DiscordIcon size={17} />
            Discord
          </button>
          <button className="support-link sidebar-support kofi" onClick={() => api.openSupport()} title="Support FeedForge on Ko-fi">
            <Coffee size={17} />
            Support us on Ko-fi
          </button>
        </div>
      </aside>
      <main className="workspace">
        <header className="topbar">
          <div className="title-group">
            <span className="page-kicker">FeedForge</span>
            <h1>{viewMeta.title}</h1>
            <p>{viewMeta.description}</p>
          </div>
          <div className="header-actions">
            <button
              className={`stem-header-status ${headerStemStatusClass(separateStems, stemServerStatus, isStartingStemServer, stemServerMatchesSelectedConfig)}`}
              onClick={() => {
                setActiveView("settings");
                setSettingsSection("stems");
              }}
              title="Open stem splitting settings"
            >
              <Server size={16} />
              <span>
                <strong>Stem server</strong>
                <small>{headerStemStatusLabel(separateStems, stemServerStatus, isStartingStemServer, stemServerMatchesSelectedConfig)}</small>
              </span>
            </button>
            <button className="primary" onClick={convertQueue} disabled={!items.length || isConverting}>
              {isConverting ? <RotateCw className="spin" size={18} /> : <Download size={18} />}
              Convert queue{isConverting ? ` (${effectiveConversionWorkers}x)` : ""}
            </button>
            {isConverting && (
              <button className="danger" onClick={stopConversion} disabled={isStopping}>
                <Square size={17} />
                {isStopping ? "Stopping" : "Stop after current"}
              </button>
            )}
          </div>
        </header>

        <section className="toolbar">
          <div className="search">
            <Search size={17} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search title, artist, or album" />
          </div>
          <button onClick={chooseFiles}><Plus size={17} /> Add files</button>
          <button onClick={chooseFolder}><FolderOpen size={17} /> Add folder</button>
        </section>

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

        {activeView === "settings" ? (
          <section className="settings-page">
            <div className="settings-nav" aria-label="Settings sections">
              <button className={settingsSection === "conversion" ? "active" : ""} onClick={() => setSettingsSection("conversion")}>Conversion</button>
              <button className={settingsSection === "stems" ? "active" : ""} onClick={() => setSettingsSection("stems")}>Stem splitting</button>
              <button className={settingsSection === "diagnostics" ? "active" : ""} onClick={() => setSettingsSection("diagnostics")}>Diagnostics</button>
            </div>

            {settingsSection === "conversion" && (
            <div className="settings-card">
              <div className="settings-card-head">
                <div>
                  <h2>Conversion</h2>
                  <p>Output, naming, and package options.</p>
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
                    <span>Available: {"{artist}"}, {"{title}"}, {"{album}"}, {"{year}"}, {"{source}"}</span>
                  </label>
                )}
                <div className="option-grid">
                  <label className="toggle"><input type="checkbox" checked={overwrite} onChange={(event) => setOverwrite(event.target.checked)} /> Overwrite existing output</label>
                  <label className="toggle"><input type="checkbox" checked={separateStems} onChange={(event) => setSeparateStems(event.target.checked)} disabled={isConverting} /> Separate stems</label>
                  <label className="toggle lab-toggle">
                    <input type="checkbox" checked={bStandardTo7String} onChange={(event) => setBStandardTo7String(event.target.checked)} disabled={isConverting} />
                    B standard to 7-string
                  </label>
                </div>
              </div>
            </div>
            )}

            {settingsSection === "stems" && (
              <div className="settings-card">
                <div className="settings-card-head">
                  <div>
                    <h2>Stem splitting</h2>
                    <p>Local Demucs or a remote FeedBack stem server.</p>
                  </div>
                  <span className={`server-badge ${stemServerBadge(stemServerStatus, isStartingStemServer, stemServerMatchesSelectedConfig).toLowerCase().replace(/\s+/g, "-")}`}>{stemServerBadge(stemServerStatus, isStartingStemServer, stemServerMatchesSelectedConfig)}</span>
                </div>
                {!separateStems ? (
                  <div className="settings-empty">
                    <strong>Stem splitting is disabled</strong>
                    <span>Enable stems to configure local or remote splitting.</span>
                    <button onClick={() => { setSettingsSection("conversion"); setSeparateStems(true); }}>Enable stems</button>
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
                      <input value={pythonPath} onChange={(event) => setPythonPath(event.target.value)} placeholder="Auto-detect or choose python.exe" disabled={isConverting || stemServerStatus.processRunning || stemServerBusy} />
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

            {settingsSection === "diagnostics" && (
              <div className="settings-card">
                <div className="settings-card-head">
                  <div>
                    <h2>Diagnostics</h2>
                    <p>Logs, stem server output, and library checks.</p>
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
            feedpakItems={feedpakItems}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onAddFiles={chooseFiles}
            onSaveFeedpakMetadata={saveFeedpakMetadata}
            onReplaceFeedpakCover={replaceFeedpakCover}
            onRemoveFeedpakCover={removeFeedpakCover}
            onReplaceFeedpakStem={replaceFeedpakStem}
            onRemoveFeedpakStem={removeFeedpakStem}
            onReprocessFeedpakStems={reprocessFeedpakStems}
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

function stemServerBadge(status, isStarting, matchesSelection = true) {
  if (status.healthy && matchesSelection) return "Running";
  if (status.healthy && !matchesSelection) return "Config changed";
  if (status.starting || status.processRunning || isStarting) return "Starting";
  if (status.running) return "Unhealthy";
  return "Stopped";
}

function headerStemStatusClass(separateStems, status, isStarting, matchesSelection = true) {
  if (!separateStems && status.healthy) return "ready muted";
  if (!separateStems) return "off";
  if (status.healthy && matchesSelection) return "ready";
  if (status.healthy && !matchesSelection) return "changed";
  if (status.starting || status.processRunning || isStarting) return "starting";
  if (status.running || status.phase === "error") return "error";
  return "off";
}

function headerStemStatusLabel(separateStems, status, isStarting, matchesSelection = true) {
  if (!separateStems && status.healthy) return "Ready, stems off";
  if (!separateStems) return "Stems off";
  if (status.healthy && matchesSelection) return "Ready";
  if (status.healthy && !matchesSelection) return "Config changed";
  if (status.starting || status.processRunning || isStarting) return "Starting";
  if (status.running || status.phase === "error") return "Needs attention";
  return "Not running";
}

function stemServerTitle(status, busy, matchesSelection = true) {
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

function stemServerActionText(status, busy, selectedModel = null) {
  if (!busy) {
    if (status.healthy) return selectedModel?.installed ? "Apply selected model" : "Download/start selected model";
    return status.running ? "Restart local stem server" : "Install/start local stem server";
  }
  if (status.phase === "downloading") return "Downloading...";
  if (status.phase === "installing") return "Installing...";
  if (status.phase === "loading") return "Loading model...";
  return "Starting...";
}

function stemPhasePercent(status) {
  if (status.healthy || status.phase === "ready") return 100;
  if (status.phase === "loading") return 78;
  if (status.phase === "installing") return 50;
  if (status.phase === "downloading") return 30;
  if (status.phase === "starting") return 14;
  if (status.phase === "error") return 100;
  return 0;
}

function stemPhaseLabel(status, busy) {
  if (status.healthy) return "Ready";
  if (status.phase === "error") return "Error";
  if (status.phase === "downloading") return "Downloading";
  if (status.phase === "installing") return "Installing";
  if (status.phase === "loading") return "Loading";
  if (busy || status.starting) return "Starting";
  return "Idle";
}

function StemSetupProgress({ status, busy, debugLogInfo }) {
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

function stemServerDetail(status, demucsModel, selectedModel, matchesSelection = true) {
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

function stemServerPortOwners(status) {
  return Array.isArray(status?.portOwners) ? status.portOwners.filter((owner) => owner?.pid) : [];
}

function stemServerMatchesSelection(status, model, device, jobs) {
  if (!status?.healthy) return false;
  const modelMatches = !status.model || status.model === model;
  const requestedDevice = status.requestedDevice || status.device || "";
  const deviceMatches = !requestedDevice || requestedDevice === device || (device === "auto" && requestedDevice === "auto");
  const jobMatches = !status.concurrency || Number(status.concurrency) === Number(jobs || 1);
  return modelMatches && deviceMatches && jobMatches;
}

function normalizeStemSelection(value) {
  const allowed = new Set(DEMUCS_STEM_OPTIONS.map((stem) => stem.id));
  const selected = Array.isArray(value) ? value : DEFAULT_DEMUCS_STEMS;
  const normalized = [];
  for (const stem of selected) {
    const id = String(stem || "").trim().toLowerCase();
    if (allowed.has(id) && !normalized.includes(id)) normalized.push(id);
  }
  return normalized.length ? normalized : DEFAULT_DEMUCS_STEMS;
}

function toggleStemSelection(current, stemId) {
  const selected = normalizeStemSelection(current);
  if (selected.includes(stemId)) {
    const next = selected.filter((stem) => stem !== stemId);
    return next.length ? next : selected;
  }
  return normalizeStemSelection([...selected, stemId]);
}

function stemSelectionSummary(stems) {
  const selected = normalizeStemSelection(stems);
  if (selected.length === DEMUCS_STEM_OPTIONS.length) return "All supported stems will be requested. Full mix is always included.";
  const labels = selected
    .map((id) => DEMUCS_STEM_OPTIONS.find((stem) => stem.id === id)?.label || id)
    .join(", ");
  return `${labels} will be requested. Full mix is always included.`;
}

function StemSetupChecklist({ pythonInfo, setup, selectedModel, status, matchesSelection }) {
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

function pythonPrereqTitle(info, checking) {
  if (checking) return "Checking Python";
  if (info?.ok) return `Python ${info.version} ready`;
  if (info?.found) return "Python version unsupported";
  if (info?.found === false) return "Python not found";
  return "Python requirement";
}

function Metric({ label, value, tone = "" }) {
  return (
    <div className={`metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function LibraryAuditPanel({ folder, criteria, report, busy, onChooseFolder, onRun, onChangeCriterion }) {
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

function ConversionProgress({ progress, isConverting }) {
  const total = Math.max(0, progress.total || 0);
  const completed = Math.min(total, Math.max(0, progress.completed || 0));
  const failed = Math.max(0, progress.failed || 0);
  const remaining = Math.max(0, total - completed);
  const percent = total ? Math.round((completed / total) * 100) : 0;
  const status = progress.stopped
    ? "Stopped"
    : isConverting
      ? "Converting"
      : completed >= total
        ? "Complete"
        : "Waiting";

  return (
    <section className={`conversion-progress ${isConverting ? "active" : progress.stopped ? "stopped" : "complete"}`}>
      <div className="conversion-progress-head">
        <div>
          <strong>{status}</strong>
          <span>
            {completed} of {total} processed
            {remaining ? `, ${remaining} remaining` : ""}
            {failed ? `, ${failed} failed` : ""}
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

function FilterSelect({ label, value, onChange, options }) {
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

function selectedDemucsModel(models, modelId) {
  return (models || []).find((model) => model.id === modelId) || null;
}

function defaultDemucsDevices() {
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

function selectedDemucsDevice(devices, deviceId) {
  return (devices || []).find((device) => device.id === deviceId) || defaultDemucsDevices()[0];
}

function normalizeAutoNumberSetting(value, fallback = AUTO_SETTING) {
  if (value === AUTO_SETTING || value === undefined || value === null || value === "") {
    return fallback;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(1, Math.floor(parsed));
}

function normalizeInitialStemJobs(settings) {
  const normalized = normalizeAutoNumberSetting(settings?.demucsStemJobs, DEFAULT_DEMUCS_STEM_JOBS);
  if ((settings?.performanceSettingsVersion || 0) < 2 && normalized === 1) {
    return AUTO_SETTING;
  }
  return normalized;
}

function hostCpuCount() {
  return Math.max(2, Number(window.navigator?.hardwareConcurrency) || 4);
}

function resolveConversionWorkerCount(setting, options = {}) {
  const manual = normalizeAutoNumberSetting(setting, AUTO_SETTING);
  if (manual !== AUTO_SETTING) return Math.max(1, Math.min(Number(manual), 8));

  const cores = hostCpuCount();
  const base = cores >= 16 ? 6 : cores >= 10 ? 5 : cores >= 6 ? 4 : 2;
  if (!options.separateStems) return base;

  const stemJobs = Math.max(1, Number(options.stemJobs || 1));
  return Math.max(2, Math.min(base, stemJobs + 1, 4));
}

function resolveStemJobCount(setting, deviceId, devices) {
  const manual = normalizeAutoNumberSetting(setting, AUTO_SETTING);
  if (manual !== AUTO_SETTING) return Math.max(1, Math.min(Number(manual), 4));

  const device = autoResolvedStemDevice(deviceId, devices);
  const id = String(device?.id || deviceId || "").toLowerCase();
  const memoryGb = deviceMemoryGb(device);
  if (id === "cpu" || device?.kind === "cpu") return 1;
  if ((device?.kind === "cuda" || id.startsWith("cuda")) && memoryGb >= 16) return 2;
  return 1;
}

function autoResolvedStemDevice(deviceId, devices) {
  const list = Array.isArray(devices) ? devices : [];
  if (deviceId && deviceId !== AUTO_SETTING) {
    return selectedDemucsDevice(list, deviceId);
  }
  return list.find((device) => device.kind === "cuda" && device.recommended)
    || list.find((device) => String(device.id || "").startsWith("cuda"))
    || selectedDemucsDevice(list, AUTO_SETTING);
}

function deviceMemoryGb(device) {
  const direct = Number(device?.memory_gb);
  if (Number.isFinite(direct) && direct > 0) return direct;
  const detailMatch = String(device?.detail || "").match(/([\d.]+)\s*GB/i);
  return detailMatch ? Number(detailMatch[1]) || 0 : 0;
}

function mergeDemucsDevices(current, accelerators) {
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

function deviceLabel(device) {
  const suffix = device.recommended ? " - recommended" : "";
  const disabled = device.available === false ? " - unavailable" : "";
  return `${device.name || device.id}${device.id && device.name !== device.id ? ` (${device.id})` : ""}${suffix}${disabled}`;
}

function deviceHelpText(device, status) {
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

function stemJobHelpText(value, status) {
  const active = Number(status?.concurrency || value || 1);
  if (active <= 1) {
    return "Safest. One stem split at a time.";
  }
  if (active === 2) {
    return "Faster on strong GPUs, higher VRAM use.";
  }
  return "High VRAM use. May be slower or fail on smaller GPUs.";
}

function stemJobSelectionLabel(setting, effectiveJobs) {
  const jobs = Number(effectiveJobs || 1);
  if (setting === AUTO_SETTING) {
    return `Auto selected ${jobs} stem job${jobs === 1 ? "" : "s"}`;
  }
  return `Selected: ${jobs} stem job${jobs === 1 ? "" : "s"}`;
}

function resolvedDeviceLabel(status) {
  const id = status?.device || "";
  const match = (status?.accelerators || []).find((device) => device.id === id);
  if (!match) return id || "an unknown device";
  const memory = match.memory_gb ? `, ${match.memory_gb} GB VRAM` : "";
  return `${match.name || id} (${id}${memory})`;
}

function modelStatusLabel(model) {
  if (!model) return "Unknown";
  if (model.remoteOnly) return "Remote only";
  if (model.installed) return "Installed";
  if (model.partial) return `Partial ${model.installedCount || 0}/${model.requiredCount || 0}`;
  return "Download needed";
}

function DropZone({ onClick }) {
  return (
    <button className="drop-zone" onClick={onClick}>
      <UploadCloud size={30} />
      <strong>Drop PSARC or FeedPak files here</strong>
      <span>Convert CDLC, inspect FeedPaks, edit metadata, or split stems.</span>
    </button>
  );
}

function Queue({ items, selectedId, onSelect, onRemove, onExportAudio, onExportAudioItem, canRemove, canExportAudio }) {
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
              <strong>{item.preview?.title || item.name}</strong>
              <span>{item.preview?.artist || item.path}</span>
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

function FeedPakTools({
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
  onOrganizeByArtist,
  onChooseOutput,
  onRemoveItem,
  outputDir,
  overwrite,
  separateStems,
  demucsStems
}) {
  const [organizeMessage, setOrganizeMessage] = useState("");

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
        </div>
      </div>
      <div className="feedpak-organize-note">
        <span>{organizeMessage || "Artist folders keep original filenames."}</span>
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

function FeedPakMetric({ label, value }) {
  return (
    <div className="metric-card">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function Inspector({
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
  const isFeedpak = item?.sourceType === "feedpak" || preview?.source_type === "feedpak";
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

  return (
    <aside className={isFeedpak ? "inspector feedpak-inspector" : "inspector convert-inspector"}>
      <div className="inspector-rail">
        <section className="song-hero">
          <div className="cover">{cover ? <img src={cover} alt="" /> : <ImageIcon size={44} />}</div>
          <div className="song-copy">
            <span className="eyebrow">{isFeedpak ? "FeedPak package" : "Selected song"}</span>
            <h2>{preview?.title || item?.name || "No song selected"}</h2>
            <p>{preview?.artist || "Add PSARC or FeedPak files to inspect package details."}</p>
            <div className="chips">
              {preview?.album && <span>{preview.album}</span>}
              {preview?.year && <span>{preview.year}</span>}
              {preview?.duration && <span>{duration(preview.duration)}</span>}
              {preview?.is_multi_song && <span>{preview.song_count} songs</span>}
              {authors.length > 0 && <span>{authors.length} credit{authors.length === 1 ? "" : "s"}</span>}
            </div>
          </div>
        </section>

        <div className="inspector-tabs">
          <button className={tab === "overview" ? "active" : ""} onClick={() => setTab("overview")}>Overview</button>
          {isFeedpak && <button className={tab === "metadata" ? "active" : ""} onClick={() => setTab("metadata")}>Metadata</button>}
          {isFeedpak && <button className={tab === "stems" ? "active" : ""} onClick={() => setTab("stems")}>Stems</button>}
          <button className={tab === "tones" ? "active" : ""} onClick={() => setTab("tones")}>Tones</button>
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
            <div className="overview-metrics">
              <FeedPakMetric label={preview?.is_multi_song ? "Songs" : "Arrangements"} value={preview?.is_multi_song ? preview.song_count : arrangements.length} />
              <FeedPakMetric label={preview?.is_multi_song ? "Arrangements" : "Stems"} value={preview?.is_multi_song ? arrangements.length : stems.length} />
              <FeedPakMetric label="Tone rigs" value={countToneDefinitions(tones)} />
              <FeedPakMetric label="Credits" value={authors.length} />
            </div>
            <ul className="readiness readiness-grid">
              <ReadyLine ok={!!cover} text={cover ? "Cover image detected" : "No cover image"} muted={!cover} />
              <ReadyLine ok={arrangements.length > 0} text={`${arrangements.length || 0} arrangement${arrangements.length === 1 ? "" : "s"}`} />
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
            {item?.error && <div className="error-box"><AlertTriangle size={17} /> {item.error}</div>}
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
                <span>From PSARC metadata</span>
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
              <h2>Arrangements</h2>
              <Guitar size={18} />
            </div>
            <div className="arrangements">
              {arrangements.length === 0 && <div className="empty compact">No arrangements inspected yet.</div>}
              {arrangements.map((arrangement) => (
                <div className="arrangement" key={arrangement.id}>
                  <strong>{arrangement.name}</strong>
                  <span>{arrangement.difficulties} levels</span>
                  <span>{arrangement.note_count || arrangement.notes + arrangement.chords} notes</span>
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

function ToneInspector({ arrangements, tones, expanded = false }) {
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

function KnobValues({ values }) {
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

function gearClassName(gear) {
  const text = `${gear?.slot || ""} ${gear?.category || ""} ${gear?.key || ""} ${gear?.type || ""}`.toLowerCase();
  if (text.includes("cab")) return "gear-cab";
  if (text.includes("amp")) return "gear-amp";
  if (text.includes("delay") || text.includes("reverb") || text.includes("rack")) return "gear-rack";
  if (text.includes("dist") || text.includes("drive") || text.includes("fuzz") || text.includes("pedal")) return "gear-pedal";
  return "gear-effect";
}

function gearRoleLabel(gear) {
  const slot = String(gear?.slot || "").toLowerCase();
  if (slot.includes("cabinet")) return "Cab";
  if (slot.includes("amp")) return "Amp";
  if (slot.includes("rack")) return "Rack";
  if (slot.includes("pre")) return "Pre";
  if (slot.includes("post")) return "Post";
  return "FX";
}

function gearInitials(gear) {
  const source = String(gear?.key || gear?.type || gear?.slot || "FX").replace(/^(Amp|Cab|Pedal|Rack|Bass_Cab|Cabinet)_/i, "");
  const tokens = source.split(/[_\s-]+/).filter(Boolean);
  return (tokens.length > 1 ? `${tokens[0][0]}${tokens[1][0]}` : source.slice(0, 2)).toUpperCase();
}

function knobPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 0;
  if (number >= 0 && number <= 1) return Math.round(number * 100);
  return Math.max(0, Math.min(100, Math.round(number)));
}

function shortKnob(value) {
  return String(value).replace(/^[A-Za-z0-9]+_/, "");
}

function formatKnob(value) {
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  return String(value);
}

function parseAuthors(value) {
  return String(value || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [name, role] = line.split("|").map((part) => part.trim());
      return { name, role: role || "charter" };
    })
    .filter((author) => author.name);
}

function formatBytes(value) {
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes <= 0) return "unknown size";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function isSongPackage(filePath) {
  const lower = String(filePath || "").toLowerCase();
  return lower.endsWith(".psarc") || lower.endsWith(".feedpak");
}

function fileType(filePath) {
  return String(filePath || "").toLowerCase().endsWith(".feedpak") ? "feedpak" : "psarc";
}

function countToneDefinitions(tones) {
  return (tones || []).reduce((total, arrangement) => total + ((arrangement.definitions || []).length), 0);
}

function countToneChanges(tones) {
  return (tones || []).reduce((total, arrangement) => total + ((arrangement.changes || []).length), 0);
}

function toneTimelineDuration(changes) {
  const times = (changes || []).map((change) => Number(change.time || 0)).filter(Number.isFinite);
  return Math.max(1, ...times);
}

function ReadyLine({ ok, text, muted = false }) {
  return <li className={`${muted ? "muted" : ""} ${ok ? "ready-ok" : "ready-missing"}`}>{ok ? <Check size={16} /> : <XCircle size={16} />} {text}</li>;
}

function StatusIcon({ status }) {
  if (status === "converted") return <Check className="status-ok" size={18} />;
  if (status === "failed" || status === "needs-review") return <AlertTriangle className="status-warn" size={18} />;
  if (status === "converting" || status === "inspecting") return <RotateCw className="spin status-blue" size={18} />;
  return <Play className="status-blue" size={18} />;
}

function statusText(status) {
  return {
    queued: "Queued",
    inspecting: "Inspecting",
    ready: "Ready",
    "needs-review": "Review",
    converting: "Converting",
    converted: "Converted",
    failed: "Failed"
  }[status] || "Waiting";
}

function sortedOptions(values) {
  return Array.from(values)
    .filter(Boolean)
    .sort((left, right) => left.localeCompare(right, undefined, { sensitivity: "base" }));
}

function arrangementTuningLabels(arrangements) {
  const labels = new Set();
  for (const arrangement of arrangements || []) {
    labels.add(tuningLabel(arrangement?.tuning));
  }
  return Array.from(labels).filter(Boolean);
}

function tuningLabel(tuning) {
  if (!Array.isArray(tuning) || tuning.length === 0) return "";
  if (tuning.every((value) => Number(value) === 0)) {
    return tuning.length === 7 ? "7-string standard" : "E standard";
  }
  if (tuning.length === 6 && tuning.every((value) => Number(value) === -5)) return "B standard";
  if (tuning.length === 6 && tuning.join(",") === "-2,0,0,0,0,0") return "Drop D";
  if (tuning.length === 6 && tuning.join(",") === "-3,-1,-1,-1,-1,-1") return "C# standard";
  if (tuning.length === 6 && tuning.join(",") === "-4,-2,-2,-2,-2,-2") return "C standard";
  return tuning.map((value) => Number(value) > 0 ? `+${value}` : String(value)).join(" ");
}

function basename(filePath) {
  return filePath.split(/[\\/]/).pop();
}

function withoutExtension(fileName) {
  return fileName.replace(/\.[^.]+$/, "");
}

function outputPathForItem(item, outputDir, layout, sourceRoot, nameFormat = "source", customTemplate = "{artist} - {title}") {
  const fileName = outputFileNameForItem(item, nameFormat, customTemplate);
  if (layout === "artist") {
    return joinPath(outputDir, safePathSegment(item.preview?.artist || "Unknown Artist"), fileName);
  }
  if (layout === "preserve") {
    const relativeDir = relativeParentDir(item.path, sourceRoot);
    return relativeDir ? joinPath(outputDir, relativeDir, fileName) : joinPath(outputDir, fileName);
  }
  return joinPath(outputDir, fileName);
}

function reserveBatchOutputPaths(items, outputDir, layout, batchSourceRoot, nameFormat, customTemplate) {
  const reserved = new Map();
  const used = new Set();
  for (const item of items || []) {
    const rawPath = outputDir ? outputPathForItem(item, outputDir, layout, item.sourceRoot || batchSourceRoot, nameFormat, customTemplate) : null;
    if (!rawPath) {
      reserved.set(item.id, null);
      continue;
    }
    const uniquePath = uniqueOutputPath(rawPath, used);
    used.add(normalizePath(uniquePath).toLowerCase());
    reserved.set(item.id, uniquePath);
  }
  return reserved;
}

function uniqueOutputPath(filePath, used) {
  const normalized = normalizePath(filePath).toLowerCase();
  if (!used.has(normalized)) return filePath;
  const folder = parentDir(filePath);
  const name = basename(filePath);
  const stem = withoutExtension(name);
  const extension = name.slice(stem.length);
  let counter = 2;
  while (true) {
    const candidate = joinPath(folder, `${stem} (${counter})${extension}`);
    if (!used.has(normalizePath(candidate).toLowerCase())) return candidate;
    counter += 1;
  }
}

function editedFeedpakPath(item, outputDir) {
  const sourceName = withoutExtension(item?.name || basename(item?.path || "song.feedpak"));
  const folder = outputDir || parentDir(item?.path || "") || "";
  const stamp = new Date().toISOString().replace(/[-:T.Z]/g, "").slice(0, 14);
  return joinPath(folder, `${safePathSegment(sourceName, "song")}.edited-${stamp}.feedpak`);
}

function outputFileNameForItem(item, format, customTemplate) {
  const meta = outputNameMetadata(item);
  const partsByFormat = {
    source: [meta.source],
    "artist-title": [meta.artist, meta.title],
    "title-artist": [meta.title, meta.artist],
    "artist-album-title": [meta.artist, meta.album, meta.title]
  };
  let stem;
  if (format === "custom") {
    stem = renderNameTemplate(customTemplate, meta);
  } else {
    stem = (partsByFormat[format] || partsByFormat.source)
      .map((part) => String(part || "").trim())
      .filter(Boolean)
      .join(" - ");
  }
  return `${safePathSegment(stem, meta.source)}.feedpak`;
}

function outputNameTemplateForFormat(format, customTemplate) {
  if (format === "custom") return customTemplate || "{source}";
  return {
    source: "{source}",
    "artist-title": "{artist} - {title}",
    "title-artist": "{title} - {artist}",
    "artist-album-title": "{artist} - {album} - {title}"
  }[format] || "{source}";
}

function outputNameMetadata(item) {
  const source = withoutExtension(item?.name || basename(item?.path || "song.psarc"));
  return {
    source,
    artist: item?.preview?.artist || "Unknown Artist",
    title: item?.preview?.title || source,
    album: item?.preview?.album || "",
    year: item?.preview?.year || ""
  };
}

function renderNameTemplate(template, metadata) {
  return String(template || "{source}").replace(/\{(artist|title|album|year|source)\}/gi, (_match, key) => metadata[key.toLowerCase()] || "");
}

function relativeParentDir(filePath, rootPath) {
  const parent = parentDir(filePath);
  if (!parent || !rootPath) return "";
  const normalizedParent = normalizePath(parent);
  const normalizedRoot = normalizePath(rootPath);
  if (normalizedParent === normalizedRoot) return "";
  const prefix = `${normalizedRoot}\\`;
  if (!normalizedParent.toLowerCase().startsWith(prefix.toLowerCase())) return "";
  return normalizedParent.slice(prefix.length);
}

function commonAncestorDir(paths) {
  const dirs = (paths || []).map(parentDir).filter(Boolean).map(normalizePath);
  if (!dirs.length) return null;
  const split = dirs.map((dir) => dir.split("\\").filter(Boolean));
  const first = split[0];
  const parts = [];
  for (let index = 0; index < first.length; index += 1) {
    const candidate = first[index].toLowerCase();
    if (split.every((items) => (items[index] || "").toLowerCase() === candidate)) {
      parts.push(first[index]);
    } else {
      break;
    }
  }
  if (!parts.length) return null;
  return parts.join("\\");
}

function joinPath(...parts) {
  return parts
    .filter((part) => part !== null && part !== undefined && String(part).length > 0)
    .map((part, index) => {
      const value = String(part);
      if (index === 0) return value.replace(/[\\/]+$/, "");
      return value.replace(/^[\\/]+|[\\/]+$/g, "");
    })
    .join("\\");
}

function normalizePath(filePath) {
  return String(filePath || "").replace(/[\\/]+/g, "\\").replace(/[\\/]$/, "");
}

function safePathSegment(value, fallback = "Unknown Artist") {
  const normalized = String(value || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "");
  const cleaned = (normalized || String(value || ""))
    .replace(/[<>:"/\\|?*\x00-\x1F]/g, "_")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/[. ]+$/g, "");
  return cleaned || fallback;
}

function normalizePathKey(filePath) {
  return String(filePath || "").replaceAll("/", "\\").toLowerCase();
}

function duration(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  const minutes = Math.floor(value / 60);
  const seconds = Math.floor(value % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function readSettings() {
  try {
    return JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}");
  } catch {
    return {};
  }
}

function normalizeAuditCriteria(value) {
  return { ...DEFAULT_AUDIT_CRITERIA, ...(value && typeof value === "object" ? value : {}) };
}

function writeSettings(settings) {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
}

function parentDir(filePath) {
  if (!filePath || typeof filePath !== "string") return null;
  const normalized = filePath.replace(/[\\/]+$/, "");
  const index = Math.max(normalized.lastIndexOf("\\"), normalized.lastIndexOf("/"));
  return index > 0 ? normalized.slice(0, index) : normalized;
}

createRoot(document.getElementById("root")).render(<App />);
