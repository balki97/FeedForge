import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertTriangle,
  Check,
  Download,
  FolderOpen,
  Guitar,
  ImageIcon,
  Play,
  Plus,
  RotateCw,
  Search,
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
  const [conversionWorkers, setConversionWorkers] = useState(DEFAULT_CONVERSION_WORKERS);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
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
    writeSettings({ outputDir, lastSourcePath, includeTones });
  }, [outputDir, lastSourcePath, includeTones]);

  useEffect(() => {
    return api.onDroppedPaths(async (paths) => {
      const expanded = await api.expandPaths(paths);
      rememberSourcePath(paths[0]);
      addFiles(expanded);
    });
  }, []);

  const selected = items.find((item) => item.id === selectedId) || items[0] || null;
  const filtered = items.filter((item) => {
    const haystack = `${item.preview?.title || item.name} ${item.preview?.artist || ""}`.toLowerCase();
    const matchesQuery = haystack.includes(query.toLowerCase());
    const matchesFilter =
      filter === "all" ||
      (filter === "ready" && ["ready", "converted"].includes(item.status)) ||
      (filter === "issues" && ["failed", "needs-review"].includes(item.status)) ||
      (filter === "converted" && item.status === "converted");
    return matchesQuery && matchesFilter;
  });

  const stats = useMemo(() => ({
    total: items.length,
    ready: items.filter((item) => item.status === "ready" || item.status === "converted").length,
    converted: items.filter((item) => item.status === "converted").length,
    failed: items.filter((item) => item.status === "failed").length
  }), [items]);

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
    const paths = await api.pickFolder({ defaultPath: lastSourcePath || outputDir || undefined });
    rememberSourcePath(paths[0]);
    addFiles(paths);
  }

  async function chooseOutput() {
    const folder = await api.pickOutput({ defaultPath: outputDir || lastSourcePath || undefined });
    if (folder) setOutputDir(folder);
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
        includeTones
      });
      if (!result.ok) {
        updateItem(item.id, { status: "failed", error: result.error });
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
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search imported songs" />
          </div>
          <button onClick={chooseFiles}><Plus size={17} /> Add PSARCs</button>
          <button onClick={chooseFolder}><FolderOpen size={17} /> Add folder</button>
          <button onClick={chooseOutput}><FolderOpen size={17} /> Output</button>
          <label className="select-control">
            Workers
            <select value={conversionWorkers} onChange={(event) => setConversionWorkers(Number(event.target.value))} disabled={isConverting}>
              {[1, 2, 3, 4, 5, 6].map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
          <div className="filter-pills">
            <button className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>All</button>
            <button className={filter === "ready" ? "active" : ""} onClick={() => setFilter("ready")}>Ready</button>
            <button className={filter === "issues" ? "active" : ""} onClick={() => setFilter("issues")}>Issues</button>
            <button className={filter === "converted" ? "active" : ""} onClick={() => setFilter("converted")}>Converted</button>
          </div>
          <label className="toggle"><input type="checkbox" checked={overwrite} onChange={(event) => setOverwrite(event.target.checked)} /> Overwrite</label>
          <label className="toggle"><input type="checkbox" checked={includeTones} onChange={(event) => setIncludeTones(event.target.checked)} disabled={isConverting} /> Include tones</label>
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
      </main>
    </div>
  );
}

function Metric({ label, value, tone = "" }) {
  return (
    <div className={`metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
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
  const preview = item?.preview;
  const cover = preview?.cover_path ? `file:///${preview.cover_path.replaceAll("\\", "/")}` : null;
  const arrangements = preview?.arrangements || [];
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
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="panel-title">
          <h2>Readiness</h2>
          <span>{item ? statusText(item.status) : "Waiting"}</span>
        </div>
        <ul className="readiness">
          <ReadyLine ok={!!preview} text="Package metadata inspected" />
          <ReadyLine ok={!!cover} text="Cover image detected" />
          <ReadyLine ok={arrangements.length > 0} text={`${arrangements.length || 0} playable arrangement${arrangements.length === 1 ? "" : "s"}`} />
          <ReadyLine ok={!!preview?.lyrics} text={preview?.lyrics ? `${preview.lyrics} lyric timing events` : "Lyrics optional"} muted={!preview?.lyrics} />
        </ul>
        {item?.error && <div className="error-box"><AlertTriangle size={17} /> {item.error}</div>}
      </section>

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
    </aside>
  );
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

function basename(filePath) {
  return filePath.split(/[\\/]/).pop();
}

function withoutExtension(fileName) {
  return fileName.replace(/\.[^.]+$/, "");
}

function duration(value) {
  if (!value) return "-";
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
