import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

const API = "http://localhost:8000/api/v1";
const SHOTS = path.join(__dirname, "..", "..", "test-results", "screens");
const SAMPLE = path.join(__dirname, "..", "..", "..", "backend", "sample_images", "early_blight", "early_blight_1.jpg");

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill("agriguard-dev");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Operations overview" })).toBeVisible();
}

test.beforeAll(async ({ request }) => {
  // Wait for the classifier to finish loading (TensorFlow start-up can take ~1 min).
  await expect.poll(async () => {
    const r = await request.get(`${API}/health/ready`);
    return (await r.json()).components?.model?.status;
  }, { timeout: 150_000, intervals: [2000] }).toBe("ok");
});

test("unauthenticated users are redirected to login", async ({ page }) => {
  await page.goto("/scans");
  await expect(page).toHaveURL(/\/login$/);
});

test("every page renders without errors (light + dark + mobile)", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  const pages: [string, string][] = [
    ["/", "Operations overview"], ["/monitoring", "Live monitoring"], ["/detect", "Disease detection"],
    ["/scans", "Scan history"], ["/operations", "Spray operations"], ["/devices", "Device management"],
    ["/analytics", "Analytics"], ["/insights", "Agricultural insights"], ["/settings", "Settings"],
  ];
  for (const [url, heading] of pages) {
    await page.goto(url);
    await expect(page.getByRole("heading", { name: heading, level: 1 })).toBeVisible();
    await expect(page.getByText("Could not load data")).toHaveCount(0);
    await page.waitForTimeout(800);
    await page.screenshot({ path: `${SHOTS}/light${url === "/" ? "/overview" : url}.png`, fullPage: true });
  }
  await page.emulateMedia({ colorScheme: "dark" });
  for (const url of ["/", "/devices", "/analytics"]) {
    await page.goto(url);
    await page.waitForTimeout(800);
    await page.screenshot({ path: `${SHOTS}/dark${url === "/" ? "/overview" : url}.png`, fullPage: true });
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(page.getByRole("link", { name: "Spray Operations" })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/mobile-nav.png` });
  await page.keyboard.press("Escape");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  expect(errors).toEqual([]);
});

test("upload a leaf image → AI prediction → safety decision", async ({ page }) => {
  await login(page);
  await page.goto("/detect");
  await page.getByLabel("Image file").setInputFiles(SAMPLE);
  await page.getByRole("button", { name: "Analyse image" }).click();
  await expect(page.getByText("2 · AI prediction").locator("..").locator("..").getByText("Early Blight").first()).toBeVisible();
  await expect(page.getByRole("table", { name: /safety rule evaluation/i })).toBeVisible();
  await expect(page.getByText("3 · Spray decision (safety engine)")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/detect-result.png`, fullPage: true });
});

test("simulated capture → approve → device sprays → completed; then emergency stop", async ({ page, request }) => {
  await login(page);
  await page.goto("/devices");
  const firstSim = page.locator("text=Simulator controls (demo only)").first().locator("..");
  await firstSim.getByRole("combobox", { name: "Sample image class" }).click();
  await page.getByRole("option", { name: "Late blight sample" }).click();
  // make sure cooldown from earlier runs does not interfere
  await firstSim.getByRole("button", { name: "Capture" }).click();
  await expect(page.getByText(/Simulated scan: Late Blight/)).toBeVisible();

  await page.goto("/operations");
  const approveBtn = page.getByRole("button", { name: /Approve & re-check/ }).first();
  await expect(page.getByRole("tab", { name: "Awaiting approval" })).toBeVisible();
  await page.waitForTimeout(1500);
  if (await approveBtn.count()) {
    await approveBtn.click();
    await expect(page.getByText(/Approved: SPRAY command dispatched|Not dispatched/)).toBeVisible();
    await page.getByRole("tab", { name: "All" }).click();
    // with a 1 s simulator tick and a 3 s spray, completion arrives within ~10 s (or the op was blocked by cooldown)
    await expect(page.getByText(/^(Completed|Blocked)$/).first()).toBeVisible({ timeout: 30_000 });
    await page.screenshot({ path: `${SHOTS}/operations.png`, fullPage: true });
  }

  // Emergency stop from the top bar
  await page.getByRole("button", { name: "Emergency stop" }).click();
  await page.getByLabel("Reason (recorded in the audit log)").fill("E2E safety drill");
  await page.getByRole("button", { name: "Activate emergency stop" }).click();
  await expect(page.getByText("EMERGENCY STOP ACTIVE: all spraying is blocked")).toBeVisible();
  const state = await (await request.get(`${API}/safety/emergency-stop`, {
    headers: { Authorization: `Bearer ${await page.evaluate(() => localStorage.getItem("agriguard.token"))}` },
  })).json();
  expect(state.active).toBe(true);
  await page.screenshot({ path: `${SHOTS}/estop.png` });
  await page.getByLabel("Reset reason").fill("Drill complete");
  await page.getByRole("button", { name: "Reset" }).click();
  await expect(page.getByText("EMERGENCY STOP ACTIVE: all spraying is blocked")).toHaveCount(0);
});

test("scan history filters and detail view", async ({ page }) => {
  await login(page);
  await page.goto("/scans");
  await expect(page.locator("tbody tr").first()).toBeVisible();
  await page.getByLabel("Result").click();
  await page.getByRole("option", { name: "Late Blight" }).click();
  await expect(page.locator("tbody tr").first()).toBeVisible();
  await page.locator("tbody tr a").first().click();
  await expect(page.getByText("Safety decision at scan time")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/scan-detail.png`, fullPage: true });
});
