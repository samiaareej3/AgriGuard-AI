import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

/**
 * End-to-end tests against the real backend (in-memory DB, simulator, trained model)
 * and the production frontend build. Run from frontend/:  npm run test:e2e
 * Reuses servers already running on :8000 / :3000.
 */
const PY = JSON.stringify(path.resolve(__dirname, "..", ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python").split(path.sep).join("/"));

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:3000", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
  webServer: [
    {
      command: `${PY} -m uvicorn app.main:app --port 8000`,
      cwd: "../backend",
      url: "http://localhost:8000/api/v1/health",
      reuseExistingServer: true,
      timeout: 180_000,
      env: { SIMULATOR_TICK_SECONDS: "1", LOG_JSON: "false", LOG_LEVEL: "WARNING" },
    },
    {
      command: "npm run start -- -p 3000",
      url: "http://localhost:3000/login",
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
});
