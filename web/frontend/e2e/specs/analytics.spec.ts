import { test, expect, type Page } from '@playwright/test';
import { resetBackend } from '../lib/reset';
import { waitForH2 } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoAnalytics(page: Page): Promise<void> {
  await page.goto('/analytics');
  await waitForH2(page, 'Analytics');
  await expect(page.getByText('Model Breakdown')).toBeVisible();
}

test('the four tabs each render distinct content', async ({ page }) => {
  await gotoAnalytics(page);
  await page.getByRole('button', { name: 'Daily', exact: true }).click();
  await expect(page.locator('main')).toContainText('Daily Cost by Engine');
  await page.getByRole('button', { name: 'Monthly', exact: true }).click();
  await expect(page.locator('main')).toContainText('Monthly Cost by Engine');
  await page.getByRole('button', { name: 'Sessions', exact: true }).click();
  await expect(page.locator('main')).toContainText('e2e-claude-project');
  await page.getByRole('button', { name: 'Overview', exact: true }).click();
  await expect(page.locator('main')).toContainText('Model Breakdown');
});

test('selecting a model in the breakdown opens and closes its detail', async ({
  page,
}) => {
  await gotoAnalytics(page);
  const firstModel = page
    .locator('div.glass-card', { hasText: 'Model Breakdown' })
    .getByRole('button')
    .first();
  await firstModel.click();
  await expect(page.locator('main')).toContainText('Token Breakdown');
  await firstModel.click();
  await expect(page.locator('main')).not.toContainText('Token Breakdown');
});

test('charts render as SVG and Refresh reloads without error', async ({ page }) => {
  await gotoAnalytics(page);
  await expect(page.locator('svg.recharts-surface').first()).toBeVisible();
  await page.getByRole('button', { name: 'Refresh' }).click();
  await expect(page.getByText('Model Breakdown')).toBeVisible();
});
