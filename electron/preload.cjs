const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("desktop", {
  openAppDataDirectory: () => ipcRenderer.invoke("desktop:open-app-data-directory")
});
