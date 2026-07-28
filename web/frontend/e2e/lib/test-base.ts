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

export const test = base.extend({
  baseURL: async ({}, use, testInfo) => {
    await use(`http://127.0.0.1:${BASE_PORT + testInfo.parallelIndex}`);
  },
});

export { expect } from '@playwright/test';
export type { Page };
