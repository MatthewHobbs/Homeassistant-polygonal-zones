import { defineConfig, devices } from "@playwright/test";

// Home Assistant base URL — overridable so the same config works in CI and
// against a locally running `hass` instance.
const HA_URL = process.env.HA_URL ?? "http://127.0.0.1:8123";

export default defineConfig({
  testDir: "./tests",
  // HA can be slow to finish booting + onboarding on a cold CI runner.
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: HA_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure"
  },
  projects: [
    // `setup` waits for HA to come up, completes onboarding via the REST API,
    // and writes an authenticated storage state the smoke test reuses.
    { name: "setup", testMatch: /global\.setup\.ts/ },
    {
      name: "chromium",
      dependencies: ["setup"],
      use: { ...devices["Desktop Chrome"], storageState: ".auth/state.json" }
    }
  ]
});
