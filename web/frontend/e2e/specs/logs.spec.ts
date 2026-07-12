import { test, expect, type Page } from '@playwright/test';
import { resetBackend } from '../lib/reset';
import { waitForH2 } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoLogs(page: Page): Promise<void> {
  await page.goto('/logs');
  await waitForH2(page, 'Logs');
}

const autoScrollBtn = (page: Page) =>
  page.getByRole('button', { name: /Auto-scroll/ });

test('auto-scroll toggle flips between ON and OFF', async ({ page }) => {
  await gotoLogs(page);
  await expect(autoScrollBtn(page)).toHaveText(/Auto-scroll ON/);
  await autoScrollBtn(page).click();
  await expect(autoScrollBtn(page)).toHaveText(/Auto-scroll OFF/);
  await autoScrollBtn(page).click();
  await expect(autoScrollBtn(page)).toHaveText(/Auto-scroll ON/);
});

test('selecting a log file highlights it and clears the empty state', async ({
  page,
}) => {
  await gotoLogs(page);
  const files = page.locator('main button', { hasText: /\.log$/ });
  const count = await files.count();
  if (count === 0) {
    await expect(page.locator('main')).toContainText('No log files');
    return;
  }
  const first = files.first();
  await first.click();
  await expect(first).toHaveClass(/bg-slate-100/);
  await expect(page.locator('main')).not.toContainText('No log files');
});
