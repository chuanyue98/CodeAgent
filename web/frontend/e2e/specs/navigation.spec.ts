import { test, expect, type Page } from '@playwright/test';
import { resetBackend } from '../lib/reset';
import { waitForH2, switchGroup } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

test('ProjectSwitcher hover reveals the menu and changes the active group', async ({
  page,
}) => {
  await page.goto('/skills');
  await switchGroup(page, 'common');
  await expect(page.locator('header button', { hasText: 'common' }).first()).toContainText('common');
});

test('sidebar nav links navigate and mark the active route', async ({ page }) => {
  await page.goto('/skills');
  await page.getByRole('link', { name: 'Chat' }).click();
  await waitForH2(page, 'Chat');
  await expect(page.getByRole('link', { name: 'Chat' })).toHaveClass(/bg-primary\/10/);
});

test('sidebar collapses to icons and expands back', async ({ page }) => {
  await page.goto('/skills');
  const aside = page.locator('aside');
  const collapseBtn = aside.locator('button').first();
  await collapseBtn.click();
  await expect(aside).toHaveClass(/w-24/);
  await collapseBtn.click();
  await expect(aside).toHaveClass(/w-64/);
});
