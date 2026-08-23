import { test, expect, type Page } from '../lib/test-base';
import { resetBackend } from '../lib/reset';
import { waitForH2 } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoDashboard(page: Page): Promise<void> {
  await page.goto('/dashboard');
  await waitForH2(page, '任务');
  await expect(page.getByText(/个任务/)).toBeVisible();
}

test('lists the seeded tasks', async ({ page }) => {
  await gotoDashboard(page);
  await expect(page.locator('main')).toContainText(/个任务/);
  await expect(page.getByText('DB Migrate')).toBeVisible();
});

test('clicking a task opens its detail view, back returns to list', async ({
  page,
}) => {
  await gotoDashboard(page);
  await page.locator('main button', { hasText: /DB Migrate/i }).first().click();
  await expect(page.getByRole('button', { name: '运行任务' })).toBeVisible();
  await page.getByRole('button', { name: '返回' }).click();
  await expect(page.getByText(/个任务/)).toBeVisible();
});

test('running a task shows execution logs and a Stop control', async ({
  page,
}) => {
  await gotoDashboard(page);
  await page.locator('main button', { hasText: /DB Migrate/i }).first().click();
  await page.getByRole('button', { name: '运行任务' }).click();
  await expect(page.getByText('执行日志')).toBeVisible({ timeout: 15000 });
  await expect(page.locator('button').filter({ hasText: '停止执行' })).toBeVisible();
  await page.locator('button').filter({ hasText: '停止执行' }).click();
  await expect(page.getByRole('button', { name: '运行任务' })).toBeVisible();
});
