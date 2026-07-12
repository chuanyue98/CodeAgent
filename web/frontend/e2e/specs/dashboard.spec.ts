import { test, expect, type Page } from '@playwright/test';
import { resetBackend } from '../lib/reset';
import { waitForH2 } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoDashboard(page: Page): Promise<void> {
  await page.goto('/dashboard');
  await waitForH2(page, 'Dashboard');
  await expect(page.getByText(/tasks available/i)).toBeVisible();
}

test('lists the seeded tasks', async ({ page }) => {
  await gotoDashboard(page);
  await expect(page.locator('main')).toContainText(/tasks available/);
  await expect(page.getByText('DB Migrate')).toBeVisible();
});

test('clicking a task opens its detail view, back returns to list', async ({
  page,
}) => {
  await gotoDashboard(page);
  await page.locator('main button', { hasText: /DB Migrate/i }).first().click();
  await expect(page.getByRole('button', { name: 'Run Task' })).toBeVisible();
  await page.getByRole('button', { name: 'Back' }).click();
  await expect(page.getByText(/tasks available/i)).toBeVisible();
});

test('running a task shows execution logs and a Stop control', async ({
  page,
}) => {
  await gotoDashboard(page);
  await page.locator('main button', { hasText: /DB Migrate/i }).first().click();
  await page.getByRole('button', { name: 'Run Task' }).click();
  await expect(page.getByText('Execution Logs')).toBeVisible({ timeout: 15000 });
  await expect(page.locator('button').filter({ hasText: 'Stop Execution' })).toBeVisible();
  await page.locator('button').filter({ hasText: 'Stop Execution' }).click();
  await expect(page.getByRole('button', { name: 'Run Task' })).toBeVisible();
});
