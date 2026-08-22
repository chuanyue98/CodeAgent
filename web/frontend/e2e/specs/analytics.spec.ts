import { test, expect, type Page } from '../lib/test-base';
import { resetBackend } from '../lib/reset';
import { waitForH2 } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoUsage(page: Page): Promise<void> {
  await page.goto('/analytics');
  await waitForH2(page, 'Usage');
  await expect(page.getByText('Model Breakdown')).toBeVisible();
}

test('every section renders on one page instead of behind sub-tabs', async ({ page }) => {
  await gotoUsage(page);
  const main = page.locator('main');
  await expect(main).toContainText('Total Cost');
  await expect(main).toContainText('Cost by engine');
  await expect(main).toContainText('Tokens by engine');
  await expect(main).toContainText('Model Breakdown');
});

test('the range control rescopes the page', async ({ page }) => {
  await gotoUsage(page);
  const range = page.getByRole('group', { name: 'Time range' });
  await expect(range.getByRole('button', { name: '30 days' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );

  // All time rolls the series up by month; the narrow ranges go by day.
  await range.getByRole('button', { name: 'All time' }).click();
  await expect(page.locator('main')).toContainText('per month');

  await range.getByRole('button', { name: '7 days' }).click();
  await expect(page.locator('main')).toContainText('last 7 days');
});

test('selecting a model in the breakdown opens and closes its detail', async ({
  page,
}) => {
  await gotoUsage(page);
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
  await gotoUsage(page);
  await expect(page.locator('svg.recharts-surface').first()).toBeVisible();
  await page.getByRole('button', { name: 'Refresh' }).click();
  await expect(page.getByText('Model Breakdown')).toBeVisible();
});
