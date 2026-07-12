import { test, expect, type Page } from '@playwright/test';
import { resetBackend } from '../lib/reset';
import { waitForH2 } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoSessions(page: Page): Promise<void> {
  await page.goto('/sessions');
  await waitForH2(page, 'Sessions');
  await expect(page.getByText(/sessions?$/)).toBeVisible();
}

test('renders the seeded sessions and filter panel', async ({ page }) => {
  await gotoSessions(page);
  await expect(page.locator('main')).toContainText('2 sessions');
  await expect(page.getByText('Filters', { exact: true })).toBeVisible();
});

test('search filters the session list', async ({ page }) => {
  await gotoSessions(page);
  await page.getByPlaceholder('Project or session...').fill('e2e-gemini-project');
  await expect(page.locator('main')).toContainText('1 session');
  await expect(page.locator('main')).toContainText('e2e-gemini-project');
});

test('engine toggle narrows the list to that engine', async ({ page }) => {
  await gotoSessions(page);
  await page.getByRole('button', { name: 'gemini' }).click();
  await expect(page.locator('main')).toContainText('1 session');
  // Toggle it off again — selection is additive, so this returns to all.
  await page.getByRole('button', { name: 'gemini' }).click();
  await expect(page.locator('main')).toContainText('2 sessions');
});

test('sort buttons toggle their direction', async ({ page }) => {
  await gotoSessions(page);
  const costBtn = page.getByRole('button', { name: 'Cost' });
  await costBtn.click();
  await expect(costBtn).toContainText('↓');
  await costBtn.click();
  await expect(costBtn).toContainText('↑');
});

test('expanding a session row reveals its model breakdown', async ({ page }) => {
  await gotoSessions(page);
  await page.locator('div.cursor-pointer', { hasText: 'e2e-claude-project' }).click();
  await expect(page.locator('main')).toContainText('Model Breakdown');
});
