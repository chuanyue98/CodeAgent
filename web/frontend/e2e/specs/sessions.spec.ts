import { test, expect, type Page } from '../lib/test-base';
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
  const geminiFilter = page.getByTestId('activity-filters').getByRole('button', { name: 'gemini' });
  await geminiFilter.click();
  await expect(page.locator('main')).toContainText('1 session');
  // Toggle it off again — selection is additive, so this returns to all.
  await geminiFilter.click();
  await expect(page.locator('main')).toContainText('2 sessions');
});

test('filters survive switching to the Timeline tab', async ({ page }) => {
  await gotoSessions(page);
  await page.getByPlaceholder('Project or session...').fill('e2e-gemini-project');
  await expect(page.locator('main')).toContainText('1 session');

  await page
    .getByRole('navigation', { name: 'Activity sections' })
    .getByRole('link', { name: 'Timeline' })
    .click();

  await waitForH2(page, 'Timeline');
  await expect(page.getByPlaceholder('Project, session, content...')).toHaveValue(
    'e2e-gemini-project',
  );
});

test('sort buttons toggle their direction', async ({ page }) => {
  await gotoSessions(page);
  const costBtn = page.getByRole('button', { name: 'Cost' });
  await costBtn.click();
  await expect(costBtn).toContainText('↓');
  await costBtn.click();
  await expect(costBtn).toContainText('↑');
});

test('opening a session row shows its detail panel', async ({ page }) => {
  await gotoSessions(page);
  await page.locator('div.cursor-pointer', { hasText: 'e2e-claude-project' }).click();

  const panel = page.getByTestId('session-detail');
  await expect(panel).toBeVisible();
  // Usage, the transcript and the per-session actions all live here now,
  // instead of being split across this tab and the Timeline tab.
  await expect(panel).toContainText('Usage');
  await expect(panel).toContainText('Conversation');
  await expect(panel.getByRole('button', { name: /Delete this session/ })).toBeVisible();

  await panel.getByLabel('Close session details').click();
  await expect(page.getByTestId('session-detail')).toHaveCount(0);
});
