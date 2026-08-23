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
  await waitForH2(page, '会话');
  await expect(page.getByText(/个会话$/)).toBeVisible();
}

test('renders the seeded sessions and filter panel', async ({ page }) => {
  await gotoSessions(page);
  await expect(page.locator('main')).toContainText('2 个会话');
  await expect(page.getByText('筛选', { exact: true })).toBeVisible();
});

test('search filters the session list', async ({ page }) => {
  await gotoSessions(page);
  await page.getByPlaceholder('项目或会话…').fill('e2e-gemini-project');
  await expect(page.locator('main')).toContainText('1 个会话');
  await expect(page.locator('main')).toContainText('e2e-gemini-project');
});

test('engine toggle narrows the list to that engine', async ({ page }) => {
  await gotoSessions(page);
  const geminiFilter = page.getByTestId('activity-filters').getByRole('button', { name: 'gemini' });
  await geminiFilter.click();
  await expect(page.locator('main')).toContainText('1 个会话');
  // Toggle it off again — selection is additive, so this returns to all.
  await geminiFilter.click();
  await expect(page.locator('main')).toContainText('2 个会话');
});

test('filters survive switching to the Timeline tab', async ({ page }) => {
  await gotoSessions(page);
  await page.getByPlaceholder('项目或会话…').fill('e2e-gemini-project');
  await expect(page.locator('main')).toContainText('1 个会话');

  await page
    .getByRole('navigation', { name: '动态分区' })
    .getByRole('link', { name: '时间线' })
    .click();

  await waitForH2(page, '时间线');
  await expect(page.getByPlaceholder('项目、会话、内容…')).toHaveValue(
    'e2e-gemini-project',
  );
});

test('sort buttons toggle their direction', async ({ page }) => {
  await gotoSessions(page);
  const costBtn = page.getByRole('button', { name: '成本' });
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
  await expect(panel).toContainText('用量');
  await expect(panel).toContainText('对话记录');
  await expect(panel.getByRole('button', { name: /删除此会话/ })).toBeVisible();

  await panel.getByLabel('关闭会话详情').click();
  await expect(page.getByTestId('session-detail')).toHaveCount(0);
});
