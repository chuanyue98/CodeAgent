import { test, expect } from '../lib/test-base';
import { resetBackend } from '../lib/reset';
import { waitForPage, switchGroup } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

test('the workspace menu changes the active resource group', async ({ page }) => {
  // The group used to be its own header chip; it is a field inside the
  // workspace menu now, since that is what decides it.
  await page.goto('/skills');
  await switchGroup(page, 'common');

  await page.getByRole('button', { name: /current workspace/i }).click();
  await expect(page.getByTestId('group-switcher')).toHaveValue('common');
});

test('sidebar nav links navigate and mark the active route', async ({ page }) => {
  await page.goto('/skills');
  const primaryNav = page.getByRole('navigation', { name: 'Primary navigation' });
  const agentLink = primaryNav.getByRole('link', { name: 'Sessions', exact: true });
  await agentLink.click();
  // Sessions opens on the terminal: it carries every feature the engine CLI has.
  await waitForPage(page, 'Sessions');
  await expect(page).toHaveURL(/\/agent\/terminal$/);
  await expect(agentLink).toHaveAttribute('aria-current', 'page');
});

test('/agent lands on the terminal', async ({ page }) => {
  await page.goto('/agent');
  await waitForPage(page, 'Sessions');
  await expect(page).toHaveURL(/\/agent\/terminal$/);
});

test('legacy routes redirect into the new hierarchy', async ({ page }) => {
  // Skills/Prompts/Hooks/Plugins are one Resources page now; the old
  // addresses carry ?kind= so a bookmark opens the kind it named.
  await page.goto('/skills');
  await waitForPage(page, 'Resources');
  await expect(page).toHaveURL(/\/extensions\/resources\?kind=skills$/);
  await expect(page.getByRole('navigation', { name: 'Extensions sections' })).toBeVisible();
  // Capabilities was flattened from a nested tab row into the section's own row.
  await expect(page.getByRole('navigation', { name: 'Capabilities sections' })).toHaveCount(0);

  await page.goto('/settings/capabilities/plugins');
  await waitForPage(page, 'Resources');
  await expect(page).toHaveURL(/\/extensions\/resources\?kind=plugins$/);

  // Resources and MCP used to be Settings tabs; their old addresses still land.
  await page.goto('/settings/mcp');
  await waitForPage(page, 'MCP');
  await expect(page).toHaveURL(/\/extensions\/mcp$/);
});

test('links to the retired Web Agent land on the terminal', async ({ page }) => {
  // /chat and /agent/web were two generations of chat surface. Both redirect
  // rather than 404 -- these paths are in people's bookmarks and history.
  for (const legacy of ['/chat', '/agent/web', '/agent/legacy']) {
    await page.goto(legacy);
    await waitForPage(page, 'Sessions');
    await expect(page).toHaveURL(/\/agent\/terminal$/);
  }

  await expect(page.getByRole('link', { name: 'Web Agent' })).toHaveCount(0);
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
  await waitForPage(page, 'MCP');
  await expect(palette).toHaveCount(0);
});

test('command palette closes on Escape without navigating', async ({ page }) => {
  await page.goto('/home');
  await page.getByTestId('command-palette-trigger').click();
  await expect(page.getByTestId('command-palette')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('command-palette')).toHaveCount(0);
  await waitForPage(page, 'Overview');
});
