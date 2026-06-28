import { test as setup, expect, request } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";

const HA_URL = process.env.HA_URL ?? "http://127.0.0.1:8123";
// HA uses the frontend origin as the OAuth client_id; the token we mint must
// be tied to the same client_id we later seed into localStorage.
const CLIENT_ID = `${HA_URL}/`;
const AUTH_DIR = ".auth";
const STATE_PATH = `${AUTH_DIR}/state.json`;

// Demo owner account created via the onboarding API. CI-only throwaway creds.
const USER = { name: "CI", username: "ci", password: "ci-smoke-password" };

/**
 * Poll the HA API until it stops returning connection errors / 502s, i.e. the
 * core has finished its (potentially slow) first boot.
 */
async function waitForHA(api: import("@playwright/test").APIRequestContext) {
  const deadline = Date.now() + 120_000;
  while (Date.now() < deadline) {
    try {
      const res = await api.get(`${HA_URL}/manifest.json`);
      if (res.ok()) return;
    } catch {
      // not up yet
    }
    await new Promise((r) => setTimeout(r, 2000));
  }
  throw new Error("Home Assistant did not become reachable within 120s");
}

setup("boot HA, onboard, and persist auth", async ({ browser }) => {
  const api = await request.newContext();
  await waitForHA(api);

  // 1) Create the owner account. Returns a one-time auth code.
  //    TODO: HA occasionally adjusts the onboarding payload between versions —
  //    if this 4xx's, diff against the browser's onboarding network calls.
  const userRes = await api.post(`${HA_URL}/api/onboarding/users`, {
    data: { ...USER, language: "en", client_id: CLIENT_ID }
  });
  expect(userRes.ok(), `onboarding/users failed: ${await userRes.text()}`).toBeTruthy();
  const { auth_code: authCode } = await userRes.json();

  // 2) Exchange the auth code for access + refresh tokens.
  const tokenRes = await api.post(`${HA_URL}/auth/token`, {
    form: { grant_type: "authorization_code", code: authCode, client_id: CLIENT_ID }
  });
  expect(tokenRes.ok(), `auth/token failed: ${await tokenRes.text()}`).toBeTruthy();
  const tokens = await tokenRes.json();

  // 3) Finish the remaining onboarding steps so the UI lands on the normal
  //    dashboard rather than the wizard. The `integration` step is the one that
  //    actually marks onboarding COMPLETE — without it HA keeps redirecting the
  //    frontend back to /onboarding, so /config/integrations never renders and
  //    the "Add integration" button is never found (the original flake). We
  //    assert it; core_config/analytics stay best-effort.
  const auth = { Authorization: `Bearer ${tokens.access_token}` };
  await api.post(`${HA_URL}/api/onboarding/core_config`, { headers: auth, data: {} });
  await api.post(`${HA_URL}/api/onboarding/analytics`, { headers: auth, data: {} });
  const integrationRes = await api.post(`${HA_URL}/api/onboarding/integration`, {
    headers: auth,
    data: { client_id: CLIENT_ID, redirect_uri: `${HA_URL}/?auth_callback=1` }
  });
  expect(
    integrationRes.ok(),
    `onboarding/integration failed: ${await integrationRes.text()}`
  ).toBeTruthy();

  // 4) Seed the tokens into localStorage the way the HA frontend stores them,
  //    so the browser context is logged in without driving the login form.
  const hassTokens = {
    ...tokens,
    expires: Date.now() + tokens.expires_in * 1000,
    hassUrl: HA_URL,
    clientId: CLIENT_ID
  };

  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto(`${HA_URL}/`);
  await page.evaluate((t) => {
    window.localStorage.setItem("hassTokens", JSON.stringify(t));
  }, hassTokens);

  mkdirSync(AUTH_DIR, { recursive: true });
  await context.storageState({ path: STATE_PATH });
  // storageState only persists cookies + origin localStorage Playwright knows
  // about; write a copy so a flaky persist still leaves usable creds behind.
  writeFileSync(`${AUTH_DIR}/tokens.json`, JSON.stringify(hassTokens, null, 2));

  await context.close();
  await api.dispose();
});
