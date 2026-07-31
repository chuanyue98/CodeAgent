import { test as base, type Page } from '@playwright/test';

/**
 * playwright.config.ts starts one isolated backend instance per worker slot
 * (ports BASE_PORT..BASE_PORT+workers-1 — see e2e/start-server.sh, which
 * already gives each invocation its own scratch $HOME/config/resource
 * roots keyed off CA_E2E_PORT). Every spec imports `test`/`expect` from
 * here instead of directly from '@playwright/test' so `baseURL` resolves
 * to *this worker's own backend* rather than one shared instance — that's
 * what lets spec files run concurrently across workers without their
 * beforeEach `resetBackend()` calls stepping on each other's state.
 */
const BASE_PORT = Number(process.env.CA_E2E_PORT || 8798);

/** Matches CA_UI_TOKEN in e2e/start-server.sh. */
const UI_TOKEN = 'codeagent-e2e-token';

export const test = base.extend({
  baseURL: async ({}, use, testInfo) => {
    await use(`http://127.0.0.1:${BASE_PORT + testInfo.parallelIndex}`);
  },

  // The backend requires a UI token on every /api call. In production the
  // launcher passes it as ?ca_token=… and the app lifts it into
  // sessionStorage (src/utils/token.ts); seeding storage directly is the
  // equivalent for specs, and keeps every page.goto() free of a query
  // string that would otherwise have to be threaded through all of them.
  page: async ({ page }, use) => {
    await page.addInitScript(token => {
      sessionStorage.setItem('codeagent.uiToken', token);
    }, UI_TOKEN);
    await use(page);
  },
});

export { expect } from '@playwright/test';
export type { Page };
