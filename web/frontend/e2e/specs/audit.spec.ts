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

async function gotoAudit(page: Page): Promise<void> {
  await page.goto('/audit');
  await waitForH2(page, 'Events');
  await expect(page.getByText('Filters', { exact: true })).toBeVisible();
}

test('renders the filter panel and an empty event state', async ({ page }) => {
  await gotoAudit(page);
  await expect(page.getByRole('button', { name: 'Message' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Tool Call' })).toBeVisible();
  await expect(page.locator('main')).toContainText('No events match your filters');
});

test('toggling an event-type filter does not error', async ({ page }) => {
  await gotoAudit(page);
  await page.getByRole('button', { name: 'Message' }).click();
  await expect(page.locator('main')).toContainText('No events match your filters');
});

test('search and refresh work without error', async ({ page }) => {
  await gotoAudit(page);
  await typeSearch(page, 'anything');
  await page.getByRole('button', { name: 'Refresh' }).click();
  await expect(page.locator('main')).toContainText('No events match your filters');
});
