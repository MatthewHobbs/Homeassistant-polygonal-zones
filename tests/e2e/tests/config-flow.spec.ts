import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

const HA_URL = process.env.HA_URL ?? "http://127.0.0.1:8123";

// HA's login state lives in localStorage under `hassTokens`. Relying on
// Playwright's storageState to carry localStorage proved flaky (it only
// persists localStorage for origins captured at storageState() time, and the
// restore raced the frontend bootstrap), so the browser kept landing on the
// login page. Instead inject the tokens the setup wrote to .auth/tokens.json
// via addInitScript — that runs BEFORE the HA frontend's scripts on every
// navigation, so the token is always present when the app reads it. The file is
// read inside beforeEach (not at module scope) so it exists: the `setup`
// project dependency has already run by the time the chromium test executes,
// whereas module scope evaluates during collection, before setup runs.
test.beforeEach(async ({ page }) => {
  const tokens = readFileSync(".auth/tokens.json", "utf8");
  await page.addInitScript((t) => {
    window.localStorage.setItem("hassTokens", t);
  }, tokens);
  void HA_URL;
});

test("Polygonal Zones appears in the Add Integration dialog", async ({ page }) => {
  // Land on the app root first so the frontend bundle hydrates and the
  // websocket authenticates against the seeded token. Going straight to a deep
  // panel on a cold instance can race the auth/bootstrap and bounce to
  // /onboarding or /auth, after which the "Add integration" button never
  // appears — wait for the top-level <home-assistant> shell before navigating.
  await page.goto("/");
  await expect(page.locator("home-assistant")).toBeAttached({ timeout: 30_000 });
  // If onboarding/auth didn't complete we'd be parked on those routes; fail
  // fast with a clear message instead of a generic button-not-found timeout.
  await expect(page, "redirected away from the app — auth/onboarding incomplete")
    .not.toHaveURL(/\/(onboarding|auth)\b/, { timeout: 30_000 });

  // Now deep-link into the integrations page. Avoid depending on the
  // sidebar/dashboard layout, which changes between HA frontend versions.
  await page.goto("/config/integrations/dashboard");

  // The HA frontend is a deep web-component tree; getByRole pierces shadow DOM.
  // Allow extra time on the first cold render of this panel.
  const addButton = page.getByRole("button", { name: /add integration/i });
  await expect(addButton).toBeVisible({ timeout: 30_000 });
  await addButton.click();

  // The Add Integration dialog has a search box; type the integration name.
  const search = page.getByRole("textbox").first();
  await search.fill("Polygonal Zones");

  // The integration must be discoverable by its manifest `name`. The dialog
  // builds the full integration list on first open — a cold WS fetch that can
  // exceed the 15s default in CI (it passed only on the warm retry otherwise) —
  // so give it the same 30s budget as the earlier steps.
  await expect(page.getByText("Polygonal Zones", { exact: false })).toBeVisible({
    timeout: 30_000
  });
});
