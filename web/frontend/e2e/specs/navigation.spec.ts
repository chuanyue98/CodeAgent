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
  // Agent opens on the terminal: it carries every feature the engine CLI has.
  await waitForH2(page, 'Local Terminal');
  await expect(page).toHaveURL(/\/agent\/terminal$/);
  await expect(agentLink).toHaveClass(/bg-primary\/10/);
});

test('/agent lands on the terminal', async ({ page }) => {
  await page.goto('/agent');
  await waitForH2(page, 'Local Terminal');
  await expect(page).toHaveURL(/\/agent\/terminal$/);
});

test('legacy routes redirect into the new hierarchy', async ({ page }) => {
  // Skills/Prompts/Hooks/Plugins are one Resources page now; the old
  // addresses carry ?kind= so a bookmark opens the kind it named.
  await page.goto('/skills');
  await waitForH2(page, 'Resources');
  await expect(page).toHaveURL(/\/settings\/resources\?kind=skills$/);
  await expect(page.getByRole('navigation', { name: 'Settings sections' })).toBeVisible();
  // Capabilities was flattened from a nested tab row into the Settings row.
  await expect(page.getByRole('navigation', { name: 'Capabilities sections' })).toHaveCount(0);

  await page.goto('/settings/capabilities/plugins');
  await waitForH2(page, 'Resources');
  await expect(page).toHaveURL(/\/settings\/resources\?kind=plugins$/);
});

test('links to the retired Web Agent land on the terminal', async ({ page }) => {
  // /chat and /agent/web were two generations of chat surface. Both redirect
  // rather than 404 -- these paths are in people's bookmarks and history.
  for (const legacy of ['/chat', '/agent/web', '/agent/legacy']) {
    await page.goto(legacy);
    await waitForH2(page, 'Local Terminal');
    await expect(page).toHaveURL(/\/agent\/terminal$/);
  }

  const sections = page.getByRole('navigation', { name: 'Agent sections' });
  await expect(sections.getByRole('link', { name: 'Local Terminal' })).toHaveAttribute('aria-current', 'page');
  await expect(sections.getByRole('link', { name: 'Web Agent' })).toHaveCount(0);
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
