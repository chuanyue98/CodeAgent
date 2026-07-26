import { test, expect, type Page } from '@playwright/test';
import { resetBackend } from '../lib/reset';
import { waitForH2 } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoMcp(page: Page): Promise<void> {
  await page.goto('/mcp');
  await waitForH2(page, 'MCP');
  await expect(page.getByText('No MCP servers configured.')).toBeVisible();
}

test('shows an empty server list by default', async ({ page }) => {
  await gotoMcp(page);
});

test('adding a server makes it appear, and removing clears it', async ({ page }) => {
  await gotoMcp(page);
  // Select an engine first so the add has a target (the engine list also
  // auto-selects, but doing it explicitly avoids a race with that effect).
  await page.getByRole('button', { name: 'Claude Code' }).click();
  await page.getByPlaceholder('my-server').fill('e2e-local');
  await page.getByPlaceholder('npx my-mcp-server --flag').fill('npx -y e2e-mcp');
  await page.getByRole('button', { name: 'Add Server' }).click();
  await expect(page.getByText('e2e-local')).toBeAttached();
  page.once('dialog', dialog => dialog.accept());
  await page.getByTitle('Remove').click();
  await expect(page.getByText('No MCP servers configured.')).toBeVisible();
});

test('switching the engine tab highlights the selection', async ({ page }) => {
  await gotoMcp(page);
  const claudeBtn = page.getByRole('button', { name: 'Claude Code' });
  await claudeBtn.click();
  await expect(claudeBtn).toHaveClass(/bg-slate-100/);
});
