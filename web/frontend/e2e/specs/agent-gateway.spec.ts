import { test, expect, type Page } from '@playwright/test';
import { resetBackend } from '../lib/reset';
import { waitForH2 } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoAgent(page: Page): Promise<void> {
  await page.goto('/agent/web');
  await waitForH2(page, 'Web Agent');
  await expect(page.getByPlaceholder(/Message the agent/)).toBeVisible();
  await expect(page.getByLabel('Workspace')).not.toHaveValue('');
  await expect(page.getByLabel('Provider')).toHaveValue('fake');
}

test('creates a structured session and streams provider-neutral events', async ({ page }) => {
  await gotoAgent(page);
  const composer = page.getByPlaceholder(/Message the agent/);
  await composer.fill('hello gateway');
  await composer.press('Enter');

  await expect(page.locator('main')).toContainText('Echo: hello gateway');
  await expect(page.locator('main')).toContainText('Interactive');
  await expect(page.getByLabel('Workspace')).toBeDisabled();
  await expect(page.getByLabel('Provider')).toBeDisabled();
});

test('activity drawer keeps protocol details out of the conversation by default', async ({ page }) => {
  await gotoAgent(page);
  const composer = page.getByPlaceholder(/Message the agent/);
  await composer.fill('show activity');
  await composer.press('Enter');
  await expect(page.locator('main')).toContainText('Echo: show activity');

  await page.getByRole('button', { name: 'Open activity' }).click();
  await expect(page.getByRole('main').getByText('Activity', { exact: true })).toBeVisible();
  await expect(page.getByText(/message\.delta/)).toBeVisible();
  await page.getByRole('button', { name: 'Close activity' }).click();
  await expect(page.getByText('Tools, diffs, usage, and protocol events')).not.toBeVisible();
});

test('replays a stored conversation when a session is resumed', async ({ page }) => {
  await gotoAgent(page);
  const composer = page.getByPlaceholder(/Message the agent/);
  await composer.fill('persist me');
  await composer.press('Enter');
  await expect(page.locator('main')).toContainText('Echo: persist me');

  await page.getByRole('button', { name: 'New', exact: true }).click();
  await page.getByRole('button', { name: /persist me/i }).click();
  await expect(page.locator('main')).toContainText('Echo: persist me');
});
