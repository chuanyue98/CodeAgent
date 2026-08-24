import { test, expect, type Page } from '../lib/test-base';
import { resetBackend } from '../lib/reset';
import { waitForH2 } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoSessions(page: Page): Promise<void> {
  // Pin "all projects": the e2e baseline config registers the scratch $HOME
  // as the only workspace and the page follows the workspace switcher by
  // default, which would exact-match the seeded /tmp/e2e-* sessions out of
  // the list (0 sessions) instead of showing them.
  await page.goto('/sessions?project=all');
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
  await page.getByPlaceholder('Project or session...').fill('e2e-codebuddy-project');
  await expect(page.locator('main')).toContainText('1 session');
  await expect(page.locator('main')).toContainText('e2e-codebuddy-project');
});

test('engine toggle narrows the list to that engine', async ({ page }) => {
  await gotoSessions(page);
  const codebuddyFilter = page.getByTestId('activity-filters').getByRole('button', { name: 'codebuddy' });
  await codebuddyFilter.click();
  await expect(page.locator('main')).toContainText('1 session');
  // Toggle it off again — selection is additive, so this returns to all.
  await codebuddyFilter.click();
  await expect(page.locator('main')).toContainText('2 sessions');
});

test('an old Timeline link still opens the session it pointed at', async ({ page }) => {
  // Timeline was removed, but its deep links are in people's history and in
  // the Agent sidebar's older sessions; they carry the same params Sessions
  // reads, so the redirect has to preserve the query string.
  await page.goto(
    '/activity/timeline?session=claude-session-1&sessionEngine=claude&sessionProject=%2Ftmp%2Fe2e-claude-project',
  );
  await waitForH2(page, 'Sessions');
  await expect(page).toHaveURL(/\/activity\/sessions\?/);
  await expect(page).toHaveURL(/session=claude-session-1/);
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
  // instead of being split across a separate event-feed tab.
  await expect(panel).toContainText('Usage');
  await expect(panel).toContainText('Conversation');
  await expect(panel.getByRole('button', { name: /Delete this session/ })).toBeVisible();

  await panel.getByLabel('Close session details').click();
  await expect(page.getByTestId('session-detail')).toHaveCount(0);
});
