import { type Locator } from '@playwright/test';
import { test, expect, type Page } from '../lib/test-base';
import { resetBackend } from '../lib/reset';
import { waitForPage } from '../lib/ui';

/** Each engine card is itself the launch button. */
function engineCard(page: Page, engine: string): Locator {
  return page.getByRole('button', { name: `Open terminal · ${engine}` });
}

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoLaunch(page: Page): Promise<void> {
  await page.goto('/launch');
  await waitForPage(page, 'Local Terminal');
  await expect(engineCard(page, 'Claude')).toBeVisible();
  // Seeded by /api/__e2e_reset: one registered project pointing at $HOME.
  // The page has no workspace field of its own any more — the header switcher
  // owns the selection, and the launcher reports the directory it resolved to.
  await expect(page.getByTestId('launch-workspace')).not.toBeEmpty();
}

test('opening an engine streams its output into an in-browser terminal', async ({ page }) => {
  await gotoLaunch(page);
  await engineCard(page, 'Codex').click();

  await expect(page.locator('.xterm')).toBeVisible();
  // The fake `codex` binary (web/frontend/e2e/fixtures/fake-engines) sleeps
  // 4s on a headless-launch invocation, then prints this line and exits —
  // proving output actually streamed from the spawned process, not a stub.
  await expect(page.locator('.xterm-accessibility-tree')).toContainText(
    '(fake codex) ok:',
    { timeout: 10000 },
  );
  // The process exiting on its own must be surfaced, not leave a silently
  // dead connection.
  await expect(page.getByText(/Session ended \(exit code/)).toBeVisible();
});

test('closing a terminal returns to the engine picker', async ({ page }) => {
  await gotoLaunch(page);
  await engineCard(page, 'Claude').click();
  await expect(page.locator('.xterm')).toBeVisible();

  await page.getByRole('button', { name: /Close terminal/i }).click();
  await expect(engineCard(page, 'Claude')).toBeVisible();
  await expect(engineCard(page, 'Codex')).toBeVisible();
});

test('unavailable browser terminal is explained and launch actions are disabled', async ({ page }) => {
  await page.route('**/api/pty/status', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      available: false,
      reason: 'Browser terminal is not supported on Windows yet',
    }),
  }));

  await page.goto('/launch');
  await waitForPage(page, 'Local Terminal');
  await expect(page.getByText('Browser terminal unavailable')).toBeVisible();
  await expect(engineCard(page, 'Claude')).toBeDisabled();
});
