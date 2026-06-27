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
  // Deep-link straight into the integrations page to avoid depending on the
  // sidebar/dashboard layout, which changes between HA frontend versions.
  await page.goto("/config/integrations/dashboard");

  // The HA frontend is a deep web-component tree; getByRole pierces shadow DOM.
  const addButton = page.getByRole("button", { name: /add integration/i });
  await expect(addButton).toBeVisible();
  await addButton.click();

  // The Add Integration dialog has a search box; type the integration name.
  const search = page.getByRole("textbox").first();
  await search.fill("Polygonal Zones");

  // The integration must be discoverable by its manifest `name`.
  await expect(page.getByText("Polygonal Zones", { exact: false })).toBeVisible();
});
