const { app, BrowserWindow, Menu, dialog, ipcMain } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

let mainWindow;
let inspectCacheRoot;

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
  cleanupStalePortableArtifacts();
  inspectCacheRoot = path.join(app.getPath("temp"), "feedforge-inspect-cache");
  resetDirectory(inspectCacheRoot);
  createWindow();
});
app.whenReady().then(() => Menu.setApplicationMenu(null));
app.on("before-quit", () => {
  if (inspectCacheRoot) removeDirectory(inspectCacheRoot);
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
  return result.canceled ? [] : result.filePaths;
});

ipcMain.handle("dialog:pickFolder", async (_event, options = {}) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: "Choose a CDLC folder",
    defaultPath: validDefaultPath(options.defaultPath),
    properties: ["openDirectory"]
  });
  if (result.canceled || !result.filePaths[0]) return [];
  return findPsarcFiles(result.filePaths[0]);
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
  return found;
});

ipcMain.handle("dialog:pickOutput", async (_event, options = {}) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: "Choose output folder",
    defaultPath: validDefaultPath(options.defaultPath),
    properties: ["openDirectory", "createDirectory"]
  });
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle("converter:inspect", async (_event, inputPath) => {
  const coverDir = createInspectionFolder(inputPath);
  const result = await runConverter(["--inspect-json", "--inspect-cover-dir", coverDir, inputPath]);
  const parsed = parseJson(result.stdout);
  if (!parsed || !parsed.ok) {
    return {
      ok: false,
      error: parsed?.error || result.stderr || "Inspection failed",
      diagnostics: result.diagnostics
    };
  }
  return parsed;
});

ipcMain.handle("converter:convert", async (_event, payload) => {
  const args = [payload.inputPath];
  if (payload.outputPath) args.push("-o", payload.outputPath);
  if (payload.overwrite) args.push("--overwrite");
  if (payload.includeTones === false) args.push("--no-tones");
  const result = await runConverter(args);
  const outputMatch = result.stdout.match(/wrote\s+(.+)/i);
  return {
    ok: result.code === 0,
    outputPath: outputMatch ? outputMatch[1].trim() : null,
    seed: payload.includeTones === false || result.code !== 0 ? null : await seedRigBuilder(payload.inputPath),
    stdout: result.stdout,
    stderr: result.stderr,
    diagnostics: result.diagnostics,
    error: result.code === 0 ? null : result.stderr || result.stdout || "Conversion failed"
  };
});

ipcMain.handle("converter:seedRigBuilder", async (_event, inputPath) => {
  return seedRigBuilder(inputPath);
});

async function seedRigBuilder(inputPath) {
  const result = await runConverter(["--seed-rig-builder", inputPath]);
  const parsed = parseJson(result.stdout);
  if (!parsed || !parsed.ok) {
    return {
      ok: false,
      error: parsed?.error || result.stderr || "Rig Builder route seeding failed",
      diagnostics: result.diagnostics
    };
  }
  return parsed;
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
  return new Promise((resolve) => {
    const child = spawn(command, [...prefix, ...args], {
      cwd,
      windowsHide: true
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk.toString(); });
    child.stderr.on("data", (chunk) => { stderr += chunk.toString(); });
    child.on("close", (code) => resolve({ code, stdout, stderr, diagnostics }));
    child.on("error", (error) => {
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
