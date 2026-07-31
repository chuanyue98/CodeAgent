import { expect } from '@playwright/test';

/**
 * Resets the isolated E2E backend to its clean baseline between specs.
 *
 * Hits POST /api/__e2e_reset (mounted only when CA_E2E=1 — see
 * core/web/routers/e2e.py). We call it via a bare fetch rather than
 * page.request so it is independent of any page-level state.
 */
export async function resetBackend(baseURL: string): Promise<void> {
  const res = await fetch(`${baseURL}/api/__e2e_reset`, {
    method: 'POST',
    // Same UI token the browser gets seeded with in test-base.ts; this
    // call bypasses the page, so it carries the header itself.
    headers: { 'X-CA-Token': 'codeagent-e2e-token' },
  });
  const status = res.status;
  expect(
    status,
    `e2e reset failed (status ${status}) — is CA_E2E=1 set in e2e/start-server.sh?`,
  ).toBe(200);
}
