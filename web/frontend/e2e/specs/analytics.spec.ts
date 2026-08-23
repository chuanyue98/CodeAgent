import { test, expect, type Page } from '../lib/test-base';
import { resetBackend } from '../lib/reset';
import { waitForH2 } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoUsage(page: Page): Promise<void> {
  await page.goto('/analytics');
  await waitForH2(page, '用量');
  await expect(page.getByText('模型明细')).toBeVisible();
}

test('every section renders on one page instead of behind sub-tabs', async ({ page }) => {
  await gotoUsage(page);
  const main = page.locator('main');
  await expect(main).toContainText('总成本');
  await expect(main).toContainText('按引擎成本');
  await expect(main).toContainText('按引擎 Token');
  await expect(main).toContainText('模型明细');
});

test('the range control rescopes the page', async ({ page }) => {
  await gotoUsage(page);
  const range = page.getByRole('group', { name: '时间范围' });
  await expect(range.getByRole('button', { name: '30 天' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );

  // All time rolls the series up by month; the narrow ranges go by day.
  await range.getByRole('button', { name: '全部' }).click();
  await expect(page.locator('main')).toContainText('按月');

  await range.getByRole('button', { name: '7 天' }).click();
  await expect(page.locator('main')).toContainText('最近 7 天');
});

test('selecting a model in the breakdown opens and closes its detail', async ({
  page,
}) => {
  await gotoUsage(page);
  const firstModel = page
    .locator('div.glass-card', { hasText: '模型明细' })
    .getByRole('button')
    .first();
  await firstModel.click();
  await expect(page.locator('main')).toContainText('Token 明细');
  await firstModel.click();
  await expect(page.locator('main')).not.toContainText('Token 明细');
});

test('charts render as SVG and Refresh reloads without error', async ({ page }) => {
  await gotoUsage(page);
  await expect(page.locator('svg.recharts-surface').first()).toBeVisible();
  await page.getByRole('button', { name: '刷新' }).click();
  await expect(page.getByText('模型明细')).toBeVisible();
});
