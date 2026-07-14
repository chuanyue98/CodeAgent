import { test, expect, type Page } from '@playwright/test';
import { resetBackend } from '../lib/reset';
import { waitForH2, cardByText } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoLaunch(page: Page): Promise<void> {
  await page.route('**/api/launch/status', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ available: true, terminal: 'xterm', mode: 'local_gui' }),
  }));
  await page.route(/\/api\/launch\/(claude|gemini|opencode|codex)$/, route => {
    const engine = route.request().url().split('/').pop();
    return route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ status: 'launched', engine, terminal: 'xterm' }),
    });
  });
  await page.goto('/launch');
  await waitForH2(page, 'Local Terminal');
  await expect(cardByText(page, 'Claude')).toBeVisible();
}

test('clicking launch shows the launched state for that engine', async ({
  page,
}) => {
  await gotoLaunch(page);
  const claudeCard = cardByText(page, 'Claude');
  await claudeCard.getByRole('button').click();
  await expect(claudeCard).toContainText('Opened in xterm', { timeout: 15000 });
});

test('each engine card is independently launchable', async ({ page }) => {
  await gotoLaunch(page);
  for (const name of ['Claude', 'Gemini', 'OpenCode', 'Codex']) {
    const card = cardByText(page, name);
    await card.getByRole('button').click();
    await expect(card).toContainText('Opened in xterm', { timeout: 15000 });
  }
});

test('unavailable local terminal is explained and launch actions are disabled', async ({ page }) => {
  await page.route('**/api/launch/status', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      available: false,
      terminal: null,
      mode: 'local_gui',
      reason: 'No supported GUI terminal emulator was found on the CodeAgent server',
    }),
  }));

  await page.goto('/launch');
  await waitForH2(page, 'Local Terminal');
  await expect(page.getByText('Local terminal unavailable')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Open terminal' }).first()).toBeDisabled();
});
