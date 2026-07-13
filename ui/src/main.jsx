import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertTriangle,
  Check,
  Coffee,
  Download,
  ExternalLink,
  FolderOpen,
  Guitar,
  ImageIcon,
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
const DEFAULT_CONVERSION_WORKERS = 2;
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
  const [demucsStemJobs, setDemucsStemJobs] = useState(() => Number(initialSettingsRef.current.demucsStemJobs) || 1);
  const [demucsStems, setDemucsStems] = useState(() => normalizeStemSelection(initialSettingsRef.current.demucsStems));
  const [demucsDevices, setDemucsDevices] = useState(defaultDemucsDevices());
  const [demucsModels, setDemucsModels] = useState([]);
  const [demucsModelRoot, setDemucsModelRoot] = useState("");
  const [demucsSetup, setDemucsSetup] = useState(null);
  const [stemServerStatus, setStemServerStatus] = useState({ url: "http://127.0.0.1:7865", running: false, starting: false, healthy: false });
  const [isStartingStemServer, setIsStartingStemServer] = useState(false);
  const [debugLogInfo, setDebugLogInfo] = useState(null);
  const [pythonInfo, setPythonInfo] = useState(null);
  const [isCheckingPython, setIsCheckingPython] = useState(false);
  const [updateInfo, setUpdateInfo] = useState(null);
  const [appVersion, setAppVersion] = useState("");
  const [conversionWorkers, setConversionWorkers] = useState(DEFAULT_CONVERSION_WORKERS);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [artistFilter, setArtistFilter] = useState("all");
  const [albumFilter, setAlbumFilter] = useState("all");
  const [tuningFilter, setTuningFilter] = useState("all");
  const [activeView, setActiveView] = useState("workspace");
  const [settingsSection, setSettingsSection] = useState("conversion");
  const [isConverting, setIsConverting] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const itemsRef = useRef(items);
  const inspectionQueueRef = useRef([]);
  const activeInspectionsRef = useRef(0);
  const isConvertingRef = useRef(false);
  const stopRequestedRef = useRef(false);

  useEffect(() => {
    itemsRef.current = items;
  }, [items]);

  useEffect(() => {
    writeSettings({ outputDir, outputLayout, outputNameFormat, outputNameTemplate, lastSourcePath, bStandardTo7String, separateStems, demucsUrl, demucsInstallDir, pythonPath, demucsModel, demucsDevice, demucsStemJobs, demucsStems });
  }, [outputDir, outputLayout, outputNameFormat, outputNameTemplate, lastSourcePath, bStandardTo7String, separateStems, demucsUrl, demucsInstallDir, pythonPath, demucsModel, demucsDevice, demucsStemJobs, demucsStems]);

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
    if (!separateStems || activeView !== "settings" || settingsSection !== "stems") return undefined;
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
    refresh();
    const pollMs = (isStartingStemServer || stemServerStatus.starting || stemServerStatus.processRunning) && !stemServerStatus.healthy ? 1000 : 5000;
    const timer = window.setInterval(refresh, pollMs);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [separateStems, activeView, settingsSection, isStartingStemServer, stemServerStatus.starting, stemServerStatus.processRunning, stemServerStatus.healthy]);

  useEffect(() => {
    return api.onDroppedPaths(async (paths) => {
      const expanded = await api.expandPaths(paths);
      rememberSourcePath(paths[0]);
      addFiles(expanded);
    });
  }, []);

  const selected = items.find((item) => item.id === selectedId) || items[0] || null;
  const filterOptions = useMemo(() => {
    const artists = new Set();
    const albums = new Set();
    const tunings = new Set();
    for (const item of items) {
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
  }, [items]);

  const filtered = items.filter((item) => {
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
    total: items.length,
    ready: items.filter((item) => item.status === "ready" || item.status === "converted").length,
    converted: items.filter((item) => item.status === "converted").length,
    failed: items.filter((item) => item.status === "failed").length
  }), [items]);
  const stemServerBusy = (isStartingStemServer || stemServerStatus.starting || stemServerStatus.processRunning) && !stemServerStatus.healthy;
  const selectedModel = selectedDemucsModel(demucsModels, demucsModel);
  const selectedDevice = selectedDemucsDevice(demucsDevices, demucsDevice);
  const stemServerMatchesSelectedConfig = stemServerMatchesSelection(stemServerStatus, demucsModel, demucsDevice, demucsStemJobs);
  const stemServerReadyForSelection = stemServerStatus.healthy && stemServerMatchesSelectedConfig;

  async function addFiles(paths, sourceRoot = null) {
    const existing = new Set(itemsRef.current.map((item) => normalizePathKey(item.path)));
    const incoming = paths
      .filter((filePath) => filePath.toLowerCase().endsWith(".psarc"))
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
        sourceRoot,
        status: "queued",
        preview: null,
        outputPath: null,
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
        `FeedForge: selected device ${demucsDevice}`
      ]
    }));
    try {
      const status = await api.startStemServer({ installDir: demucsInstallDir, pythonPath, model: demucsModel, device: demucsDevice, concurrency: demucsStemJobs });
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

  async function chooseDemucsInstallDir() {
    const folder = await api.pickDemucsInstallDir({ defaultPath: demucsInstallDir || undefined });
    if (folder) setDemucsInstallDir(folder);
  }

  function rememberSourcePath(filePath) {
    const sourcePath = parentDir(filePath);
    if (sourcePath) setLastSourcePath(sourcePath);
  }

  async function convertQueue() {
    if (!items.length || isConverting) return;
    isConvertingRef.current = true;
    stopRequestedRef.current = false;
    setIsStopping(false);
    setIsConverting(true);
    const stopManagedStemServerAfterQueue = separateStems && stemServerStatus.processRunning;
    const pending = [];
    const pendingPaths = new Set();
    for (const item of itemsRef.current) {
      if (item.status === "converted" || item.status === "converting") continue;
      const key = normalizePathKey(item.path);
      if (pendingPaths.has(key)) continue;
      pendingPaths.add(key);
      pending.push(item);
    }
    const batchSourceRoot = commonAncestorDir(pending.map((item) => item.path));
    let index = 0;

    async function convertNext() {
      if (stopRequestedRef.current) return;
      const item = pending[index];
      index += 1;
      if (!item) return;
      updateItem(item.id, { status: "converting", error: null });
      const outputPath = outputDir ? outputPathForItem(item, outputDir, outputLayout, item.sourceRoot || batchSourceRoot, outputNameFormat, outputNameTemplate) : null;
      const result = await api.convert({
        inputPath: item.path,
        outputPath,
        overwrite,
        bStandardTo7String,
        separateStems,
        demucsUrl: demucsUrl.trim(),
        demucsApiKey: demucsApiKey.trim(),
        demucsModel,
        demucsStems
      });
      if (!result.ok) {
        updateItem(item.id, { status: "failed", error: result.error });
      } else {
        const warnings = Array.isArray(result.warnings) ? result.warnings.filter(Boolean) : [];
        updateItem(item.id, {
          status: "converted",
          outputPath: result.outputPath || outputPath,
          error: warnings.length ? warnings.join("\n") : null
        });
      }
      if (stopRequestedRef.current) return;
      await convertNext();
    }

    try {
      const workerCount = Math.min(Math.max(1, conversionWorkers), pending.length);
      await Promise.all(Array.from({ length: workerCount }, () => convertNext()));
    } finally {
      isConvertingRef.current = false;
      stopRequestedRef.current = false;
      setIsStopping(false);
      setIsConverting(false);
      if (stopManagedStemServerAfterQueue) {
        stopLocalStemServer();
      }
      pumpInspectionQueue();
    }
  }

  function stopConversion() {
    stopRequestedRef.current = true;
    setIsStopping(true);
  }

  function onDrop(event) {
    event.preventDefault();
  }

  return (
    <div className="app" onDragOver={(event) => event.preventDefault()} onDrop={onDrop}>
      <main className="workspace">
        <header className="topbar">
          <div className="title-group">
            <div className="brand">
              <span className="brand-mark">FF</span>
              <div>
                <strong>FeedForge {appVersion && <span className="version-badge">v{appVersion}</span>}</strong>
                <small>FeedBack song toolkit</small>
              </div>
            </div>
            <h1>Build FeedPaks</h1>
            <p>Convert, organize, and package CDLC for FeedBack.</p>
          </div>
          <div className="header-actions">
            <button className="support-link" onClick={() => api.openSupport()} title="Support FeedForge on Ko-fi">
              <Coffee size={17} />
              Support
            </button>
            <button className="primary" onClick={convertQueue} disabled={!items.length || isConverting}>
              {isConverting ? <RotateCw className="spin" size={18} /> : <Download size={18} />}
              Convert queue{isConverting ? ` (${conversionWorkers}x)` : ""}
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
          <button onClick={chooseFiles}><Plus size={17} /> Add PSARCs</button>
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

        <section className="view-tabs app-tabs" aria-label="FeedForge sections">
          <button className={activeView === "workspace" ? "active" : ""} onClick={() => setActiveView("workspace")}>Workspace</button>
          <button className={activeView === "settings" ? "active" : ""} onClick={() => setActiveView("settings")}>Settings</button>
        </section>

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
                  <select value={conversionWorkers} onChange={(event) => setConversionWorkers(Number(event.target.value))} disabled={isConverting}>
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
                    <select value={demucsStemJobs} onChange={(event) => setDemucsStemJobs(Number(event.target.value))} disabled={isConverting || stemServerBusy}>
                      {[1, 2, 3, 4].map((value) => <option key={value} value={value}>{value}</option>)}
                    </select>
                  </label>
                  <div className="demucs-device-note">
                    <strong>{stemServerReadyForSelection ? `Server allows ${stemServerStatus.concurrency || 1} stem job${Number(stemServerStatus.concurrency || 1) === 1 ? "" : "s"}` : `Selected: ${demucsStemJobs} stem job${demucsStemJobs === 1 ? "" : "s"}`}</strong>
                    <span>{stemJobHelpText(demucsStemJobs, stemServerStatus)}</span>
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
                    <p>Logs and stem server output.</p>
                  </div>
                </div>
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
                <Queue items={filtered} selectedId={selected?.id} onSelect={setSelectedId} onRemove={removeItem} canRemove={!isConverting} />
              </div>
              <Inspector item={selected} />
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
      <strong>Drop PSARC files here</strong>
      <span>Batch import, inspect, and convert without leaving this screen.</span>
    </button>
  );
}

function Queue({ items, selectedId, onSelect, onRemove, canRemove }) {
  const visibleItems = items.slice(0, QUEUE_RENDER_LIMIT);
  const hiddenCount = Math.max(0, items.length - visibleItems.length);
  return (
    <section className="panel queue-panel">
      <div className="panel-title">
        <h2>Import queue</h2>
        <span>{items.length} file{items.length === 1 ? "" : "s"}</span>
      </div>
      <div className="queue">
        {items.length === 0 && <div className="empty">No PSARC files imported yet.</div>}
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
            </div>
            <div className="queue-meta">
              <span>{item.preview ? duration(item.preview.duration) : "-"}</span>
              <b>{statusText(item.status)}</b>
            </div>
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

function Inspector({ item }) {
  const [tab, setTab] = useState("overview");
  const preview = item?.preview;
  const cover = preview?.cover_path ? `file:///${preview.cover_path.replaceAll("\\", "/")}` : null;
  const arrangements = preview?.arrangements || [];
  const tones = preview?.tones || [];
  const authors = preview?.authors || [];
  return (
    <aside className="inspector">
      <section className="song-hero">
        <div className="cover">{cover ? <img src={cover} alt="" /> : <ImageIcon size={44} />}</div>
        <div className="song-copy">
          <span className="eyebrow">Selected song</span>
          <h2>{preview?.title || item?.name || "No song selected"}</h2>
          <p>{preview?.artist || "Add PSARC files to inspect metadata and conversion readiness."}</p>
            <div className="chips">
              {preview?.album && <span>{preview.album}</span>}
              {preview?.year && <span>{preview.year}</span>}
              {preview?.duration && <span>{duration(preview.duration)}</span>}
              {authors.length > 0 && <span>{authors.length} credit{authors.length === 1 ? "" : "s"}</span>}
            </div>
        </div>
      </section>

      <div className="inspector-tabs">
        <button className={tab === "overview" ? "active" : ""} onClick={() => setTab("overview")}>Overview</button>
        <button className={tab === "tones" ? "active" : ""} onClick={() => setTab("tones")}>Tones</button>
      </div>

      {tab === "overview" ? (
        <>
          <section className="panel">
            <div className="panel-title">
              <h2>Readiness</h2>
              <span>{item ? statusText(item.status) : "Waiting"}</span>
            </div>
            <ul className="readiness">
              <ReadyLine ok={!!preview} text="Package metadata inspected" />
              <ReadyLine ok={!!cover} text="Cover image detected" />
              <ReadyLine ok={arrangements.length > 0} text={`${arrangements.length || 0} playable arrangement${arrangements.length === 1 ? "" : "s"}`} />
              <ReadyLine ok={tones.length > 0} text={tones.length ? `${countToneDefinitions(tones)} tone definition${countToneDefinitions(tones) === 1 ? "" : "s"} detected` : "No tone definitions detected"} muted={!tones.length} />
              <ReadyLine ok={authors.length > 0} text={authors.length ? `${authors.length} author credit${authors.length === 1 ? "" : "s"} retained` : "No embedded author credit found"} muted={!authors.length} />
              <ReadyLine ok={!!preview?.lyrics} text={preview?.lyrics ? `${preview.lyrics} lyric timing events for karaoke` : "No vocals lyrics detected"} muted={!preview?.lyrics} />
            </ul>
            {item?.error && <div className="error-box"><AlertTriangle size={17} /> {item.error}</div>}
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
      ) : (
        <ToneInspector arrangements={arrangements} tones={tones} />
      )}
    </aside>
  );
}

function ToneInspector({ arrangements, tones }) {
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
  useEffect(() => {
    if (rows.length && !rows.some((arrangement) => arrangement.id === activeArrangement)) {
      setActiveArrangement(rows[0].id);
    }
  }, [rows, activeArrangement]);

  return (
    <section className="panel tone-panel">
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
            <div className="tone-changes">
              {(active.changes || []).length === 0 && <span className="muted-text">No tone changes. Base tone is used for the whole song.</span>}
              {(active.changes || []).slice(0, 16).map((change, index) => (
                <div className="tone-change" key={`${change.time}-${change.name}-${index}`}>
                  <b>{duration(change.time)}</b>
                  <span>{change.name}</span>
                  <code>{change.rig}</code>
                </div>
              ))}
              {(active.changes || []).length > 16 && <span className="muted-text">Showing first 16 of {active.changes.length} tone changes.</span>}
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
                          <div className="gear-face">
                            <b>{gearInitials(gear)}</b>
                            <i />
                            <i />
                            <i />
                          </div>
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

function countToneDefinitions(tones) {
  return (tones || []).reduce((total, arrangement) => total + ((arrangement.definitions || []).length), 0);
}

function countToneChanges(tones) {
  return (tones || []).reduce((total, arrangement) => total + ((arrangement.changes || []).length), 0);
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
