import { test, expect, type Page } from '../lib/test-base';
import { resetBackend } from '../lib/reset';
import { waitForPage } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoCron(page: Page): Promise<void> {
  await page.goto('/cron');
  await waitForPage(page, 'Schedules');
  await expect(page.getByLabel('Workspace', { exact: true })).not.toHaveValue('');
  await expect(page.getByText('No schedules yet.')).toBeVisible();
}

test('creating a schedule adds it to the list', async ({ page }) => {
  await gotoCron(page);
  await page.getByLabel('Task').selectOption('db-migrate');
  await page.getByLabel('Engine').selectOption('claude');
  await page.getByPlaceholder('0 9 * * *').fill('0 0 * * *');
  await page.getByRole('button', { name: 'Create Schedule' }).click();
  await expect(page.locator('main')).toContainText('db-migrate');
  await expect(page.locator('main')).toContainText('Next:');
});

test('toggling a schedule disables then re-enables it', async ({ page }) => {
  await gotoCron(page);
  await page.getByLabel('Task').selectOption('db-migrate');
  await page.getByLabel('Engine').selectOption('claude');
  await page.getByPlaceholder('0 9 * * *').fill('0 0 * * *');
  await page.getByRole('button', { name: 'Create Schedule' }).click();
  await page.getByTitle('Disable').click();
  await expect(page.getByTitle('Enable')).toBeVisible();
  await page.getByTitle('Enable').click();
  await expect(page.getByTitle('Disable')).toBeVisible();
});

test('deleting a schedule returns to the empty state', async ({ page }) => {
  await gotoCron(page);
  await page.getByLabel('Task').selectOption('db-migrate');
  await page.getByLabel('Engine').selectOption('claude');
  await page.getByPlaceholder('0 9 * * *').fill('0 0 * * *');
  await page.getByRole('button', { name: 'Create Schedule' }).click();
  await page.getByTitle('Delete').click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'Delete' }).click();
  await expect(page.getByText('No schedules yet.')).toBeVisible();
});
