import { test as setup, expect, request } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";

const HA_URL = process.env.HA_URL ?? "http://127.0.0.1:8123";
// HA uses the frontend origin as the OAuth client_id; the token we mint must
// be tied to the same client_id we later seed into localStorage.
const CLIENT_ID = `${HA_URL}/`;
const AUTH_DIR = ".auth";

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

setup("boot HA, onboard, and persist auth", async () => {
  const api = await request.newContext();
  await waitForHA(api);

  // 1) Obtain a one-time OAuth auth code. On a fresh instance, create the owner
  //    via onboarding. If HA is already onboarded (e.g. Playwright retried this
  //    setup against the same already-onboarded instance — the users step then
  //    4xx's with "User step already done"), fall back to a normal login with
  //    the same throwaway credentials. Either path yields an auth code.
  let authCode: string;
  let createdUser = false;
  const userRes = await api.post(`${HA_URL}/api/onboarding/users`, {
    data: { ...USER, language: "en", client_id: CLIENT_ID }
  });
  if (userRes.ok()) {
    authCode = (await userRes.json()).auth_code;
    createdUser = true;
  } else {
    // Already onboarded: drive the auth login flow to mint a fresh code.
    const flowRes = await api.post(`${HA_URL}/auth/login_flow`, {
      data: {
        client_id: CLIENT_ID,
        handler: ["homeassistant", null],
        redirect_uri: `${HA_URL}/?auth_callback=1`
      }
    });
    expect(flowRes.ok(), `login_flow start failed: ${await flowRes.text()}`).toBeTruthy();
    const { flow_id: flowId } = await flowRes.json();
    const stepRes = await api.post(`${HA_URL}/auth/login_flow/${flowId}`, {
      data: { client_id: CLIENT_ID, username: USER.username, password: USER.password }
    });
    expect(stepRes.ok(), `login step failed: ${await stepRes.text()}`).toBeTruthy();
    const step = await stepRes.json();
    expect(
      step.type,
      `unexpected login flow result: ${JSON.stringify(step)}`
    ).toBe("create_entry");
    authCode = step.result;
  }

  // 2) Exchange the auth code for access + refresh tokens.
  const tokenRes = await api.post(`${HA_URL}/auth/token`, {
    form: { grant_type: "authorization_code", code: authCode, client_id: CLIENT_ID }
  });
  expect(tokenRes.ok(), `auth/token failed: ${await tokenRes.text()}`).toBeTruthy();
  const tokens = await tokenRes.json();

  // 3) Finish onboarding so the frontend lands on the app, not the wizard. Only
  //    needed when we just created the user; if HA was already onboarded these
  //    are done. The `integration` step is the one that marks onboarding
  //    COMPLETE — without it HA redirects the frontend to /onboarding and
  //    /config/integrations never renders. core_config/analytics stay
  //    best-effort (analytics works even when the analytics component is absent).
  if (createdUser) {
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
  }

  // 4) Persist the tokens in the shape the HA frontend keeps under localStorage
  //    "hassTokens". The config-flow spec reads this file and injects it via
  //    addInitScript before each navigation — more reliable than Playwright
  //    storageState, whose localStorage restore raced the frontend bootstrap
  //    (and whose capture step here destroyed the page context mid-redirect).
  //    No browser is needed in setup.
  const hassTokens = {
    ...tokens,
    expires: Date.now() + tokens.expires_in * 1000,
    hassUrl: HA_URL,
    clientId: CLIENT_ID
  };

  mkdirSync(AUTH_DIR, { recursive: true });
  writeFileSync(`${AUTH_DIR}/tokens.json`, JSON.stringify(hassTokens, null, 2));

  await api.dispose();
});
