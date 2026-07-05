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

contextBridge.exposeInMainWorld("feedbackConverter", {
  pickPsarc: (options) => ipcRenderer.invoke("dialog:pickPsarc", options),
  pickFolder: (options) => ipcRenderer.invoke("dialog:pickFolder", options),
  pickOutput: (options) => ipcRenderer.invoke("dialog:pickOutput", options),
  expandPaths: (paths) => ipcRenderer.invoke("files:expandPaths", paths),
  onDroppedPaths: (callback) => {
    const listener = (event) => callback(event.detail);
    window.addEventListener("feedforge:dropped-paths", listener);
    return () => window.removeEventListener("feedforge:dropped-paths", listener);
  },
  inspect: (inputPath) => ipcRenderer.invoke("converter:inspect", inputPath),
  convert: (payload) => ipcRenderer.invoke("converter:convert", payload)
});
