const http = require("node:http");
const path = require("node:path");
const { spawn } = require("node:child_process");

const repoRoot = path.resolve(__dirname, "..", "..");
const healthUrl = "http://127.0.0.1:18765/api/health";

function checkHealth() {
  return new Promise((resolve) => {
    const req = http.get(healthUrl, (res) => {
      res.resume();
      resolve(res.statusCode && res.statusCode >= 200 && res.statusCode < 500);
    });
    req.on("error", () => resolve(false));
    req.setTimeout(1000, () => {
      req.destroy();
      resolve(false);
    });
  });
}

(async () => {
  const alreadyRunning = await checkHealth();
  if (alreadyRunning) {
  console.log("[backend] Existing service detected on http://127.0.0.1:18765; reusing it.");
    setInterval(() => {}, 60_000);
    return;
  }

  console.log("[backend] Starting FastAPI service on http://127.0.0.1:18765");
  const child = spawn("python", ["-m", "desktop_backend.main"], {
    cwd: repoRoot,
    env: {
      ...process.env,
      PYTHONPATH: repoRoot,
      PYTHONIOENCODING: "utf-8",
      VTCM_BACKEND_PORT: "18765"
    },
    stdio: "inherit"
  });

  child.on("exit", (code) => {
    process.exit(code ?? 1);
  });
})();
