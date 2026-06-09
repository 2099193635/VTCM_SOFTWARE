import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("vtcm", {
  selectFile: () => ipcRenderer.invoke("select-file"),
  backendUrl: () => ipcRenderer.invoke("backend-url")
});

