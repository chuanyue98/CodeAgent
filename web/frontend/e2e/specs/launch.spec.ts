import { test, expect, type Page } from '@playwright/test';
import { resetBackend } from '../lib/reset';
import { waitForH2, cardByText } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoLaunch(page: Page): Promise<void> {
  await page.goto('/launch');
  await waitForH2(page, 'Local Terminal');
  await expect(cardByText(page, 'Claude')).toBeVisible();
  // Seeded by /api/__e2e_reset: one registered project pointing at $HOME.
  await expect(page.locator('#launchpad-project')).not.toHaveValue('');
}

test('opening an engine streams its output into an in-browser terminal', async ({ page }) => {
  await gotoLaunch(page);
  const codexCard = cardByText(page, 'Codex');
  await codexCard.getByRole('button', { name: 'Open terminal' }).click();

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
  await cardByText(page, 'Claude').getByRole('button', { name: 'Open terminal' }).click();
  await expect(page.locator('.xterm')).toBeVisible();

  await page.getByRole('button', { name: /Close terminal/i }).click();
  await expect(cardByText(page, 'Claude')).toBeVisible();
  await expect(cardByText(page, 'Codex')).toBeVisible();
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
  await waitForH2(page, 'Local Terminal');
  await expect(page.getByText('Browser terminal unavailable')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Open terminal' }).first()).toBeDisabled();
});
