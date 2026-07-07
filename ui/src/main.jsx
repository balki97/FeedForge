import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertTriangle,
  Check,
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
const TONE_MIGRATION_WARNING =
  "Tone migration will also seed or repair local FeedBack Rig Builder routes on this PC after conversion. Existing FeedForge-created routes for these songs may be replaced. Continue?";

function App() {
  const initialSettingsRef = useRef(null);
  if (initialSettingsRef.current === null) {
    initialSettingsRef.current = readSettings();
  }

  const [items, setItems] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [outputDir, setOutputDir] = useState(() => initialSettingsRef.current.outputDir || null);
  const [lastSourcePath, setLastSourcePath] = useState(() => initialSettingsRef.current.lastSourcePath || null);
  const [overwrite, setOverwrite] = useState(false);
  const [includeTones, setIncludeTones] = useState(() => initialSettingsRef.current.includeTones !== false);
  const [bStandardTo7String, setBStandardTo7String] = useState(() => initialSettingsRef.current.bStandardTo7String === true);
  const [separateStems, setSeparateStems] = useState(() => initialSettingsRef.current.separateStems === true);
  const [demucsUrl, setDemucsUrl] = useState(() => initialSettingsRef.current.demucsUrl || "");
  const [demucsApiKey, setDemucsApiKey] = useState("");
  const [demucsInstallDir, setDemucsInstallDir] = useState(() => initialSettingsRef.current.demucsInstallDir || "");
  const [demucsModel, setDemucsModel] = useState(() => initialSettingsRef.current.demucsModel || "htdemucs_6s");
  const [demucsModels, setDemucsModels] = useState([]);
  const [demucsModelRoot, setDemucsModelRoot] = useState("");
  const [stemServerStatus, setStemServerStatus] = useState({ url: "http://127.0.0.1:7865", running: false, starting: false, healthy: false });
  const [isStartingStemServer, setIsStartingStemServer] = useState(false);
  const [updateInfo, setUpdateInfo] = useState(null);
  const [rigBuilderDataDir, setRigBuilderDataDir] = useState(() => initialSettingsRef.current.rigBuilderDataDir || "");
  const [conversionWorkers, setConversionWorkers] = useState(DEFAULT_CONVERSION_WORKERS);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [artistFilter, setArtistFilter] = useState("all");
  const [albumFilter, setAlbumFilter] = useState("all");
  const [tuningFilter, setTuningFilter] = useState("all");
  const [activeView, setActiveView] = useState("workspace");
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
    writeSettings({ outputDir, lastSourcePath, includeTones, bStandardTo7String, separateStems, demucsUrl, demucsInstallDir, demucsModel, rigBuilderDataDir });
  }, [outputDir, lastSourcePath, includeTones, bStandardTo7String, separateStems, demucsUrl, demucsInstallDir, demucsModel, rigBuilderDataDir]);

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
    check();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function loadDemucsModels() {
      try {
        const result = await api.getStemServerModels({ installDir: demucsInstallDir });
        if (cancelled) return;
        setDemucsModels(result.models || []);
        setDemucsModelRoot(result.installRoot || result.defaultInstallDir || "");
        if (!demucsInstallDir && result.defaultInstallDir) {
          setDemucsInstallDir(result.defaultInstallDir);
        }
      } catch {
        // Model metadata is helpful but not required for conversion.
      }
    }
    loadDemucsModels();
    return () => {
      cancelled = true;
    };
  }, [demucsInstallDir]);

  useEffect(() => {
    if (!separateStems) return undefined;
    let cancelled = false;
    async function refresh() {
      try {
        const status = await api.getStemServerStatus();
        if (!cancelled) setStemServerStatus(status);
      } catch {
        if (!cancelled) setStemServerStatus((current) => ({ ...current, running: false, healthy: false }));
      }
    }
    refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [separateStems]);

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
  const stemServerBusy = (isStartingStemServer || stemServerStatus.starting) && !stemServerStatus.healthy && !stemServerStatus.running;

  async function addFiles(paths) {
    const existing = new Set(itemsRef.current.map((item) => item.path));
    const incoming = paths
      .filter((filePath) => filePath.toLowerCase().endsWith(".psarc"))
      .filter((filePath) => {
        if (existing.has(filePath)) return false;
        existing.add(filePath);
        return true;
      })
      .map((filePath) => ({
        id: crypto.randomUUID(),
        path: filePath,
        name: basename(filePath),
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
    const result = await api.inspect(item.path, { rigBuilderDataDir });
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
    const paths = await api.pickFolder({ defaultPath: lastSourcePath || outputDir || undefined });
    rememberSourcePath(paths[0]);
    addFiles(paths);
  }

  async function chooseOutput() {
    const folder = await api.pickOutput({ defaultPath: outputDir || lastSourcePath || undefined });
    if (folder) setOutputDir(folder);
  }

  async function chooseRigBuilderData() {
    const folder = await api.pickRigBuilderData({ defaultPath: rigBuilderDataDir || undefined });
    if (!folder) return;
    setRigBuilderDataDir(folder);
    for (const item of itemsRef.current) {
      if (item.status === "converted" || item.status === "converting") continue;
      inspectionQueueRef.current.push(item.id);
    }
    pumpInspectionQueue();
  }

  async function startLocalStemServer() {
    if (isStartingStemServer) return;
    setIsStartingStemServer(true);
    try {
      const status = await api.startStemServer({ installDir: demucsInstallDir, model: demucsModel });
      setStemServerStatus(status);
      if (status.url) setDemucsUrl(status.url);
      const result = await api.getStemServerModels({ installDir: demucsInstallDir });
      setDemucsModels(result.models || []);
      setDemucsModelRoot(result.installRoot || result.defaultInstallDir || "");
    } finally {
      setIsStartingStemServer(false);
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
    if (includeTones && !window.confirm(TONE_MIGRATION_WARNING)) return;
    isConvertingRef.current = true;
    stopRequestedRef.current = false;
    setIsStopping(false);
    setIsConverting(true);
    const stopManagedStemServerAfterQueue = separateStems && stemServerStatus.processRunning;
    const pending = itemsRef.current.filter((item) => item.status !== "converted" && item.status !== "converting");
    let index = 0;

    async function convertNext() {
      if (stopRequestedRef.current) return;
      const item = pending[index];
      index += 1;
      if (!item) return;
      updateItem(item.id, { status: "converting", error: null });
      const outputPath = outputDir ? `${outputDir}\\${withoutExtension(item.name)}.feedpak` : null;
      const result = await api.convert({
        inputPath: item.path,
        outputPath,
        overwrite,
        includeTones,
        bStandardTo7String,
        separateStems,
        demucsUrl: demucsUrl.trim(),
        demucsApiKey: demucsApiKey.trim(),
        rigBuilderDataDir
      });
      if (!result.ok) {
        updateItem(item.id, { status: "failed", error: result.error });
      } else if (result.seed && !result.seed.ok) {
        updateItem(item.id, {
          status: "converted",
          outputPath: result.outputPath || outputPath,
          error: `Converted, but Rig Builder route seeding failed: ${result.seed.error || "unknown error"}`
        });
      } else {
        updateItem(item.id, { status: "converted", outputPath: result.outputPath || outputPath });
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
                <strong>FeedForge</strong>
                <small>FeedBack song toolkit</small>
              </div>
            </div>
            <h1>Build FeedPak packages</h1>
            <p>Import CDLC packages, review song details, and export FeedBack-ready files.</p>
          </div>
          <div className="header-actions">
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

        <section className="view-tabs" aria-label="FeedForge sections">
          <button className={activeView === "workspace" ? "active" : ""} onClick={() => setActiveView("workspace")}>Workspace</button>
          <button className={activeView === "settings" ? "active" : ""} onClick={() => setActiveView("settings")}>Settings</button>
        </section>

        {activeView === "settings" ? (
          <section className="settings-page">
            <div className="settings-card">
              <div className="settings-card-head">
                <div>
                  <h2>Conversion</h2>
                  <p>Output location, worker count, and package options.</p>
                </div>
              </div>
              <div className="settings-grid">
                <button className="path-action wide" onClick={chooseOutput} title={outputDir || "Use source folders for output"}>
                  <FolderOpen size={17} />
                  <span>Output</span>
                  <b>{outputDir ? outputDir : "Source folder"}</b>
                </button>
                <button className="path-action wide" onClick={chooseRigBuilderData} title={rigBuilderDataDir || "Auto-detect FeedBack Rig Builder data"}>
                  <FolderOpen size={17} />
                  <span>Rig data</span>
                  <b>{rigBuilderDataDir ? rigBuilderDataDir : "Auto"}</b>
                </button>
                <label className="select-control">
                  Workers
                  <select value={conversionWorkers} onChange={(event) => setConversionWorkers(Number(event.target.value))} disabled={isConverting}>
                    {[1, 2, 3, 4, 5, 6].map((value) => <option key={value} value={value}>{value}</option>)}
                  </select>
                </label>
                <div className="option-grid">
                  <label className="toggle"><input type="checkbox" checked={overwrite} onChange={(event) => setOverwrite(event.target.checked)} /> Overwrite existing output</label>
                  <label className="toggle"><input type="checkbox" checked={includeTones} onChange={(event) => setIncludeTones(event.target.checked)} disabled={isConverting} /> Include tones</label>
                  <label className="toggle"><input type="checkbox" checked={separateStems} onChange={(event) => setSeparateStems(event.target.checked)} disabled={isConverting} /> Separate stems</label>
                  <label className="toggle lab-toggle">
                    <input type="checkbox" checked={bStandardTo7String} onChange={(event) => setBStandardTo7String(event.target.checked)} disabled={isConverting} />
                    B standard to 7-string
                  </label>
                </div>
              </div>
            </div>

            {separateStems && (
              <div className="settings-card">
                <div className="settings-card-head">
                  <div>
                    <h2>Stem Server</h2>
                    <p>Local Demucs setup and optional remote server settings.</p>
                  </div>
                  <span className={`server-badge ${stemServerBadge(stemServerStatus, isStartingStemServer).toLowerCase()}`}>{stemServerBadge(stemServerStatus, isStartingStemServer)}</span>
                </div>
                <div className="stem-settings">
                  <label>
                    Model
                    <select value={demucsModel} onChange={(event) => setDemucsModel(event.target.value)} disabled={isConverting || stemServerStatus.processRunning || stemServerBusy}>
                      {(demucsModels.length ? demucsModels : [{ id: "htdemucs_6s", name: "HTDemucs 6-source", size: "approx. 270 MB", description: "Best FeedForge default." }]).map((model) => (
                        <option key={model.id} value={model.id}>{model.name} ({model.size}) - {modelStatusLabel(model)}</option>
                      ))}
                    </select>
                  </label>
                  <div className="demucs-model-note">
                    <strong>{modelStatusLabel(selectedDemucsModel(demucsModels, demucsModel))} - {selectedDemucsModel(demucsModels, demucsModel)?.size || "Model size varies"}</strong>
                    <span>{selectedDemucsModel(demucsModels, demucsModel)?.description || "The selected model downloads on first local server start."}</span>
                    <em>{selectedDemucsModel(demucsModels, demucsModel)?.installed ? "Starting this model should reuse the local checkpoint." : `Cache checked in ${demucsModelRoot || "the selected install folder"} and the legacy Torch cache.`}</em>
                  </div>
                  <div className="demucs-install-row">
                    <label>
                      Install folder
                      <input value={demucsInstallDir} onChange={(event) => setDemucsInstallDir(event.target.value)} placeholder="Choose where Demucs, caches, and models are stored" disabled={isConverting || stemServerStatus.processRunning || stemServerBusy} />
                    </label>
                    <button onClick={chooseDemucsInstallDir} disabled={isConverting || stemServerStatus.processRunning || stemServerBusy}>
                      <FolderOpen size={17} />
                      Browse
                    </button>
                  </div>
                  <label>
                    Demucs server
                    <input value={demucsUrl} onChange={(event) => setDemucsUrl(event.target.value)} placeholder="Auto from FeedBack, or http://127.0.0.1:8000" disabled={isConverting} />
                  </label>
                  <label>
                    API key
                    <input value={demucsApiKey} onChange={(event) => setDemucsApiKey(event.target.value)} placeholder="Optional" type="password" disabled={isConverting} />
                  </label>
                  <div className="local-stem-server">
                    <div className={`server-state ${stemServerStatus.healthy ? "ready" : stemServerBusy ? "starting" : ""}`}>
                      <Server size={17} />
                      <div>
                        <strong>{stemServerStatus.healthy ? "Local stem server ready" : stemServerBusy ? "Installing or starting stem server" : stemServerStatus.running ? "Stem server reachable, Demucs not ready" : "Local stem server not running"}</strong>
                        <span>{stemServerStatus.healthy ? `${stemServerStatus.url} - ${stemServerStatus.model || demucsModel} is ready for conversions.` : stemServerStatus.running ? "The port is reachable, but health did not pass. Open the debug log if this stays unresolved." : selectedDemucsModel(demucsModels, demucsModel)?.installed ? "Selected model is installed. Starting should not download it again." : "First start downloads Python dependencies and the selected model into the install folder."}</span>
                      </div>
                    </div>
                    <div className="server-actions">
                      <button onClick={startLocalStemServer} disabled={isConverting || stemServerBusy}>
                        {stemServerBusy ? <RotateCw className="spin" size={17} /> : <Download size={17} />}
                        {stemServerStatus.healthy ? "Use local stem server" : "Install/start local stem server"}
                      </button>
                      {(stemServerStatus.processRunning || stemServerBusy) && (
                        <button className="ghost" onClick={stopLocalStemServer} disabled={isConverting}>
                          <Power size={17} />
                          Stop
                        </button>
                      )}
                    </div>
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
                <Queue items={filtered} selectedId={selected?.id} onSelect={setSelectedId} />
              </div>
              <Inspector item={selected} />
            </section>
          </>
        )}
      </main>
    </div>
  );
}

function stemServerBadge(status, isStarting) {
  if (status.healthy) return "Running";
  if (status.starting || isStarting) return "Starting";
  if (status.running) return "Unhealthy";
  return "Stopped";
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

function modelStatusLabel(model) {
  if (!model) return "Unknown";
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

function Queue({ items, selectedId, onSelect }) {
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
  const rigBuilder = preview?.rig_builder || [];
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
                  <span>{arrangement.notes + arrangement.chords} events</span>
                </div>
              ))}
            </div>
          </section>
        </>
      ) : (
        <ToneInspector arrangements={arrangements} tones={tones} rigBuilder={rigBuilder} />
      )}
    </aside>
  );
}

function ToneInspector({ arrangements, tones, rigBuilder }) {
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
        <h2>Tone Export</h2>
        <span>{countToneDefinitions(tones)} definitions</span>
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

          <ToneRouteSummary definitions={active.definitions || []} rigBuilder={rigBuilder} />

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
            <h3>Source Tones to FeedBack Audio</h3>
            <div className="tone-definitions">
              {(active.definitions || []).map((definition) => (
                <div className="tone-definition" key={definition.key || definition.name}>
                  <div className="tone-definition-head">
                    <div>
                      <strong>{definition.name || "Unnamed tone"}</strong>
                      <span>PSARC key: {definition.key || "no-key"}</span>
                    </div>
                    <RouteBadge mapping={findRigBuilderMapping(rigBuilder, definition)} />
                  </div>
                  <div className="gear-list">
                    {(definition.gear || []).length === 0 && <span className="muted-text">No gear chain found.</span>}
                    {(definition.gear || []).map((gear) => (
                      <div className="gear-chip" key={`${definition.key}-${gear.slot}-${gear.key}`}>
                        <span>{gear.slot}</span>
                        <strong>{gear.key || gear.type || "Unknown gear"}</strong>
                        <small>{gear.category || gear.type || "mapped by key"} - {gear.knobs} knobs</small>
                        <GearRecommendation gear={gear} />
                        <KnobValues values={gear.knob_values} />
                      </div>
                    ))}
                  </div>
                  <RigBuilderRoute mapping={findRigBuilderMapping(rigBuilder, definition)} />
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function ToneRouteSummary({ definitions, rigBuilder }) {
  const total = definitions.length;
  const mapped = definitions.filter((definition) => findRigBuilderMapping(rigBuilder, definition)?.status === "ready").length;
  const partial = definitions.filter((definition) => findRigBuilderMapping(rigBuilder, definition)?.status === "partial").length;
  const missing = Math.max(0, total - mapped - partial);
  return (
    <div className="tone-route-summary">
      <div>
        <strong>{mapped}/{total}</strong>
        <span>Ready routes</span>
      </div>
      <div>
        <strong>{partial}</strong>
        <span>Partial</span>
      </div>
      <div>
        <strong>{missing}</strong>
        <span>Not seeded</span>
      </div>
    </div>
  );
}

function GearRecommendation({ gear }) {
  if (!gear.recommendation && !gear.recommendation_kind) return null;
  return (
    <div className="gear-recommendation">
      <b>{gear.recommendation_kind || "Mapped"}</b>
      <span>{gear.recommendation || "No named target"}</span>
      {gear.recommendation_detail && <small>{gear.recommendation_detail}</small>}
    </div>
  );
}

function KnobValues({ values }) {
  const entries = Object.entries(values || {}).slice(0, 6);
  if (!entries.length) return null;
  return (
    <div className="knob-values">
      {entries.map(([key, value]) => (
        <span key={key}>{shortKnob(key)} {formatKnob(value)}</span>
      ))}
    </div>
  );
}

function shortKnob(value) {
  return String(value).replace(/^[A-Za-z0-9]+_/, "");
}

function formatKnob(value) {
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  return String(value);
}

function RouteBadge({ mapping }) {
  if (!mapping) return <span className="route-badge missing">No local route</span>;
  return <span className={`route-badge ${mapping.status}`}>{routeStatusText(mapping.status)}</span>;
}

function RigBuilderRoute({ mapping }) {
  if (!mapping) {
    return (
      <div className="rig-route missing">
        <strong>FeedBack audio route</strong>
        <span>No local route has been written for this tone yet. Convert with Include tones enabled to seed it for FeedBack.</span>
      </div>
    );
  }
  return (
    <div className={`rig-route ${mapping.status}`}>
      <div className="rig-route-head">
        <strong>FeedBack audio route</strong>
        <code>{mapping.preset || mapping.tone_key}</code>
      </div>
      <div className="route-stages">
        {(mapping.stages || []).map((stage, index) => (
          <div className={`route-stage ${stage.status}`} key={`${mapping.tone_key}-${stage.slot}-${stage.gear}-${index}`}>
            <span>{stage.slot}</span>
            <strong>{stage.gear || "Unknown gear"}</strong>
            <small>{stage.kind.toUpperCase()} - {stage.asset || "missing assignment"}</small>
            {stage.kind === "vst" && <em>{stage.state_applied ? "RS knobs applied" : "Default plugin settings"}</em>}
          </div>
        ))}
      </div>
    </div>
  );
}

function findRigBuilderMapping(mappings, definition) {
  const candidates = [definition?.key, definition?.name].filter(Boolean).map((item) => String(item).trim().toLowerCase());
  return (mappings || []).find((mapping) => candidates.includes(String(mapping.tone_key || "").trim().toLowerCase())) || null;
}

function routeStatusText(status) {
  if (status === "ready") return "Mapped";
  if (status === "partial") return "Partial";
  if (status === "bypassed") return "Bypassed";
  return "Missing";
}

function countToneDefinitions(tones) {
  return (tones || []).reduce((total, arrangement) => total + ((arrangement.definitions || []).length), 0);
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
