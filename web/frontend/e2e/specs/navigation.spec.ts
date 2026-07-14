import { test, expect } from '@playwright/test';
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
  const primaryNav = page.getByRole('navigation', { name: 'Primary navigation' });
  const agentLink = primaryNav.getByRole('link', { name: 'Agent', exact: true });
  await agentLink.click();
  await waitForH2(page, 'Chat');
  await expect(agentLink).toHaveClass(/bg-primary\/10/);
});

test('legacy routes redirect into the new hierarchy', async ({ page }) => {
  await page.goto('/skills');
  await waitForH2(page, 'Skills');
  await expect(page).toHaveURL(/\/settings\/capabilities\/skills$/);
  await expect(page.getByRole('navigation', { name: 'Settings sections' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Capabilities sections' })).toBeVisible();
});

test('Agent workspace combines Web Agent and Native Terminal modes', async ({ page }) => {
  await page.goto('/chat');
  await waitForH2(page, 'Chat');
  const sections = page.getByRole('navigation', { name: 'Agent sections' });
  await expect(sections.getByRole('link', { name: 'Web Agent' })).toHaveAttribute('aria-current', 'page');

  await sections.getByRole('link', { name: 'Native Terminal' }).click();
  await waitForH2(page, 'Launch');
  await expect(page).toHaveURL(/\/agent\/terminal$/);
  await expect(page.getByText('选择引擎，点击启动即可在新终端窗口中运行对应的 ca 会话。')).toBeVisible();
});

test('sidebar collapses to icons and expands back', async ({ page }) => {
  await page.goto('/skills');
  const aside = page.locator('aside').first();
  const collapseBtn = aside.locator('button').first();
  await collapseBtn.click();
  await expect(aside).toHaveClass(/w-24/);
  await collapseBtn.click();
  await expect(aside).toHaveClass(/w-64/);
});
