import { test, expect, type Page } from '../lib/test-base';
import { resetBackend } from '../lib/reset';
import { waitForH2 } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoMcp(page: Page): Promise<void> {
  await page.goto('/mcp');
  await waitForH2(page, 'MCP');
  await expect(page.getByText('No MCP servers configured for this engine.')).toBeVisible();
}

test('shows an empty server list by default', async ({ page }) => {
  await gotoMcp(page);
});

test('adding a server makes it appear, and removing clears it', async ({ page }) => {
  await gotoMcp(page);
  // Select an engine first so the add has a target (the engine list also
  // auto-selects, but doing it explicitly avoids a race with that effect).
  await page.getByRole('button', { name: 'Claude Code' }).click();

  // Add Server opens the modal form instead of the old permanent side panel.
  await page.getByRole('button', { name: 'Add Server' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await dialog.getByPlaceholder('my-server').fill('e2e-local');
  await dialog.getByPlaceholder('npx my-mcp-server --flag').fill('npx -y e2e-mcp');
  await dialog.getByRole('button', { name: 'Add Server' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByText('e2e-local')).toBeAttached();

  await page.getByRole('button', { name: 'Remove e2e-local' }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'Remove' }).click();
  await expect(page.getByText('No MCP servers configured for this engine.')).toBeVisible();
});

test('switching the engine tab highlights the selection', async ({ page }) => {
  await gotoMcp(page);
  const claudeBtn = page.getByRole('button', { name: 'Claude Code' });
  await claudeBtn.click();
  await expect(claudeBtn).toHaveClass(/bg-primary\/10/);
});
