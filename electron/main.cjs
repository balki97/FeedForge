const { app, BrowserWindow, Menu, dialog, ipcMain } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

let mainWindow;
let inspectCacheRoot;
let debugLogPath;
const DEBUG_LOG_MAX_BYTES = 2 * 1024 * 1024;

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
    hasRigBuilderDataDir: Boolean(payload.rigBuilderDataDir)
  });
  const args = [payload.inputPath];
  if (payload.outputPath) args.push("-o", payload.outputPath);
  if (payload.overwrite) args.push("--overwrite");
  if (payload.includeTones === false) args.push("--no-tones");
  if (payload.bStandardTo7String) args.push("--b-standard-to-7-string");
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
    .replace(/(token|password|secret|authorization|cookie)(["'\s:=]+)([^"'\s,}]+)/gi, "$1$2[redacted]")
    .replace(/(Bearer\s+)[A-Za-z0-9._~+/=-]+/gi, "$1[redacted]");
}
