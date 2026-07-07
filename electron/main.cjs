const { app, BrowserWindow, Menu, dialog, ipcMain, shell } = require("electron");
const { spawn } = require("child_process");
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
    id: "mdx_q",
    name: "MDX Q",
    size: "approx. 40 MB",
    description: "Quantized MDX model. Smaller download and often faster, with lower separation quality.",
    signatures: ["6b9c2ca1", "b72baf4e", "42e558d4", "305bc58f"]
  },
  {
    id: "mdx_extra_q",
    name: "MDX Extra Q",
    size: "approx. 40 MB",
    description: "Quantized MDX Extra. Smaller and faster than MDX Extra, usually lower quality than full-size models.",
    signatures: ["83fc094f", "464b36d7", "14fc6a69", "7fd6ef75"]
  }
];

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1500,
    height: 930,
    minWidth: 1180,
    minHeight: 760,
    backgroundColor: "#090f18",
    title: "FeedForge",
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

ipcMain.handle("dialog:pickRigBuilderData", async (_event, options = {}) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: "Choose FeedBack Rig Builder data folder",
    defaultPath: validDefaultPath(options.defaultPath),
    properties: ["openDirectory"]
  });
  const folder = result.canceled ? null : result.filePaths[0];
  logDebug("dialog.pickRigBuilderData", { selected: folder || "" });
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

ipcMain.handle("converter:inspect", async (_event, inputPath, options = {}) => {
  logDebug("converter.inspect.start", {
    inputPath,
    hasRigBuilderDataDir: Boolean(options.rigBuilderDataDir)
  });
  const coverDir = createInspectionFolder(inputPath);
  const result = await runConverter([
    "--inspect-json",
    "--inspect-cover-dir",
    coverDir,
    ...rigBuilderArgs(options.rigBuilderDataDir),
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
    includeTones: payload.includeTones !== false,
    bStandardTo7String: Boolean(payload.bStandardTo7String),
    separateStems: Boolean(payload.separateStems),
    hasDemucsUrl: Boolean(payload.demucsUrl),
    hasRigBuilderDataDir: Boolean(payload.rigBuilderDataDir)
  });
  const args = [payload.inputPath];
  if (payload.outputPath) args.push("-o", payload.outputPath);
  if (payload.overwrite) args.push("--overwrite");
  if (payload.includeTones === false) args.push("--no-tones");
  if (payload.bStandardTo7String) args.push("--b-standard-to-7-string");
  if (payload.separateStems) args.push("--separate-stems");
  if (payload.demucsUrl) args.push("--demucs-url", payload.demucsUrl);
  if (payload.demucsApiKey) args.push("--demucs-api-key", payload.demucsApiKey);
  args.push(...rigBuilderArgs(payload.rigBuilderDataDir));
  const result = await runConverter(args);
  const outputMatch = result.stdout.match(/wrote\s+(.+)/i);
  logDebug(result.code === 0 ? "converter.convert.ok" : "converter.convert.failed", {
    inputPath: payload.inputPath,
    outputPath: outputMatch ? outputMatch[1].trim() : payload.outputPath || "",
    code: result.code,
    stdoutTail: tail(result.stdout),
    stderrTail: tail(result.stderr),
    diagnostics: result.diagnostics
  });
  const seed = payload.includeTones === false || result.code !== 0 ? null : await seedRigBuilder(payload.inputPath, payload);
  return {
    ok: result.code === 0,
    outputPath: outputMatch ? outputMatch[1].trim() : null,
    seed,
    stdout: result.stdout,
    stderr: result.stderr,
    diagnostics: result.diagnostics,
    error: result.code === 0 ? null : result.stderr || result.stdout || "Conversion failed"
  };
});

ipcMain.handle("converter:seedRigBuilder", async (_event, inputPath, options = {}) => {
  return seedRigBuilder(inputPath, options);
});

ipcMain.handle("stemServer:status", async () => {
  return stemServerStatus();
});

ipcMain.handle("stemServer:models", async (_event, options = {}) => {
  const installRoot = demucsInstallRoot(options.installDir);
  return {
    defaultInstallDir: defaultDemucsInstallRoot(),
    installRoot,
    models: modelInstallStates(installRoot)
  };
});

ipcMain.handle("stemServer:start", async (_event, options = {}) => {
  return startStemServer(options);
});

ipcMain.handle("stemServer:stop", async () => {
  stopStemServer();
  return stemServerStatus();
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

async function seedRigBuilder(inputPath, options = {}) {
  logDebug("converter.seedRigBuilder.start", {
    inputPath,
    hasRigBuilderDataDir: Boolean(options.rigBuilderDataDir)
  });
  const result = await runConverter(["--seed-rig-builder", ...rigBuilderArgs(options.rigBuilderDataDir), inputPath]);
  const parsed = parseJson(result.stdout);
  if (!parsed || !parsed.ok) {
    logDebug("converter.seedRigBuilder.failed", {
      inputPath,
      code: result.code,
      stdoutTail: tail(result.stdout),
      stderrTail: tail(result.stderr),
      diagnostics: result.diagnostics
    });
    return {
      ok: false,
      error: parsed?.error || result.stderr || "Rig Builder route seeding failed",
      diagnostics: result.diagnostics
    };
  }
  logDebug("converter.seedRigBuilder.ok", {
    inputPath,
    routes: parsed.routes?.length || 0,
    warnings: parsed.warnings || []
  });
  return parsed;
}

function rigBuilderArgs(folder) {
  return typeof folder === "string" && folder ? ["--rig-builder-data-dir", folder] : [];
}

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
  const existing = await stemServerStatus();
  if (existing.running || stemServerStarting) {
    if (existing.processRunning && (existing.installRoot !== installRoot || existing.model !== model)) {
      stopStemServer();
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
  logDebug("stemServer.start", { scriptPath, installRoot, model });

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
      TORCH_HOME: path.join(installRoot, "model-cache", "torch"),
      XDG_CACHE_HOME: path.join(installRoot, "model-cache"),
      PIP_CACHE_DIR: path.join(installRoot, "pip-cache")
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

  return stemServerState({ ok: true, starting: true, installRoot, model });
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
    health: health.body || null,
    error: health.error || ""
  });
}

function stopStemServer() {
  if (!stemServerProcess) return;
  logDebug("stemServer.stop");
  const pid = stemServerProcess.pid;
  try {
    if (process.platform === "win32" && pid) {
      spawn("taskkill.exe", ["/pid", String(pid), "/T", "/F"], { windowsHide: true });
    } else {
      stemServerProcess.kill();
    }
  } catch (error) {
    logDebug("stemServer.stop.failed", errorToLog(error));
  }
  stemServerProcess = null;
  stemServerStarting = false;
}

function stemServerState(extra = {}) {
  const processRunning = Boolean(stemServerProcess && stemServerProcess.exitCode === null);
  const running = Boolean(extra.running || processRunning);
  const healthy = Boolean(extra.healthy);
  return {
    ...extra,
    ok: Boolean(extra.ok),
    url: LOCAL_STEM_SERVER_URL,
    installRoot: extra.installRoot || defaultDemucsInstallRoot(),
    model: extra.model || null,
    running,
    starting: Boolean((extra.starting || stemServerStarting) && !running && !healthy),
    healthy,
    processRunning,
    log: stemServerLog.slice(-STEM_SERVER_LOG_LINES)
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

function modelInstallStates(installRoot) {
  const checkpointFiles = checkpointFileNames(installRoot);
  return DEMUCS_MODELS.map((model) => {
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
