const { contextBridge, ipcRenderer, webUtils } = require("electron");

function droppedPaths(files) {
  return Array.from(files).map((file) => webUtils.getPathForFile(file)).filter(Boolean);
}

window.addEventListener("dragover", (event) => {
  event.preventDefault();
}, true);

window.addEventListener("drop", (event) => {
  event.preventDefault();
  const paths = droppedPaths(event.dataTransfer?.files || []);
  if (paths.length > 0) {
    window.dispatchEvent(new CustomEvent("feedforge:dropped-paths", { detail: paths }));
  }
}, true);

window.addEventListener("error", (event) => {
  ipcRenderer.send("app:rendererError", {
    type: "error",
    message: event.message || "",
    source: event.filename || "",
    line: event.lineno || 0,
    column: event.colno || 0,
    stack: event.error?.stack || ""
  });
});

window.addEventListener("unhandledrejection", (event) => {
  const reason = event.reason;
  ipcRenderer.send("app:rendererError", {
    type: "unhandledrejection",
    message: reason?.message || String(reason || ""),
    stack: reason?.stack || ""
  });
});

contextBridge.exposeInMainWorld("feedbackConverter", {
  pickPsarc: (options) => ipcRenderer.invoke("dialog:pickPsarc", options),
  pickFolder: (options) => ipcRenderer.invoke("dialog:pickFolder", options),
  pickFolderWithRoot: (options) => ipcRenderer.invoke("dialog:pickFolderWithRoot", options),
  pickAuditFolder: (options) => ipcRenderer.invoke("dialog:pickAuditFolder", options),
  pickOutput: (options) => ipcRenderer.invoke("dialog:pickOutput", options),
  pickCoverImage: (options) => ipcRenderer.invoke("dialog:pickCoverImage", options),
  pickAudioStem: (options) => ipcRenderer.invoke("dialog:pickAudioStem", options),
  pickDemucsInstallDir: (options) => ipcRenderer.invoke("dialog:pickDemucsInstallDir", options),
  pickPythonExecutable: (options) => ipcRenderer.invoke("dialog:pickPythonExecutable", options),
  expandPaths: (paths) => ipcRenderer.invoke("files:expandPaths", paths),
  onDroppedPaths: (callback) => {
    const listener = (event) => callback(event.detail);
    window.addEventListener("feedforge:dropped-paths", listener);
    return () => window.removeEventListener("feedforge:dropped-paths", listener);
  },
  inspect: (inputPath, options) => ipcRenderer.invoke("converter:inspect", inputPath, options),
  convert: (payload) => ipcRenderer.invoke("converter:convert", payload),
  updateFeedpak: (payload) => ipcRenderer.invoke("feedpak:update", payload),
  organizeFeedpaks: (payload) => ipcRenderer.invoke("feedpak:organize", payload),
  auditFeedpakLibrary: (payload) => ipcRenderer.invoke("audit:feedpakLibrary", payload),
  openAuditReport: (filePath) => ipcRenderer.invoke("audit:openReport", filePath),
  getStemServerStatus: () => ipcRenderer.invoke("stemServer:status"),
  getStemServerModels: (options) => ipcRenderer.invoke("stemServer:models", options),
  startStemServer: (options) => ipcRenderer.invoke("stemServer:start", options),
  stopStemServer: () => ipcRenderer.invoke("stemServer:stop"),
  freeStemServerPort: () => ipcRenderer.invoke("stemServer:freePort"),
  getAppVersion: () => ipcRenderer.invoke("app:version"),
  getDebugLogInfo: () => ipcRenderer.invoke("app:debugLogInfo"),
  openDebugLog: () => ipcRenderer.invoke("app:openDebugLog"),
  openDebugLogFolder: () => ipcRenderer.invoke("app:openDebugLogFolder"),
  getPythonInfo: (options) => ipcRenderer.invoke("app:pythonInfo", options),
  openPythonDownload: () => ipcRenderer.invoke("app:openPythonDownload"),
  openSupport: () => ipcRenderer.invoke("app:openSupport"),
  openWebsite: () => ipcRenderer.invoke("app:openWebsite"),
  openDiscord: () => ipcRenderer.invoke("app:openDiscord"),
  checkForUpdates: () => ipcRenderer.invoke("updates:check"),
  openLatestRelease: (url) => ipcRenderer.invoke("updates:openLatest", url)
});
