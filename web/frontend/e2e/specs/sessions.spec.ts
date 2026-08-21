import { test, expect, type Page } from '../lib/test-base';
import { resetBackend } from '../lib/reset';
import { waitForH2 } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoSessions(page: Page): Promise<void> {
  await page.goto('/sessions');
  await waitForH2(page, 'History');
  await expect(page.getByText(/sessions?$/)).toBeVisible();
}

test('renders the seeded sessions and filter panel', async ({ page }) => {
  await gotoSessions(page);
  await expect(page.locator('main')).toContainText('2 sessions');
  await expect(page.getByText('Filters', { exact: true })).toBeVisible();
});

test('search filters the session list', async ({ page }) => {
  await gotoSessions(page);
  await page.getByPlaceholder('Title, project or id…').fill('e2e-gemini-project');
  await expect(page.locator('main')).toContainText('1 session');
  await expect(page.locator('main')).toContainText('e2e-gemini-project');
});

test('engine toggle narrows the list to that engine', async ({ page }) => {
  await gotoSessions(page);
  const geminiFilter = page.getByTestId('session-filters').getByRole('button', { name: 'gemini' });
  await geminiFilter.click();
  await expect(page.locator('main')).toContainText('1 session');
  // Toggle it off again — selection is additive, so this returns to all.
  await geminiFilter.click();
  await expect(page.locator('main')).toContainText('2 sessions');
});

test('expanding a session row reveals its conversation', async ({ page }) => {
  await gotoSessions(page);
  // new SessionsPage expands via the chevron button, not the whole row
  const row = page.locator('div.border', { hasText: 'e2e-claude-project' }).first();
  await row.getByRole('button', { name: /Expand conversation/ }).click();
  await expect(page.locator('main')).toContainText('Continue');
});
