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
  pickOutput: (options) => ipcRenderer.invoke("dialog:pickOutput", options),
  pickRigBuilderData: (options) => ipcRenderer.invoke("dialog:pickRigBuilderData", options),
  pickDemucsInstallDir: (options) => ipcRenderer.invoke("dialog:pickDemucsInstallDir", options),
  expandPaths: (paths) => ipcRenderer.invoke("files:expandPaths", paths),
  onDroppedPaths: (callback) => {
    const listener = (event) => callback(event.detail);
    window.addEventListener("feedforge:dropped-paths", listener);
    return () => window.removeEventListener("feedforge:dropped-paths", listener);
  },
  inspect: (inputPath, options) => ipcRenderer.invoke("converter:inspect", inputPath, options),
  convert: (payload) => ipcRenderer.invoke("converter:convert", payload),
  seedRigBuilder: (inputPath, options) => ipcRenderer.invoke("converter:seedRigBuilder", inputPath, options),
  getStemServerStatus: () => ipcRenderer.invoke("stemServer:status"),
  getStemServerModels: (options) => ipcRenderer.invoke("stemServer:models", options),
  startStemServer: (options) => ipcRenderer.invoke("stemServer:start", options),
  stopStemServer: () => ipcRenderer.invoke("stemServer:stop"),
  checkForUpdates: () => ipcRenderer.invoke("updates:check"),
  openLatestRelease: (url) => ipcRenderer.invoke("updates:openLatest", url)
});
