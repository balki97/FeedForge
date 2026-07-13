const { app, BrowserWindow, Menu, dialog, ipcMain, shell } = require("electron");
const { spawn, execFileSync } = require("child_process");
const fs = require("fs");
const http = require("http");
const https = require("https");
const path = require("path");

let mainWindow;
let inspectCacheRoot;
let debugLogPath;
let stemServerProcess = null;
let stemServerStarting = false;
let stemServerLog = [];
const DEBUG_LOG_MAX_BYTES = 2 * 1024 * 1024;
const LOCAL_STEM_SERVER_URL = "http://127.0.0.1:7865";
const GITHUB_REPO = "balki97/FeedForge";
const GITHUB_RELEASES_URL = `https://github.com/${GITHUB_REPO}/releases/latest`;
const GITHUB_LATEST_API_URL = `https://api.github.com/repos/${GITHUB_REPO}/releases/latest`;
const STEM_SERVER_LOG_LINES = 80;
const DEMUCS_MODELS = [
  {
    id: "htdemucs_6s",
    name: "HTDemucs 6-source",
    size: "approx. 270 MB",
    description: "Best FeedForge default from Demucs v4. Separates guitar, bass, drums, vocals, piano, and other.",
    signatures: ["5c90dfd2"]
  },
  {
    id: "htdemucs",
    name: "HTDemucs",
    size: "approx. 80 MB",
    description: "Official Demucs v4 hybrid transformer model. Faster and smaller; separates drums, bass, vocals, and other.",
    signatures: ["955717e8"]
  },
  {
    id: "htdemucs_ft",
    name: "HTDemucs fine-tuned",
    size: "approx. 80 MB",
    description: "Official fine-tuned Demucs v4 model. Better quality for many tracks; separates drums, bass, vocals, and other.",
    signatures: ["f7e0c4bc", "d12395a8", "92cfc3b6", "04573f0d"]
  },
  {
    id: "hdemucs_mmi",
    name: "Hybrid Demucs v3",
    size: "approx. 80 MB",
    description: "Older official hybrid Demucs model. Included for compatibility and sometimes faster CPU separation.",
    signatures: ["75fc33f5"]
  },
  {
    id: "mdx",
    name: "MDX",
    size: "approx. 150 MB",
    description: "Official MDX-Net model family from Demucs. Alternative 4-source split that can be faster on some machines.",
    signatures: ["0d19c1c6", "7ecf8ec1", "c511e2ab", "7d865c68"]
  },
  {
    id: "mdx_extra",
    name: "MDX Extra",
    size: "approx. 150 MB",
    description: "MDX model trained with extra data. Can outperform HTDemucs on some mixes, but still 4-source only.",
    signatures: ["e51eebcc", "a1d90b5c", "5d2d6c55", "c5cba043"]
  },
  {
    id: "bs_roformer_sw",
    name: "BS-RoFormer-SW",
    size: "remote server",
    description: "FeedBack Demucs server model. Six-source split returned as FLAC when the remote server supports audio-separator/RoFormer.",
    signatures: [],
    remoteOnly: true
  }
];

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1500,
    height: 930,
    minWidth: 1180,
    minHeight: 760,
    backgroundColor: "#090f18",
    title: `FeedForge ${app.getVersion()}`,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  mainWindow.once("ready-to-show", () => mainWindow.show());

  if (!app.isPackaged && process.env.VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL);
    return;
  }

  if (!app.isPackaged) {
    const builtIndex = path.join(app.getAppPath(), "desktop-dist", "index.html");
    if (fs.existsSync(builtIndex)) {
      mainWindow.loadFile(builtIndex);
      return;
    }
    mainWindow.loadURL("http://127.0.0.1:5173");
    return;
  }

  mainWindow.loadFile(path.join(process.resourcesPath, "app.asar", "desktop-dist", "index.html"));
}

app.whenReady().then(() => {
  initializeDebugLog();
  logDebug("app.ready", {
    version: app.getVersion(),
    packaged: app.isPackaged,
    appPath: app.getAppPath(),
    userData: app.getPath("userData"),
    resourcesPath: process.resourcesPath,
    platform: process.platform,
    arch: process.arch
  });
  cleanupStalePortableArtifacts();
  inspectCacheRoot = path.join(app.getPath("temp"), "feedforge-inspect-cache");
  resetDirectory(inspectCacheRoot);
  createWindow();
});
app.whenReady().then(() => Menu.setApplicationMenu(null));
app.on("before-quit", () => {
  logDebug("app.beforeQuit");
  stopStemServer();
  if (inspectCacheRoot) removeDirectory(inspectCacheRoot);
});
app.on("render-process-gone", (_event, webContents, details) => {
  logDebug("app.renderProcessGone", {
    reason: details.reason,
    exitCode: details.exitCode,
    url: webContents?.getURL?.() || ""
  });
});
process.on("uncaughtException", (error) => {
  logDebug("process.uncaughtException", errorToLog(error));
});
process.on("unhandledRejection", (reason) => {
  logDebug("process.unhandledRejection", errorToLog(reason));
});
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

ipcMain.handle("dialog:pickPsarc", async (_event, options = {}) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: "Choose PSARC CDLC files",
    defaultPath: validDefaultPath(options.defaultPath),
    properties: ["openFile", "multiSelections"],
    filters: [{ name: "PSARC files", extensions: ["psarc"] }]
  });
  const paths = result.canceled ? [] : result.filePaths;
  logDebug("dialog.pickPsarc", { count: paths.length, defaultPath: options.defaultPath || "" });
  return paths;
});

ipcMain.handle("dialog:pickFolder", async (_event, options = {}) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: "Choose a CDLC folder",
    defaultPath: validDefaultPath(options.defaultPath),
    properties: ["openDirectory"]
  });
  if (result.canceled || !result.filePaths[0]) return [];
  const files = await findPsarcFiles(result.filePaths[0]);
  logDebug("dialog.pickFolder", { folder: result.filePaths[0], count: files.length });
  return files;
});

ipcMain.handle("dialog:pickFolderWithRoot", async (_event, options = {}) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: "Choose a CDLC folder",
    defaultPath: validDefaultPath(options.defaultPath),
    properties: ["openDirectory"]
  });
  if (result.canceled || !result.filePaths[0]) return { folder: "", files: [] };
  const folder = result.filePaths[0];
  const files = await findPsarcFiles(folder);
  logDebug("dialog.pickFolderWithRoot", { folder, count: files.length });
  return { folder, files };
});

ipcMain.handle("files:expandPaths", async (_event, inputPaths) => {
  const found = [];
  for (const inputPath of inputPaths || []) {
    try {
      const stat = await fs.promises.stat(inputPath);
      if (stat.isDirectory()) {
        found.push(...await findPsarcFiles(inputPath));
      } else if (stat.isFile() && inputPath.toLowerCase().endsWith(".psarc")) {
        found.push(inputPath);
      }
    } catch {
      // Ignore paths the OS no longer exposes.
    }
  }
  logDebug("files.expandPaths", { inputCount: (inputPaths || []).length, outputCount: found.length });
  return found;
});

ipcMain.handle("dialog:pickOutput", async (_event, options = {}) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: "Choose output folder",
    defaultPath: validDefaultPath(options.defaultPath),
    properties: ["openDirectory", "createDirectory"]
  });
  const folder = result.canceled ? null : result.filePaths[0];
  logDebug("dialog.pickOutput", { selected: folder || "" });
  return folder;
});

ipcMain.handle("dialog:pickDemucsInstallDir", async (_event, options = {}) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: "Choose Demucs install folder",
    defaultPath: validDefaultPath(options.defaultPath) || defaultDemucsInstallRoot(),
    properties: ["openDirectory", "createDirectory"]
  });
  const folder = result.canceled ? null : result.filePaths[0];
  logDebug("dialog.pickDemucsInstallDir", { selected: folder || "" });
  return folder;
});

ipcMain.handle("dialog:pickPythonExecutable", async (_event, options = {}) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: "Choose python.exe",
    defaultPath: validDefaultPath(options.defaultPath) || "C:\\Program Files",
    properties: ["openFile"],
    filters: [{ name: "Python executable", extensions: ["exe"] }]
  });
  const filePath = result.canceled ? null : result.filePaths[0];
  logDebug("dialog.pickPythonExecutable", { selected: filePath || "" });
  return filePath;
});

ipcMain.handle("converter:inspect", async (_event, inputPath, options = {}) => {
  logDebug("converter.inspect.start", {
    inputPath
  });
  const coverDir = createInspectionFolder(inputPath);
  const result = await runConverter([
    "--inspect-json",
    "--inspect-cover-dir",
    coverDir,
    inputPath
  ]);
  const parsed = parseJson(result.stdout);
  if (!parsed || !parsed.ok) {
    logDebug("converter.inspect.failed", {
      inputPath,
      code: result.code,
      stdoutTail: tail(result.stdout),
      stderrTail: tail(result.stderr),
      diagnostics: result.diagnostics
    });
    return {
      ok: false,
      error: parsed?.error || result.stderr || "Inspection failed",
      diagnostics: result.diagnostics
    };
  }
  logDebug("converter.inspect.ok", {
    inputPath,
    title: parsed.preview?.title || "",
    artist: parsed.preview?.artist || "",
    arrangements: parsed.preview?.arrangements?.length || 0,
    tones: parsed.preview?.tones?.length || 0,
    warnings: parsed.preview?.warnings || []
  });
  return parsed;
});

ipcMain.handle("converter:convert", async (_event, payload) => {
  logDebug("converter.convert.start", {
    inputPath: payload.inputPath,
    outputPath: payload.outputPath || "",
    overwrite: Boolean(payload.overwrite),
    bStandardTo7String: Boolean(payload.bStandardTo7String),
    separateStems: Boolean(payload.separateStems),
    keepFullStem: payload.keepFullStem !== false,
    hasDemucsUrl: Boolean(payload.demucsUrl),
    demucsModel: payload.demucsModel || "",
    demucsStems: Array.isArray(payload.demucsStems) ? payload.demucsStems : []
  });
  const args = [payload.inputPath];
  if (payload.outputPath) args.push("-o", payload.outputPath);
  if (payload.overwrite) args.push("--overwrite");
  if (payload.bStandardTo7String) args.push("--b-standard-to-7-string");
  if (payload.separateStems) args.push("--separate-stems");
  if (payload.keepFullStem === false) args.push("--no-full-stem");
  if (payload.demucsUrl) args.push("--demucs-url", payload.demucsUrl);
  if (payload.demucsApiKey) args.push("--demucs-api-key", payload.demucsApiKey);
  if (payload.demucsModel) args.push("--demucs-model", payload.demucsModel);
  if (Array.isArray(payload.demucsStems) && payload.demucsStems.length) {
    args.push("--demucs-stems", payload.demucsStems.join(","));
  }
  const result = await runConverter(args);
  const outputPaths = [...result.stdout.matchAll(/^wrote\s+(.+)$/gim)].map((match) => match[1].trim()).filter(Boolean);
  const warnings = [...`${result.stdout}\n${result.stderr}`.matchAll(/^warning:\s+(.+)$/gim)].map((match) => match[1].trim()).filter(Boolean);
  const outputMatch = outputPaths[0] || null;
  logDebug(result.code === 0 ? "converter.convert.ok" : "converter.convert.failed", {
    inputPath: payload.inputPath,
    outputPath: outputMatch || payload.outputPath || "",
    outputCount: outputPaths.length,
    code: result.code,
    warnings,
    stdoutTail: tail(result.stdout),
    stderrTail: tail(result.stderr),
    diagnostics: result.diagnostics
  });
  return {
    ok: result.code === 0,
    outputPath: outputMatch,
    outputPaths,
    warnings,
    stdout: result.stdout,
    stderr: result.stderr,
    diagnostics: result.diagnostics,
    error: result.code === 0 ? null : result.stderr || result.stdout || "Conversion failed"
  };
});

ipcMain.handle("stemServer:status", async () => {
  return stemServerStatus();
});

ipcMain.handle("stemServer:models", async (_event, options = {}) => {
  const installRoot = demucsInstallRoot(options.installDir);
  return {
    defaultInstallDir: defaultDemucsInstallRoot(),
    installRoot,
    setup: await demucsSetupState(installRoot),
    devices: await demucsDeviceOptions(installRoot),
    models: modelInstallStates(installRoot)
  };
});

ipcMain.handle("stemServer:start", async (_event, options = {}) => {
  return startStemServer(options);
});

ipcMain.handle("stemServer:stop", async () => {
  await stopStemServer({ forcePort: true });
  return stemServerStatus();
});

ipcMain.handle("app:version", async () => app.getVersion());

ipcMain.handle("app:debugLogInfo", async () => {
  return debugLogInfo();
});

ipcMain.handle("app:openDebugLog", async () => {
  const info = debugLogInfo();
  if (info.path && fs.existsSync(info.path)) {
    await shell.openPath(info.path);
    return { ok: true, path: info.path };
  }
  if (info.folder) {
    fs.mkdirSync(info.folder, { recursive: true });
    await shell.openPath(info.folder);
    return { ok: true, path: info.folder };
  }
  return { ok: false, error: "Debug log path is not available." };
});

ipcMain.handle("app:openDebugLogFolder", async () => {
  const info = debugLogInfo();
  if (!info.folder) return { ok: false, error: "Debug log folder is not available." };
  fs.mkdirSync(info.folder, { recursive: true });
  await shell.openPath(info.folder);
  return { ok: true, path: info.folder };
});

ipcMain.handle("app:pythonInfo", async (_event, options = {}) => {
  return pythonInfo(options);
});

ipcMain.handle("app:openPythonDownload", async () => {
  await shell.openExternal("https://www.python.org/downloads/windows/");
  return { ok: true };
});

ipcMain.handle("app:openSupport", async () => {
  await shell.openExternal("https://ko-fi.com/feedforge");
  return { ok: true };
});

ipcMain.handle("updates:check", async () => {
  return checkForUpdates();
});

ipcMain.handle("updates:openLatest", async (_event, url) => {
  const target = safeGithubReleaseUrl(url) || GITHUB_RELEASES_URL;
  await shell.openExternal(target);
  return { ok: true, url: target };
});

ipcMain.on("app:rendererError", (_event, payload = {}) => {
  logDebug("renderer.error", payload);
});

async function checkForUpdates() {
  const currentVersion = app.getVersion();
  try {
    const release = await requestJsonHttps(GITHUB_LATEST_API_URL, 5000);
    const latestVersion = normalizeVersion(release.tag_name || release.name || "");
    const latestUrl = safeGithubReleaseUrl(release.html_url) || GITHUB_RELEASES_URL;
    const available = latestVersion ? compareVersions(latestVersion, normalizeVersion(currentVersion)) > 0 : false;
    const payload = {
      ok: true,
      currentVersion,
      latestVersion: latestVersion || "",
      updateAvailable: available,
      releaseUrl: latestUrl,
      releaseName: String(release.name || release.tag_name || latestVersion || "Latest release"),
      publishedAt: release.published_at || ""
    };
    logDebug("updates.check.ok", payload);
    return payload;
  } catch (error) {
    const payload = {
      ok: false,
      currentVersion,
      latestVersion: "",
      updateAvailable: false,
      releaseUrl: GITHUB_RELEASES_URL,
      error: error?.message || String(error || "Update check failed")
    };
    logDebug("updates.check.failed", payload);
    return payload;
  }
}

function requestJsonHttps(url, timeoutMs) {
  return new Promise((resolve, reject) => {
    const request = https.get(url, {
      timeout: timeoutMs,
      headers: {
        "Accept": "application/vnd.github+json",
        "User-Agent": `FeedForge/${app.getVersion()}`
      }
    }, (response) => {
      let body = "";
      response.setEncoding("utf8");
      response.on("data", (chunk) => { body += chunk; });
      response.on("end", () => {
        if (response.statusCode < 200 || response.statusCode >= 300) {
          reject(new Error(`GitHub returned ${response.statusCode}: ${body.slice(0, 200)}`));
          return;
        }
        try {
          const parsed = JSON.parse(body);
          if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
            reject(new Error("GitHub returned a non-object response."));
            return;
          }
          resolve(parsed);
        } catch (error) {
          reject(new Error(`GitHub returned invalid JSON: ${error.message}`));
        }
      });
    });
    request.on("timeout", () => request.destroy(new Error("Update check timed out.")));
    request.on("error", reject);
  });
}

function normalizeVersion(value) {
  const text = String(value || "").trim();
  const match = text.match(/v?(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?/);
  return match ? `${Number(match[1])}.${Number(match[2])}.${Number(match[3])}` : "";
}

function compareVersions(left, right) {
  const a = String(left || "0.0.0").split(".").map((part) => Number(part) || 0);
  const b = String(right || "0.0.0").split(".").map((part) => Number(part) || 0);
  for (let index = 0; index < 3; index += 1) {
    if ((a[index] || 0) > (b[index] || 0)) return 1;
    if ((a[index] || 0) < (b[index] || 0)) return -1;
  }
  return 0;
}

function safeGithubReleaseUrl(value) {
  if (typeof value !== "string" || !value.trim()) return "";
  try {
    const parsed = new URL(value);
    if (parsed.protocol !== "https:" || parsed.hostname !== "github.com") return "";
    if (!parsed.pathname.toLowerCase().startsWith(`/${GITHUB_REPO.toLowerCase()}/releases`)) return "";
    return parsed.toString();
  } catch {
    return "";
  }
}

async function startStemServer(options = {}) {
  const installRoot = demucsInstallRoot(options.installDir);
  const model = demucsModelId(options.model);
  const modelInfo = DEMUCS_MODELS.find((item) => item.id === model);
  if (modelInfo?.remoteOnly) {
    return stemServerState({
      ok: false,
      healthy: false,
      running: false,
      error: `${modelInfo.name} is only available when using a compatible remote FeedBack Demucs server. Enter the remote URL and convert with stem separation enabled.`,
      model
    });
  }
  const device = demucsDeviceId(options.device);
  const concurrency = demucsConcurrency(options.concurrency);
  const pythonExe = pythonExecutablePath(options.pythonPath);
  const torchIndex = demucsTorchIndex(device);
  const existing = await stemServerStatus();
  if (existing.running || stemServerStarting) {
    const configChanged = existing.installRoot !== installRoot || existing.model !== model || existing.requestedDevice !== device || Number(existing.concurrency || 1) !== concurrency;
    if (existing.processRunning && configChanged) {
      await stopStemServer({ forcePort: true });
      await waitForStemServerStop(4500);
    } else if (existing.running && configChanged) {
      appendStemServerLog(`FeedForge: stopping current stem server model=${existing.model || "unknown"}`);
      await stopStemServer({ forcePort: true });
      const stopped = await waitForStemServerStop(4500);
      if (!stopped) {
        return stemServerState({
          ok: false,
          running: true,
          healthy: false,
          installRoot,
          model: existing.model || null,
          requestedDevice: existing.requestedDevice || null,
          concurrency: existing.concurrency || null,
          error: `Could not stop the current stem server on ${LOCAL_STEM_SERVER_URL}. Open Diagnostics, stop it, then start ${model} again.`
        });
      }
    } else {
      return { ...existing, starting: stemServerStarting, url: LOCAL_STEM_SERVER_URL };
    }
  }

  if (stemServerStarting) {
    return { ...existing, starting: stemServerStarting, url: LOCAL_STEM_SERVER_URL };
  }

  const scriptPath = stemServerLauncherPath();
  if (!scriptPath || !fs.existsSync(scriptPath)) {
    const error = `Local stem server launcher was not found: ${scriptPath || "unknown path"}`;
    logDebug("stemServer.start.missingLauncher", { scriptPath, error });
    return stemServerState({ ok: false, error });
  }

  stemServerStarting = true;
  stemServerLog = [];
  fs.mkdirSync(installRoot, { recursive: true });
  const runtimeRoot = path.join(installRoot, "runtime");
  const tempRoot = path.join(runtimeRoot, "temp");
  const storageRoot = path.join(runtimeRoot, "jobs");
  fs.mkdirSync(tempRoot, { recursive: true });
  fs.mkdirSync(storageRoot, { recursive: true });
  logDebug("stemServer.start", { scriptPath, installRoot, model, device, concurrency, torchIndex, hasPythonOverride: Boolean(pythonExe) });
  appendStemServerLog(`FeedForge: preparing local stem setup`);
  appendStemServerLog(`FeedForge: model=${model}, device=${device}, jobs=${concurrency}`);
  appendStemServerLog(`FeedForge: install folder ${installRoot}`);
  appendStemServerLog(`FeedForge: runtime folder ${runtimeRoot}`);
  if (pythonExe) appendStemServerLog(`FeedForge: using selected Python ${pythonExe}`);

  stemServerProcess = spawn("powershell.exe", [
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    scriptPath
  ], {
    cwd: path.dirname(scriptPath),
    env: {
      ...process.env,
      FEEDFORGE_DEMUCS_HOME: installRoot,
      FEEDFORGE_DEMUCS_MODEL: model,
      FEEDFORGE_DEMUCS_DEVICE: device,
      FEEDFORGE_DEMUCS_CONCURRENCY: String(concurrency),
      FEEDFORGE_PYTHON_EXE: pythonExe,
      FEEDFORGE_TORCH_INDEX: torchIndex,
      TORCH_HOME: path.join(installRoot, "model-cache", "torch"),
      XDG_CACHE_HOME: path.join(installRoot, "model-cache"),
      HF_HOME: path.join(installRoot, "model-cache", "huggingface"),
      PIP_CACHE_DIR: path.join(installRoot, "pip-cache"),
      TEMP: tempRoot,
      TMP: tempRoot
    },
    windowsHide: true
  });

  stemServerProcess.stdout.on("data", (chunk) => appendStemServerLog(chunk));
  stemServerProcess.stderr.on("data", (chunk) => appendStemServerLog(chunk));
  stemServerProcess.on("error", (error) => {
    stemServerStarting = false;
    appendStemServerLog(`\n${error.message}\n`);
    logDebug("stemServer.process.error", errorToLog(error));
  });
  stemServerProcess.on("close", (code, signal) => {
    stemServerStarting = false;
    appendStemServerLog(`\nStem server exited with code ${code ?? "null"} signal ${signal || "none"}.\n`);
    logDebug("stemServer.process.close", { code, signal, logTail: stemServerLog.slice(-20) });
    stemServerProcess = null;
  });

  setTimeout(async () => {
    const status = await stemServerStatus();
    if (status.running) stemServerStarting = false;
  }, 3000);

  return stemServerState({ ok: true, starting: true, installRoot, model, requestedDevice: device, concurrency });
}

async function stemServerStatus() {
  const health = await requestJson(`${LOCAL_STEM_SERVER_URL}/health`, 1200);
  if (health.body) {
    stemServerStarting = false;
  }
  return stemServerState({
    ok: Boolean(health.ok && health.body?.ok),
    running: Boolean(health.body),
    healthy: Boolean(health.ok && health.body?.ok),
    model: health.body?.model || null,
    device: health.body?.device || null,
    requestedDevice: health.body?.requested_device || null,
    concurrency: Number(health.body?.concurrency) || null,
    accelerators: Array.isArray(health.body?.accelerators) ? health.body.accelerators : [],
    capabilities: health.body?.capabilities || null,
    storageDir: health.body?.storage_dir || null,
    health: health.body || null,
    error: health.error || ""
  });
}

async function stopStemServer(options = {}) {
  if (!stemServerProcess && !options.forcePort) return;
  logDebug("stemServer.stop");
  const pid = stemServerProcess?.pid;
  try {
    if (stemServerProcess && process.platform === "win32" && pid) {
      spawn("taskkill.exe", ["/pid", String(pid), "/T", "/F"], { windowsHide: true });
    } else if (stemServerProcess) {
      stemServerProcess.kill();
    }
  } catch (error) {
    logDebug("stemServer.stop.failed", errorToLog(error));
  }
  stemServerProcess = null;
  stemServerStarting = false;
  if (options.forcePort) {
    await stopLocalStemServerPort();
  }
}

async function stopLocalStemServerPort() {
  if (process.platform !== "win32") return;
  const result = await runProcess("netstat.exe", ["-ano", "-p", "TCP"], { timeoutMs: 7000 });
  if (result.code !== 0 || !result.stdout) return;
  const pids = new Set();
  for (const line of result.stdout.split(/\r?\n/)) {
    if (!/\sLISTENING\s/i.test(line)) continue;
    if (!/(?:127\.0\.0\.1|0\.0\.0\.0|\[::1\]|\[::\]):7865\b/i.test(line)) continue;
    const match = line.trim().match(/\s(\d+)$/);
    if (match?.[1]) pids.add(match[1]);
  }
  for (const listenPid of pids) {
    try {
      await runProcess("taskkill.exe", ["/pid", listenPid, "/T", "/F"], { timeoutMs: 7000 });
      appendStemServerLog(`FeedForge: stopped old stem server process ${listenPid}`);
    } catch (error) {
      logDebug("stemServer.portStop.failed", { pid: listenPid, ...errorToLog(error) });
    }
  }
}

async function waitForStemServerStop(timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const health = await requestJson(`${LOCAL_STEM_SERVER_URL}/health`, 500);
    if (!health.body) return true;
    await delay(350);
  }
  return false;
}

function stemServerState(extra = {}) {
  const processRunning = Boolean(stemServerProcess && stemServerProcess.exitCode === null);
  const running = Boolean(extra.running || processRunning);
  const healthy = Boolean(extra.healthy);
  const progress = stemServerProgress(extra, healthy, running, processRunning);
  return {
    ...extra,
    ok: Boolean(extra.ok),
    url: LOCAL_STEM_SERVER_URL,
    installRoot: extra.installRoot || defaultDemucsInstallRoot(),
    model: extra.model || null,
    device: extra.device || null,
    requestedDevice: extra.requestedDevice || null,
    concurrency: extra.concurrency || null,
    accelerators: extra.accelerators || [],
    capabilities: extra.capabilities || null,
    storageDir: extra.storageDir || null,
    running,
    starting: Boolean((extra.starting || stemServerStarting) && !running && !healthy),
    healthy,
    processRunning,
    phase: progress.phase,
    message: progress.message,
    log: stemServerLog.slice(-STEM_SERVER_LOG_LINES)
  };
}

function stemServerProgress(extra, healthy, running, processRunning) {
  if (healthy) {
    return {
      phase: "ready",
      message: `Ready on ${extra.device || "detected device"}.`
    };
  }
  const lines = stemServerLog.slice(-30);
  const text = lines.join("\n");
  const lastImportant = [...lines].reverse().find((line) => /error|traceback|feedforge:|successfully installed|installing collected|using cached|downloading|collecting|uvicorn|running/i.test(line)) || "";
  if (/traceback|error:/i.test(text)) {
    return {
      phase: "error",
      message: lastImportant || extra.error || "The stem server reported an error. Open the debug log for details."
    };
  }
  if (/successfully installed/i.test(text)) {
    return {
      phase: "loading",
      message: "CUDA/Python packages installed. Loading Demucs and starting the local server."
    };
  }
  if (/feedforge: starting demucs server/i.test(text)) {
    return {
      phase: "loading",
      message: "Starting Demucs and preloading the selected model. First model load can take a while."
    };
  }
  if (/feedforge: installing cuda pytorch|feedforge: installing pytorch/i.test(text)) {
    return {
      phase: "installing",
      message: "Installing the PyTorch runtime for the selected device."
    };
  }
  if (/feedforge: installing feedforge stem dependencies/i.test(text)) {
    return {
      phase: "installing",
      message: "Installing FeedForge stem dependencies into the local environment."
    };
  }
  if (/feedforge: creating local python environment/i.test(text)) {
    return {
      phase: "installing",
      message: "Creating the local Python environment for stem splitting."
    };
  }
  if (/feedforge: preparing/i.test(text)) {
    return {
      phase: "starting",
      message: "Preparing local stem setup."
    };
  }
  if (/installing collected packages/i.test(text)) {
    return {
      phase: "installing",
      message: "Installing Python, Demucs, and PyTorch packages. This can take several minutes on first GPU setup."
    };
  }
  if (/using cached .*torch|downloading .*torch|collecting .*torch/i.test(text)) {
    return {
      phase: "downloading",
      message: "Preparing the PyTorch runtime. CUDA builds are large and may take time on first setup."
    };
  }
  if (extra.starting || stemServerStarting || processRunning) {
    return {
      phase: "starting",
      message: "Starting the local stem server."
    };
  }
  if (running) {
    return {
      phase: "unhealthy",
      message: extra.error || "The port is reachable, but health did not pass yet."
    };
  }
  return {
    phase: "stopped",
    message: "Local stem server is not running."
  };
}

function stemServerLauncherPath() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, "demucs-server", "start-demucs-server.ps1");
  }
  return path.join(app.getAppPath(), "tools", "start-demucs-server.ps1");
}

function defaultDemucsInstallRoot() {
  return path.join(app.getPath("userData"), "demucs-server");
}

function demucsInstallRoot(value) {
  if (typeof value !== "string" || !value.trim()) {
    return defaultDemucsInstallRoot();
  }
  return path.resolve(value.trim());
}

function demucsModelId(value) {
  const id = typeof value === "string" ? value.trim() : "";
  return DEMUCS_MODELS.some((model) => model.id === id) ? id : "htdemucs_6s";
}

function demucsDeviceId(value) {
  const id = typeof value === "string" ? value.trim().toLowerCase() : "";
  if (!id || id === "auto" || id === "cpu" || id === "mps" || /^cuda(?::\d+)?$/.test(id)) {
    return id || "auto";
  }
  return "auto";
}

function demucsConcurrency(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 1;
  return Math.max(1, Math.min(Math.trunc(parsed), 4));
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function demucsDeviceOptions(installRoot) {
  const fallback = [
    {
      id: "auto",
      name: "Auto",
      detail: "Installs and uses CUDA PyTorch when an NVIDIA GPU is detected, otherwise CPU.",
      available: true,
      recommended: true
    },
    { id: "cpu", name: "CPU", detail: "Compatible with every PC, but slow for stem splitting.", available: true }
  ];
  const python = path.join(installRoot, ".demucs-venv", "Scripts", "python.exe");
  if (!fs.existsSync(python)) {
    return mergeDeviceOptions(fallback, await systemGpuDeviceOptions());
  }
  const script = [
    "import json",
    "devices=[{'id':'auto','name':'Auto','detail':'Installs and uses CUDA PyTorch when an NVIDIA GPU is detected, otherwise CPU.','available':True,'recommended':True},{'id':'cpu','name':'CPU','detail':'Compatible with every PC, but slow for stem splitting.','available':True}]",
    "try:",
    " import torch",
    " if torch.cuda.is_available():",
    "  [devices.append({'id':f'cuda:{i}','name':torch.cuda.get_device_name(i),'detail':f'CUDA GPU, {round(torch.cuda.get_device_properties(i).total_memory/(1024**3),1)} GB VRAM','available':True,'recommended':i==0}) for i in range(torch.cuda.device_count())]",
    " if hasattr(torch.backends,'mps') and torch.backends.mps.is_available(): devices.append({'id':'mps','name':'Apple GPU','detail':'Metal acceleration available.','available':True})",
    "except Exception as exc:",
    " devices.append({'id':'torch-error','name':'GPU detection unavailable','detail':str(exc),'available':False})",
    "print(json.dumps(devices))"
  ].join("\n");
  try {
    const result = await runProcess(python, ["-c", script], { cwd: installRoot, timeoutMs: 12000 });
    if (result.code !== 0) {
      logDebug("stemServer.devices.failed", { code: result.code, stderrTail: tail(result.stderr) });
      return fallback;
    }
    const parsed = JSON.parse(result.stdout);
    return mergeDeviceOptions(Array.isArray(parsed) && parsed.length ? parsed : fallback, await systemGpuDeviceOptions());
  } catch (error) {
    logDebug("stemServer.devices.error", errorToLog(error));
    return mergeDeviceOptions(fallback, await systemGpuDeviceOptions());
  }
}

async function systemGpuDeviceOptions() {
  if (process.platform !== "win32") return [];
  const result = await runProcess("nvidia-smi.exe", [
    "--query-gpu=name,memory.total",
    "--format=csv,noheader,nounits"
  ], { timeoutMs: 5000 });
  if (result.code !== 0 || !result.stdout.trim()) return [];
  return result.stdout
    .split(/\r?\n/)
    .map((line, index) => {
      const [name, memory] = line.split(",").map((part) => part.trim());
      if (!name) return null;
      const memoryGb = Number(memory) ? `${(Number(memory) / 1024).toFixed(1)} GB VRAM` : "VRAM unknown";
      return {
        id: `cuda:${index}`,
        name,
        detail: `NVIDIA GPU detected by nvidia-smi, ${memoryGb}. FeedForge will install CUDA PyTorch when this device is used.`,
        available: true,
        recommended: index === 0,
        kind: "cuda"
      };
    })
    .filter(Boolean);
}

function mergeDeviceOptions(primary, discovered) {
  const byId = new Map();
  for (const item of [...primary, ...discovered]) {
    if (!item?.id || byId.has(item.id)) continue;
    byId.set(item.id, item);
  }
  return [...byId.values()];
}

function demucsTorchIndex(device) {
  if (String(device || "").startsWith("cuda")) {
    return "https://download.pytorch.org/whl/cu128";
  }
  if (device === "auto") {
    return "auto";
  }
  return "";
}

function runProcess(command, args, options = {}) {
  return new Promise((resolve) => {
    let stdout = "";
    let stderr = "";
    let settled = false;
    const child = spawn(command, args, {
      cwd: options.cwd || processWorkingDirectory(),
      env: options.env || process.env,
      windowsHide: true
    });
    const timer = options.timeoutMs ? setTimeout(() => {
      if (settled) return;
      settled = true;
      try {
        child.kill();
      } catch {
        // Best effort timeout cleanup.
      }
      resolve({ code: 1, stdout, stderr: `${stderr}\nProcess timed out after ${options.timeoutMs}ms.` });
    }, options.timeoutMs) : null;
    child.stdout.on("data", (chunk) => { stdout += chunk.toString(); });
    child.stderr.on("data", (chunk) => { stderr += chunk.toString(); });
    child.on("close", (code) => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      resolve({ code: code ?? 0, stdout, stderr });
    });
    child.on("error", (error) => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      resolve({ code: 1, stdout, stderr: `${stderr}\n${error.message}` });
    });
  });
}

function processWorkingDirectory() {
  const appPath = app.getAppPath();
  if (appPath && /\.asar$/i.test(appPath)) {
    return path.dirname(appPath);
  }
  if (appPath && fs.existsSync(appPath)) {
    try {
      const stat = fs.statSync(appPath);
      return stat.isDirectory() ? appPath : path.dirname(appPath);
    } catch {
      // Fall through to the executable directory.
    }
  }
  return path.dirname(process.execPath);
}

function modelInstallStates(installRoot) {
  const checkpointFiles = checkpointFileNames(installRoot);
  return DEMUCS_MODELS.map((model) => {
    if (model.remoteOnly) {
      return {
        ...model,
        installed: false,
        partial: false,
        installedCount: 0,
        requiredCount: 0
      };
    }
    const signatures = model.signatures || [];
    const installedCount = signatures.filter((signature) => checkpointFiles.some((file) => file.startsWith(signature))).length;
    const installed = signatures.length > 0 && installedCount === signatures.length;
    const partial = installedCount > 0 && !installed;
    return {
      ...model,
      installed,
      partial,
      installedCount,
      requiredCount: signatures.length
    };
  });
}

async function demucsSetupState(installRoot) {
  const venvPython = path.join(installRoot, ".demucs-venv", "Scripts", "python.exe");
  const marker = path.join(installRoot, ".feedforge-stems-source");
  const checkpointFiles = checkpointFileNames(installRoot);
  const environmentInstalled = fs.existsSync(venvPython);
  return {
    installRoot,
    venvPython,
    environmentInstalled,
    dependenciesInstalled: fs.existsSync(marker),
    marker,
    checkpointCount: checkpointFiles.length,
    cacheRoots: [
      path.join(installRoot, "model-cache", "torch", "hub", "checkpoints"),
      path.join(osHome(), ".cache", "torch", "hub", "checkpoints")
    ]
  };
}

function checkpointFileNames(installRoot) {
  const roots = [
    path.join(installRoot, "model-cache", "torch", "hub", "checkpoints"),
    path.join(osHome(), ".cache", "torch", "hub", "checkpoints")
  ];
  const names = new Set();
  for (const root of roots) {
    let entries = [];
    try {
      entries = fs.readdirSync(root, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      if (entry.isFile()) names.add(entry.name);
    }
  }
  return [...names];
}

function osHome() {
  return process.env.USERPROFILE || process.env.HOME || app.getPath("home");
}

function appendStemServerLog(chunk) {
  const text = redact(String(chunk || ""));
  const lines = text.split(/\r?\n/).filter((line) => line.length > 0);
  stemServerLog.push(...lines);
  if (stemServerLog.length > STEM_SERVER_LOG_LINES) {
    stemServerLog = stemServerLog.slice(-STEM_SERVER_LOG_LINES);
  }
  logDebug("stemServer.output", { tail: tail(text, 2000) });
}

function requestJson(url, timeoutMs) {
  return new Promise((resolve) => {
    const request = http.get(url, { timeout: timeoutMs }, (response) => {
      let body = "";
      response.setEncoding("utf8");
      response.on("data", (chunk) => { body += chunk; });
      response.on("end", () => {
        try {
          const parsed = JSON.parse(body);
          resolve({
            ok: response.statusCode >= 200 && response.statusCode < 300,
            statusCode: response.statusCode,
            body: parsed
          });
        } catch {
          resolve({ ok: false, error: `Invalid response from stem server (${response.statusCode})` });
        }
      });
    });
    request.on("timeout", () => {
      request.destroy(new Error("Stem server status timed out."));
    });
    request.on("error", (error) => {
      resolve({ ok: false, error: error.message });
    });
  });
}

function converterCommand() {
  const packaged = path.join(process.resourcesPath || "", "bin", "psarc2feedpak", "psarc2feedpak.exe");
  const packagedLegacy = path.join(process.resourcesPath || "", "bin", "psarc2feedpak.exe");
  const localDirExe = path.join(app.getAppPath(), "dist", "psarc2feedpak", "psarc2feedpak.exe");
  const localExe = path.join(app.getAppPath(), "dist", "psarc2feedpak.exe");
  if (app.isPackaged && fs.existsSync(packaged)) {
    return { command: packaged, prefix: [], cwd: path.dirname(packaged) };
  }
  if (app.isPackaged && fs.existsSync(packagedLegacy)) {
    return { command: packagedLegacy, prefix: [], cwd: path.dirname(packagedLegacy) };
  }
  if (fs.existsSync(localDirExe)) {
    return { command: localDirExe, prefix: [], cwd: path.dirname(localDirExe) };
  }
  if (fs.existsSync(localExe)) {
    return { command: localExe, prefix: [], cwd: app.getAppPath() };
  }
  return {
    command: path.join(app.getAppPath(), ".venv", "Scripts", "python.exe"),
    prefix: ["-m", "feedback_converter.cli"],
    cwd: app.getAppPath()
  };
}

function validDefaultPath(defaultPath) {
  if (typeof defaultPath !== "string" || !defaultPath) return undefined;
  try {
    return fs.existsSync(defaultPath) ? defaultPath : undefined;
  } catch {
    return undefined;
  }
}

function runConverter(args) {
  const { command, prefix, cwd } = converterCommand();
  const diagnostics = {
    command,
    cwd,
    exists: fs.existsSync(command),
    packaged: app.isPackaged,
    resourcesPath: process.resourcesPath,
    appPath: app.getAppPath()
  };
  logDebug("converter.process.start", {
    command,
    cwd,
    args: [...prefix, ...args],
    diagnostics
  });
  return new Promise((resolve) => {
    const startedAt = Date.now();
    const child = spawn(command, [...prefix, ...args], {
      cwd,
      windowsHide: true
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk.toString(); });
    child.stderr.on("data", (chunk) => { stderr += chunk.toString(); });
    child.on("close", (code) => {
      logDebug("converter.process.close", {
        code,
        durationMs: Date.now() - startedAt,
        stdoutTail: tail(stdout),
        stderrTail: tail(stderr),
        diagnostics
      });
      resolve({ code, stdout, stderr, diagnostics });
    });
    child.on("error", (error) => {
      logDebug("converter.process.error", {
        error: errorToLog(error),
        diagnostics
      });
      resolve({
        code: 1,
        stdout,
        stderr: `${error.message}\nConverter: ${command}\nWorking directory: ${cwd}\nExists: ${diagnostics.exists}`,
        diagnostics
      });
    });
  });
}

async function findPsarcFiles(root) {
  const files = [];
  const pending = [root];
  while (pending.length > 0) {
    const folder = pending.pop();
    let entries;
    try {
      entries = await fs.promises.readdir(folder, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      const fullPath = path.join(folder, entry.name);
      if (entry.isDirectory()) {
        pending.push(fullPath);
      } else if (entry.isFile() && entry.name.toLowerCase().endsWith(".psarc")) {
        files.push(fullPath);
      }
    }
  }
  return files;
}

function parseJson(value) {
  try {
    return JSON.parse(value);
  } catch {
    const line = value.split(/\r?\n/).find((item) => item.trim().startsWith("{"));
    return line ? JSON.parse(line) : null;
  }
}

function createInspectionFolder(inputPath) {
  if (!inspectCacheRoot) {
    inspectCacheRoot = path.join(app.getPath("temp"), "feedforge-inspect-cache");
  }
  fs.mkdirSync(inspectCacheRoot, { recursive: true });
  const safeName = path.basename(inputPath, path.extname(inputPath)).replace(/[^a-z0-9._-]+/gi, "_").slice(0, 80) || "song";
  return fs.mkdtempSync(path.join(inspectCacheRoot, `${safeName}-`));
}

function resetDirectory(targetPath) {
  try {
    removeDirectory(targetPath);
    fs.mkdirSync(targetPath, { recursive: true });
  } catch {
    // Cache cleanup is best-effort.
  }
}

function removeDirectory(targetPath) {
  fs.rmSync(targetPath, { recursive: true, force: true });
}

function cleanupStalePortableArtifacts() {
  const tempRoot = app.getPath("temp");
  const staleBefore = Date.now() - 10 * 60 * 1000;
  let entries = [];
  try {
    entries = fs.readdirSync(tempRoot, { withFileTypes: true });
  } catch {
    return;
  }

  for (const entry of entries) {
    if (!entry.isDirectory() || !/^ns.*\.tmp$/i.test(entry.name)) {
      continue;
    }
    const folder = path.join(tempRoot, entry.name);
    const marker = path.join(folder, "7z-out", "FeedForge.exe");
    try {
      const stat = fs.statSync(folder);
      if (stat.mtimeMs > staleBefore || !fs.existsSync(marker)) {
        continue;
      }
      removeDirectory(folder);
    } catch {
      // Active portable launcher folders can be locked; the next launch can retry.
    }
  }
}

function initializeDebugLog() {
  try {
    const logDir = path.join(app.getPath("userData"), "logs");
    fs.mkdirSync(logDir, { recursive: true });
    debugLogPath = path.join(logDir, "feedforge-debug.log");
    rotateDebugLogIfNeeded();
    logDebug("log.initialized", { path: debugLogPath });
  } catch {
    debugLogPath = null;
  }
}

function debugLogInfo() {
  const folder = debugLogPath ? path.dirname(debugLogPath) : path.join(app.getPath("userData"), "logs");
  const previous = debugLogPath ? debugLogPath.replace(/\.log$/i, ".previous.log") : path.join(folder, "feedforge-debug.previous.log");
  return {
    path: debugLogPath || path.join(folder, "feedforge-debug.log"),
    previousPath: previous,
    folder,
    exists: Boolean(debugLogPath && fs.existsSync(debugLogPath)),
    previousExists: fs.existsSync(previous)
  };
}

async function pythonInfo(options = {}) {
  const installRoot = demucsInstallRoot(options.installDir);
  const candidates = pythonCandidates(installRoot, options.pythonPath);
  const errors = [];
  for (const candidate of candidates) {
    const result = await runProcess(candidate.command, candidate.args, { timeoutMs: 8000 });
    if (result.code !== 0) {
      errors.push(`${candidate.command}: ${tail(result.stderr || result.stdout, 400)}`);
      continue;
    }
    try {
      const parsed = JSON.parse(result.stdout.trim().split(/\r?\n/).pop() || "{}");
      const major = Number(parsed.major);
      const minor = Number(parsed.minor);
      const supported = major > 3 || (major === 3 && minor >= 11);
      return {
        ok: supported,
        found: true,
        supported,
        executable: parsed.executable || candidate.command,
        version: parsed.version || "",
        source: candidate.source,
        message: supported
          ? `Python ${parsed.version} is ready for stem splitting${candidate.source ? ` (${candidate.source})` : ""}.`
          : `Python ${parsed.version || ""} was found, but FeedForge needs Python 3.11 or newer.`,
      };
    } catch (error) {
      errors.push(`${candidate.command}: invalid version response`);
    }
  }
  logDebug("python.detect.failed", {
    installRoot,
    candidateCount: candidates.length,
    candidates: candidates.map((candidate) => ({ command: candidate.command, source: candidate.source })),
    errors
  });
  return {
    ok: false,
    found: false,
    supported: false,
    executable: "",
    version: "",
    message: "Python 3.11 or newer was not found. Install Python 3.11+ from python.org or select a Demucs folder that already has a FeedForge stem environment.",
    errors,
  };
}

function pythonCandidates(installRoot, pythonPath) {
  const code = "import json, sys; print(json.dumps({'executable': sys.executable, 'version': sys.version.split()[0], 'major': sys.version_info.major, 'minor': sys.version_info.minor}))";
  const candidates = [];
  const addExe = (command, source, args = ["-c", code]) => {
    if (!command) return;
    if (path.isAbsolute(command) && !fs.existsSync(command)) return;
    if (candidates.some((candidate) => candidate.command.toLowerCase() === command.toLowerCase() && candidate.args.join("\u0000") === args.join("\u0000"))) return;
    candidates.push({ command, args, source });
  };

  addExe(pythonExecutablePath(pythonPath), "selected Python");
  addExe(path.join(installRoot, ".demucs-venv", "Scripts", "python.exe"), "FeedForge local stem environment");
  for (const command of registryPythonExecutables()) {
    addExe(command, "Windows Python registry");
  }
  addExe("python.exe", "PATH");
  addExe("py.exe", "Python launcher", ["-3", "-c", code]);

  for (const root of [
    installRoot,
    process.env.ProgramFiles,
    process.env["ProgramFiles(x86)"],
    process.env.LOCALAPPDATA,
    "C:\\Program Files",
    "C:\\Program Files (x86)",
    path.join(osHome(), "AppData", "Local", "Programs", "Python"),
  ].filter(Boolean)) {
    for (const command of findPythonExecutables(root)) {
      addExe(command, "standard install");
    }
  }

  return candidates;
}

function pythonExecutablePath(value) {
  if (typeof value !== "string" || !value.trim()) return "";
  const resolved = path.resolve(value.trim());
  try {
    if (fs.existsSync(resolved) && fs.statSync(resolved).isFile() && path.basename(resolved).toLowerCase() === "python.exe") {
      return resolved;
    }
    const nested = path.join(resolved, "python.exe");
    if (fs.existsSync(nested)) return nested;
  } catch {
    return "";
  }
  return "";
}

function registryPythonExecutables() {
  if (process.platform !== "win32") return [];
  const roots = [
    "HKCU\\Software\\Python\\PythonCore",
    "HKLM\\Software\\Python\\PythonCore",
    "HKLM\\Software\\WOW6432Node\\Python\\PythonCore"
  ];
  const executables = [];
  for (const root of roots) {
    let output = "";
    try {
      output = execFileSync("reg.exe", ["query", root, "/s", "/v", "ExecutablePath"], {
        encoding: "utf8",
        windowsHide: true,
        timeout: 5000
      });
    } catch {
      continue;
    }
    for (const line of output.split(/\r?\n/)) {
      const match = line.match(/ExecutablePath\s+REG_\w+\s+(.+?)\s*$/i);
      if (match?.[1]) executables.push(match[1].trim());
    }
  }
  return executables;
}

function findPythonExecutables(root) {
  const executables = [];
  const seen = new Set();
  const queue = [{ dir: root, depth: 0 }];
  const maxDepth = 4;
  const maxDirs = 600;

  while (queue.length && seen.size < maxDirs) {
    const { dir, depth } = queue.shift();
    const normalized = path.resolve(dir).toLowerCase();
    if (seen.has(normalized)) continue;
    seen.add(normalized);

    const direct = path.join(dir, "python.exe");
    if (fs.existsSync(direct)) executables.push(direct);
    if (depth >= maxDepth) continue;

    let entries = [];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      const name = entry.name;
      if (!pythonSearchDirName(name, depth)) continue;
      queue.push({ dir: path.join(dir, name), depth: depth + 1 });
    }
  }
  return executables;
}

function pythonSearchDirName(name, depth) {
  if (/^Python\d+/i.test(name)) return true;
  if (/^\.demucs-venv$/i.test(name)) return true;
  if (/^(Scripts|Programs|Python|PythonCore)$/i.test(name)) return true;
  if (/^(Program Files|Program Files \(x86\))$/i.test(name)) return true;
  if (depth === 0 && /^(Python|Programs|feedforge|demucs-server)$/i.test(name)) return true;
  return false;
}

function logDebug(event, details = {}) {
  if (!debugLogPath) return;
  try {
    rotateDebugLogIfNeeded();
    const record = {
      time: new Date().toISOString(),
      event,
      details: sanitizeForLog(details)
    };
    fs.appendFileSync(debugLogPath, `${JSON.stringify(record)}\n`, "utf8");
  } catch {
    // Debug logging must never break conversion.
  }
}

function rotateDebugLogIfNeeded() {
  if (!debugLogPath || !fs.existsSync(debugLogPath)) return;
  try {
    const stat = fs.statSync(debugLogPath);
    if (stat.size < DEBUG_LOG_MAX_BYTES) return;
    const rotated = debugLogPath.replace(/\.log$/i, ".previous.log");
    fs.rmSync(rotated, { force: true });
    fs.renameSync(debugLogPath, rotated);
  } catch {
    // Rotation is best-effort.
  }
}

function sanitizeForLog(value) {
  if (value instanceof Error) return errorToLog(value);
  if (Array.isArray(value)) return value.map((item) => sanitizeForLog(item));
  if (!value || typeof value !== "object") {
    return typeof value === "string" ? redact(value) : value;
  }
  const output = {};
  for (const [key, entry] of Object.entries(value)) {
    if (/token|password|secret|cookie|authorization/i.test(key)) {
      output[key] = "[redacted]";
    } else {
      output[key] = sanitizeForLog(entry);
    }
  }
  return output;
}

function errorToLog(error) {
  if (error instanceof Error) {
    return {
      name: error.name,
      message: redact(error.message || ""),
      stack: redact(error.stack || "")
    };
  }
  return {
    message: redact(String(error || ""))
  };
}

function tail(value, maxLength = 6000) {
  const text = redact(String(value || ""));
  return text.length > maxLength ? text.slice(-maxLength) : text;
}

function redact(value) {
  return String(value)
    .replace(/(--demucs-api-key["'\s,]+)([^"'\s,}\]]+)/gi, "$1[redacted]")
    .replace(/(token|password|secret|authorization|cookie)(["'\s:=]+)([^"'\s,}]+)/gi, "$1$2[redacted]")
    .replace(/(Bearer\s+)[A-Za-z0-9._~+/=-]+/gi, "$1[redacted]");
}
