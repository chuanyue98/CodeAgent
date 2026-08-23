import { test, expect } from '../lib/test-base';
import { resetBackend } from '../lib/reset';
import { waitForH2 } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

test('SystemPanel opens from the header status button and expands/collapses its details', async ({ page }) => {
  await page.goto('/');
  const statusButton = page.getByTestId('system-status-button');
  await expect(statusButton).toBeVisible();
  await expect(page.getByTestId('system-metrics')).toHaveCount(0);

  await statusButton.click();
  const detailsBtn = page.getByRole('button', { name: '详情' });
  await expect(detailsBtn).toBeVisible();
  await detailsBtn.click();
  await expect(page.getByText('历史数据库')).toBeVisible();
  await page.getByRole('button', { name: '收起' }).click();
  await expect(page.getByText('历史数据库')).toHaveCount(0);

  await statusButton.click();
  await expect(page.getByTestId('system-metrics')).toHaveCount(0);
});

test('/system page renders metrics and Refresh reloads', async ({ page }) => {
  await page.goto('/system');
  await waitForH2(page, '系统');
  await expect(page.getByText('指标')).toBeVisible();
  await page.getByRole('button', { name: '刷新' }).click();
  await expect(page.getByText('指标')).toBeVisible();
});
