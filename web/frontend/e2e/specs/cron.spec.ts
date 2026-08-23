import { test, expect, type Page } from '../lib/test-base';
import { resetBackend } from '../lib/reset';
import { waitForH2 } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoCron(page: Page): Promise<void> {
  await page.goto('/cron');
  await waitForH2(page, '定时任务');
  await expect(page.getByLabel('工作区', { exact: true })).not.toHaveValue('');
  await expect(page.getByText('还没有定时计划')).toBeVisible();
}

test('creating a schedule adds it to the list', async ({ page }) => {
  await gotoCron(page);
  await page.getByLabel('任务').selectOption('db-migrate');
  await page.getByLabel('引擎').selectOption('claude');
  await page.getByPlaceholder('0 9 * * *').fill('0 0 * * *');
  await page.getByRole('button', { name: '创建定时计划' }).click();
  await expect(page.locator('main')).toContainText('db-migrate');
  await expect(page.locator('main')).toContainText('下次：');
});

test('toggling a schedule disables then re-enables it', async ({ page }) => {
  await gotoCron(page);
  await page.getByLabel('任务').selectOption('db-migrate');
  await page.getByLabel('引擎').selectOption('claude');
  await page.getByPlaceholder('0 9 * * *').fill('0 0 * * *');
  await page.getByRole('button', { name: '创建定时计划' }).click();
  await page.getByTitle('停用').click();
  await expect(page.getByTitle('启用')).toBeVisible();
  await page.getByTitle('启用').click();
  await expect(page.getByTitle('停用')).toBeVisible();
});

test('deleting a schedule returns to the empty state', async ({ page }) => {
  await gotoCron(page);
  await page.getByLabel('任务').selectOption('db-migrate');
  await page.getByLabel('引擎').selectOption('claude');
  await page.getByPlaceholder('0 9 * * *').fill('0 0 * * *');
  await page.getByRole('button', { name: '创建定时计划' }).click();
  await page.getByTitle('删除').click();
  await page.getByRole('alertdialog').getByRole('button', { name: '删除' }).click();
  await expect(page.getByText('还没有定时计划')).toBeVisible();
});
