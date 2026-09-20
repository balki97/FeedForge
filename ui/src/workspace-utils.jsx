
import { AlertTriangle, Check, Play, RotateCw, XCircle } from "lucide-react";
import { SETTINGS_KEY, DEFAULT_AUDIT_CRITERIA } from "./settings.mjs";
import { joinPath } from "./output-path.mjs";
export { joinPath } from "./output-path.mjs";
export function parseAuthors(value) {
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

export function formatBytes(value) {
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes <= 0) return "unknown size";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function isSongPackage(filePath) {
  const lower = String(filePath || "").toLowerCase();
  return lower.endsWith(".psarc") || lower.endsWith(".feedpak");
}

export function fileType(filePath) {
  return String(filePath || "").toLowerCase().endsWith(".feedpak") ? "feedpak" : "psarc";
}

export function isRs1SongsArchive(filePath) {
  return basename(String(filePath || "")).toLowerCase() === "songs.psarc";
}

export function countToneDefinitions(tones) {
  return (tones || []).reduce((total, arrangement) => total + ((arrangement.definitions || []).length), 0);
}

export function countToneChanges(tones) {
  return (tones || []).reduce((total, arrangement) => total + ((arrangement.changes || []).length), 0);
}

export function toneTimelineDuration(changes) {
  const times = (changes || []).map((change) => Number(change.time || 0)).filter(Number.isFinite);
  return Math.max(1, ...times);
}

export function ReadyLine({ ok, text, muted = false }) {
  return <li className={`${muted ? "muted" : ""} ${ok ? "ready-ok" : "ready-missing"}`}>{ok ? <Check size={16} /> : <XCircle size={16} />} {text}</li>;
}

export function StatusIcon({ status }) {
  if (status === "converted") return <Check className="status-ok" size={18} />;
  if (status === "failed" || status === "needs-review") return <AlertTriangle className="status-warn" size={18} />;
  if (status === "converting" || status === "inspecting") return <RotateCw className="spin status-blue" size={18} />;
  return <Play className="status-blue" size={18} />;
}

export function statusText(status) {
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

export function sortedOptions(values) {
  return Array.from(values)
    .filter(Boolean)
    .sort((left, right) => left.localeCompare(right, undefined, { sensitivity: "base" }));
}

export function arrangementTuningLabels(arrangements) {
  const labels = new Set();
  for (const arrangement of arrangements || []) {
    labels.add(tuningLabel(arrangement?.tuning));
  }
  return Array.from(labels).filter(Boolean);
}

export function tuningLabel(tuning) {
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

export function basename(filePath) {
  return filePath.split(/[\\/]/).pop();
}

export function withoutExtension(fileName) {
  return fileName.replace(/\.[^.]+$/, "");
}

export function outputPathForItem(item, outputDir, layout, sourceRoot, nameFormat = "source", customTemplate = "{artist} - {title}") {
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

export function reserveBatchOutputPaths(items, outputDir, layout, batchSourceRoot, nameFormat, customTemplate, initiallyReserved = []) {
  const reserved = new Map();
  const used = new Set((initiallyReserved || []).filter(Boolean).map((filePath) => normalizePath(filePath).toLowerCase()));
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

export function uniqueOutputPath(filePath, used) {
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

export function editedFeedpakPath(item, outputDir) {
  const sourceName = withoutExtension(item?.name || basename(item?.path || "song.feedpak"));
  const folder = outputDir || parentDir(item?.path || "") || "";
  const stamp = new Date().toISOString().replace(/[-:T.Z]/g, "").slice(0, 14);
  return joinPath(folder, `${safePathSegment(sourceName, "song")}.edited-${stamp}.feedpak`);
}

export function outputFileNameForItem(item, format, customTemplate) {
  const meta = outputNameMetadata(item);
  const partsByFormat = {
    source: [meta.source],
    "artist-title": [meta.artist, meta.title],
    "title-artist": [meta.title, meta.artist],
    "artist-album-title": [meta.artist, meta.album, meta.title],
    "artist-title-parts": [meta.artist, meta.title, meta.parts]
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

export function outputNameTemplateForFormat(format, customTemplate) {
  if (format === "custom") return customTemplate || "{source}";
  return {
    source: "{source}",
    "artist-title": "{artist} - {title}",
    "title-artist": "{title} - {artist}",
    "artist-album-title": "{artist} - {album} - {title}",
    "artist-title-parts": "{artist} - {title} - {parts}"
  }[format] || "{source}";
}

export function outputNameMetadata(item) {
  const source = withoutExtension(item?.name || basename(item?.path || "song.psarc"));
  return {
    source,
    artist: item?.preview?.artist || "Unknown Artist",
    title: item?.preview?.title || source,
    album: item?.preview?.album || "",
    year: item?.preview?.year || "",
    parts: arrangementPartsCode(item?.preview?.arrangements)
  };
}

export function renderNameTemplate(template, metadata) {
  return String(template || "{source}").replace(/\{(artist|title|album|year|source|parts)\}/gi, (_match, key) => metadata[key.toLowerCase()] || "");
}

export function arrangementPartsCode(arrangements) {
  const labels = (arrangements || []).map((arrangement) => (
    `${arrangement?.type || ""} ${arrangement?.id || ""} ${arrangement?.name || ""}`.toLowerCase()
  ));
  return [
    ["bass", "B"],
    ["lead", "L"],
    ["rhythm", "R"],
    ["vocal", "V"],
    ["combo", "C"]
  ].filter(([needle]) => labels.some((label) => label.includes(needle))).map(([, code]) => code).join("");
}

export function relativeParentDir(filePath, rootPath) {
  const parent = parentDir(filePath);
  if (!parent || !rootPath) return "";
  const normalizedParent = normalizePath(parent);
  const normalizedRoot = normalizePath(rootPath);
  if (normalizedParent === normalizedRoot) return "";
  const prefix = `${normalizedRoot}\\`;
  if (!normalizedParent.toLowerCase().startsWith(prefix.toLowerCase())) return "";
  return normalizedParent.slice(prefix.length);
}

export function commonAncestorDir(paths) {
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
  if (String(paths[0]).startsWith("/")) return "/" + parts.join("/");
  return (String(paths[0]).startsWith("\\\\") ? "\\\\" : "") + parts.join("\\");
}

export function normalizePath(filePath) {
  return String(filePath || "").replace(/[\\/]+/g, "\\").replace(/[\\/]$/, "");
}

export function safePathSegment(value, fallback = "Unknown Artist") {
  const normalized = String(value || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "");
  const cleaned = (normalized || String(value || ""))
    .replace(/[<>:"/\\|?*\x00-\x1F]/g, "_")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/[. ]+$/g, "");
  return cleaned || fallback;
}

export function normalizePathKey(filePath) {
  return String(filePath || "").replaceAll("/", "\\").toLowerCase();
}

export function duration(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  const minutes = Math.floor(value / 60);
  const seconds = Math.floor(value % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
}

export function readSettings() {
  try {
    return JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}");
  } catch {
    return {};
  }
}

export function normalizeAuditCriteria(value) {
  return { ...DEFAULT_AUDIT_CRITERIA, ...(value && typeof value === "object" ? value : {}) };
}

export function writeSettings(settings) {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify({ ...readSettings(), ...settings }));
}

export function parentDir(filePath) {
  if (!filePath || typeof filePath !== "string") return null;
  const normalized = filePath.replace(/[\\/]+$/, "");
  const index = Math.max(normalized.lastIndexOf("\\"), normalized.lastIndexOf("/"));
  if (index === 0) return normalized[0];
  if (index === 2 && /^[a-z]:/i.test(normalized)) return normalized.slice(0, 3);
  return index > 0 ? normalized.slice(0, index) : normalized;
}
