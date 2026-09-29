import { test, expect } from '../lib/test-base';
import { resetBackend } from '../lib/reset';
import { waitForPage } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

// The fake engine binaries echo their argv (web/frontend/e2e/fixtures/
// fake-engines), so the first message showing up in the terminal proves the
// whole path: composer -> POST /api/pty/prompt -> websocket -> engine argv.
test('the composer starts the chosen engine with its first message', async ({ page }) => {
  await page.goto('/');
  await waitForPage(page, 'Overview');

  await page.getByRole('group', { name: 'Engine for the new session' }).getByRole('button', { name: 'Codex' }).click();
  await page.getByLabel('First message for the new session').fill('e2e-first-message');
  await page.getByRole('button', { name: 'Start', exact: true }).click();

  await expect(page).toHaveURL(/\/agent\/terminal$/);
  await expect(page.locator('.xterm')).toBeVisible();
  const screen = page.locator('.xterm-accessibility-tree');
  await expect(screen).toContainText('(fake codex) ok:', { timeout: 30_000 });
  await expect(screen).toContainText('e2e-first-message');
});
