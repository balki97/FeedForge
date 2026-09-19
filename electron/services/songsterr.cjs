const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const { parseCoreResponse } = require("./core-response.cjs");

function validateUrl(value) {
  if (typeof value !== "string" || value.length > 2048) throw new Error("Paste a Songsterr tab link.");
  const url = new URL(value);
  if (url.protocol !== "https:" || !["songsterr.com", "www.songsterr.com"].includes(url.hostname) ||
      url.username || url.password || (url.port && url.port !== "443") || !url.pathname.startsWith("/a/wsa/")) {
    throw new Error("Paste an HTTPS Songsterr tab link.");
  }
  return value;
}

function outputPayload(payload) {
  if (!payload || typeof payload !== "object") throw new Error("Missing song details.");
  validateUrl(payload.url);
  if (!Array.isArray(payload.selected_parts) || !payload.selected_parts.length ||
      payload.selected_parts.some(id => !Number.isInteger(id) || id < 0)) throw new Error("Select valid arrangements.");
  const name = payload.output_name;
  if (typeof name !== "string" || !name.toLowerCase().endsWith(".feedpak") ||
      /[<>:"/\\|?*\x00-\x1f]/.test(name) || name.length > 220 ||
      /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(name)) throw new Error("Choose a valid FeedPak filename.");
  if (typeof payload.output_dir !== "string" || !path.isAbsolute(payload.output_dir) ||
      !fs.statSync(payload.output_dir).isDirectory()) throw new Error("Choose an existing output folder.");
  let output = path.join(payload.output_dir, name);
  const stem = name.slice(0, -8);
  for (let index = 2; fs.existsSync(output); index++) output = path.join(payload.output_dir, `${stem} (${index}).feedpak`);
  return { ...payload, output_path: output };
}

function registerSongsterr({ app, ipcMain, dialog, window, runConverter, terminateChildProcessTree, logDebug, removeTemporaryDirectory }) {
  let active = null;
  const previews = new Set();
  app.whenReady?.().then(() => {
    const root = app.getPath("temp");
    for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
      if (!entry.isDirectory() || !entry.name.startsWith("feedforge-songsterr-job-")) continue;
      const directory = path.join(root, entry.name);
      try {
        if (Date.now() - fs.statSync(directory).mtimeMs > 86400000) removeTemporaryDirectory(directory);
      } catch (error) { logDebug("songsterr.staleCleanupFailed", { message: error.message }); }
    }
  });
  app.on?.("before-quit", () => {
    if (active) { active.cancelled = true; terminateChildProcessTree(active.child); }
    for (const directory of previews) removeTemporaryDirectory(directory);
  });
  const send = (event, progress) => { if (!event.sender.isDestroyed()) event.sender.send("songsterr:progress", progress); };
  async function invoke(event, action, payload) {
    if (active) throw new Error("A Songsterr operation is already running.");
    const state = { cancelled: false, child: null };
    active = state;
    try {
      const payloads = action === "batch" ? payload : [payload];
      if (!Array.isArray(payloads) || !payloads.length || payloads.length > 200) throw new Error("Use between 1 and 200 songs per batch.");
      const results = [];
      for (let index = 0; index < payloads.length; index++) {
        if (state.cancelled) break;
        const operation = action === "batch" ? "create" : action;
        const title = payloads[index]?.title || "Song";
        let directory;
        let timer;
        try {
          const value = operation === "create" ? outputPayload(payloads[index]) : payloads[index];
          if (operation === "analyze") validateUrl(value);
          directory = fs.mkdtempSync(path.join(app.getPath("temp"), "feedforge-songsterr-job-"));
          if (operation === "preview") value.preview_dir = directory;
          const request = path.join(directory, "request.json");
          fs.writeFileSync(request, JSON.stringify({ action: operation, payload: value }));
          send(event, { stage: "Starting", title, index: index + 1, total: payloads.length });
          let timedOut = false;
          const result = await runConverter(["songsterr", request], {
            logOutput: false,
            env: { ...process.env, TEMP: directory, TMP: directory, TMPDIR: directory,
              SONGSTERR_NODE_PATH: process.execPath, ELECTRON_RUN_AS_NODE: "1" },
            onSpawn: child => {
              state.child = child;
              timer = setTimeout(() => { timedOut = true; terminateChildProcessTree(child); }, operation === "create" ? (value.separateStems ? 3600000 : 600000) : 180000);
            },
            onStderrLine: line => {
              if (!line.startsWith("FEEDFORGE_PROGRESS ")) return;
              try { send(event, { ...JSON.parse(line.slice(19)), index: index + 1, total: payloads.length }); } catch { /* diagnostics retain malformed lines */ }
            }
          });
          if (timedOut) throw new Error("Operation timed out. Retry, or choose local audio if downloading failed.");
          let response;
          try { response = parseCoreResponse(result.stdout); } catch { response = null; }
          if (!response?.ok || result.code !== 0) throw new Error(response?.error || "Songsterr operation failed. Open Settings → Diagnostics for the log.");
          if (operation === "preview") {
            response.result.audio_url = pathToFileURL(response.result.audio_path).href;
            previews.add(directory);
          }
          results.push({ ok: true, ...response.result });
          if (action !== "batch") return response.result;
        } catch (error) {
          logDebug("songsterr.failed", { action, title, message: error.message });
          if (action !== "batch") throw error;
          results.push({ ok: false, title, error: error.message });
        } finally {
          clearTimeout(timer);
          state.child = null;
          if (directory && !previews.has(directory)) removeTemporaryDirectory(directory);
        }
      }
      return { results, created: results.filter(r => r.ok).length, failed: results.filter(r => !r.ok).length, cancelled: state.cancelled, skipped: payloads.length - results.length };
    } finally { active = null; }
  }
  for (const action of ["analyze", "create", "batch", "lyrics", "preview"]) {
    ipcMain.handle(`songsterr:${action}`, (event, payload) => invoke(event, action, payload));
  }
  ipcMain.handle("songsterr:cancel", () => { if (active) active.cancelled = true; return { stopping: Boolean(active) }; });
  ipcMain.handle("songsterr:defaults", () => ({ output_dir: app.getPath("desktop") }));
  ipcMain.handle("songsterr:cover", async () => {
    const result = await dialog.showOpenDialog(window(), { properties: ["openFile"], filters: [{ name: "Artwork", extensions: ["png", "jpg", "jpeg", "webp"] }] });
    if (result.canceled || !result.filePaths[0]) return null;
    const file = result.filePaths[0];
    if (fs.statSync(file).size > 20 * 1024 * 1024) throw new Error("Choose an image smaller than 20 MB.");
    const mime = { ".png": "image/png", ".webp": "image/webp" }[path.extname(file).toLowerCase()] || "image/jpeg";
    return { path: file, preview: `data:${mime};base64,${(await fs.promises.readFile(file)).toString("base64")}` };
  });
  ipcMain.handle("songsterr:lrc", async event => {
    const result = await dialog.showOpenDialog(window(), { properties: ["openFile"], filters: [{ name: "Synchronized lyrics", extensions: ["lrc"] }] });
    return result.canceled || !result.filePaths[0] ? null : invoke(event, "lrc", result.filePaths[0]);
  });
}

module.exports = { registerSongsterr, validateUrl, outputPayload };
