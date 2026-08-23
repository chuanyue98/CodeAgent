import { test, expect, type Page } from '../lib/test-base';
import { resetBackend } from '../lib/reset';
import { waitForH2, typeSearch } from '../lib/ui';

// NOTE: the Audit Trail reads real per-engine session files from disk
// (see core/session_history), which the isolated E2E backend does not seed.
// These specs therefore cover the filter UI and empty state; row-expand and
// the session drawer require real session history and are validated by the
// Python suite instead.

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoTimeline(page: Page): Promise<void> {
  await page.goto('/audit');
  await waitForH2(page, '时间线');
  await expect(page.getByText('筛选', { exact: true })).toBeVisible();
}

test('renders the filter panel and an empty event state', async ({ page }) => {
  await gotoTimeline(page);
  await expect(page.getByRole('button', { name: '消息' })).toBeVisible();
  await expect(page.getByRole('button', { name: '工具调用' })).toBeVisible();
  await expect(page.locator('main')).toContainText('没有符合筛选条件的事件');
});

test('toggling an event-type filter does not error', async ({ page }) => {
  await gotoTimeline(page);
  await page.getByRole('button', { name: '消息' }).click();
  await expect(page.locator('main')).toContainText('没有符合筛选条件的事件');
});

test('search and refresh work without error', async ({ page }) => {
  await gotoTimeline(page);
  await typeSearch(page, 'anything');
  await page.getByRole('button', { name: '刷新' }).click();
  await expect(page.locator('main')).toContainText('没有符合筛选条件的事件');
});
