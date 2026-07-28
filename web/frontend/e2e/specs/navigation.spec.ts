import { test, expect } from '../lib/test-base';
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
  await waitForH2(page, 'Web Agent');
  await expect(agentLink).toHaveClass(/bg-primary\/10/);
});

test('legacy routes redirect into the new hierarchy', async ({ page }) => {
  await page.goto('/skills');
  await waitForH2(page, 'Skills');
  await expect(page).toHaveURL(/\/settings\/capabilities\/skills$/);
  await expect(page.getByRole('navigation', { name: 'Settings sections' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Capabilities sections' })).toBeVisible();
});

test('Agent workspace combines Web Agent and Local Terminal modes', async ({ page }) => {
  await page.goto('/chat');
  await waitForH2(page, 'Web Agent');
  const sections = page.getByRole('navigation', { name: 'Agent sections' });
  await expect(sections.getByRole('link', { name: 'Web Agent' })).toHaveAttribute('aria-current', 'page');

  await sections.getByRole('link', { name: 'Local Terminal' }).click();
  await waitForH2(page, 'Local Terminal');
  await expect(page).toHaveURL(/\/agent\/terminal$/);
  await expect(page.getByText('Opens the provider CLI in an in-browser terminal, running on the machine hosting CodeAgent.')).toBeVisible();
});

test('command palette opens via Ctrl/Cmd+K, filters, and navigates', async ({ page }) => {
  await page.goto('/home');
  await page.keyboard.press('ControlOrMeta+k');
  const palette = page.getByTestId('command-palette');
  await expect(palette).toBeVisible();

  await page.getByLabel('Command palette search').fill('mcp');
  await expect(page.getByRole('option', { name: /^MCP/ })).toBeVisible();
  await expect(page.getByRole('option', { name: /Web Agent/ })).toHaveCount(0);

  await page.getByRole('option', { name: /^MCP/ }).click();
  await waitForH2(page, 'MCP');
  await expect(palette).toHaveCount(0);
});

test('command palette closes on Escape without navigating', async ({ page }) => {
  await page.goto('/home');
  await page.getByTestId('command-palette-trigger').click();
  await expect(page.getByTestId('command-palette')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('command-palette')).toHaveCount(0);
  await waitForH2(page, 'Home');
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
