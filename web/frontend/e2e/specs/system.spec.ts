import { test, expect } from '@playwright/test';
import { resetBackend } from '../lib/reset';
import { waitForH2 } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

test('SystemPanel expands and collapses its details', async ({ page }) => {
  await page.goto('/');
  const detailsBtn = page.getByRole('button', { name: 'Details' });
  await expect(detailsBtn).toBeVisible();
  await detailsBtn.click();
  await expect(page.getByText('History DB')).toBeVisible();
  await page.getByRole('button', { name: 'Hide' }).click();
  await expect(page.getByText('History DB')).toHaveCount(0);
});

test('/system page renders metrics and Refresh reloads', async ({ page }) => {
  await page.goto('/system');
  await waitForH2(page, 'System');
  await expect(page.getByText('Metrics')).toBeVisible();
  await page.getByRole('button', { name: 'Refresh' }).click();
  await expect(page.getByText('Metrics')).toBeVisible();
});
