import { test, expect } from "@playwright/test";

const HA_URL = process.env.HA_URL ?? "http://127.0.0.1:8123";

// Re-seed the auth tokens into localStorage on every page we open. HA's login
// state lives in localStorage, which Playwright's storageState restores, but
// we set it defensively here too in case the origin wasn't captured.
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    // No-op placeholder hook; storageState already carries hassTokens. Kept so
    // a future token refresh can be injected here without touching each test.
  });
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

  // The integration must be discoverable by its manifest `name`.
  await expect(page.getByText("Polygonal Zones", { exact: false })).toBeVisible();
});
