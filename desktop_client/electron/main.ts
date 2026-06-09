import { app, BrowserWindow, dialog, ipcMain } from "electron";
import path from "node:path";
import fs from "node:fs";
import { spawn, ChildProcessWithoutNullStreams } from "node:child_process";

let mainWindow: BrowserWindow | null = null;
let backendProcess: ChildProcessWithoutNullStreams | null = null;

const repoRoot = path.resolve(__dirname, "..", "..");
const backendUrl = "http://127.0.0.1:18765";
const isDev = !app.isPackaged;

function appIconPath() {
  if (isDev) return path.join(repoRoot, "desktop_client", "build", "icon.ico");
  return path.join(__dirname, "..", "build", "icon.ico");
}

function startBackend() {
  if (backendProcess) return;
  if (isDev) return;
  const packagedBackend = path.join(process.resourcesPath || "", "backend", "vtcm-backend.exe");
  if (!isDev && fs.existsSync(packagedBackend)) {
    backendProcess = spawn(packagedBackend, [], { cwd: repoRoot });
    return;
  }
  backendProcess = spawn("python", ["-m", "desktop_backend.main"], {
    cwd: repoRoot,
    env: { ...process.env, PYTHONIOENCODING: "utf-8", VTCM_BACKEND_PORT: "18765" }
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 940,
    minWidth: 1180,
    minHeight: 760,
    title: "VTCM Workbench",
    icon: appIconPath(),
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  if (isDev) {
    mainWindow.loadURL("http://127.0.0.1:5173");
  } else {
    mainWindow.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }
}

app.whenReady().then(() => {
  startBackend();
  createWindow();

  ipcMain.handle("select-file", async () => {
    const result = await dialog.showOpenDialog(mainWindow!, {
      properties: ["openFile"],
      filters: [
        { name: "Data files", extensions: ["csv", "txt", "npz", "yaml", "json"] },
        { name: "All files", extensions: ["*"] }
      ]
    });
    return result.canceled ? null : result.filePaths[0];
  });

  ipcMain.handle("backend-url", () => backendUrl);
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  if (backendProcess) backendProcess.kill();
});
