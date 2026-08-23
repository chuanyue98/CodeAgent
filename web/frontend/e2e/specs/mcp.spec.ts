import { test, expect, type Page } from '../lib/test-base';
import { resetBackend } from '../lib/reset';
import { waitForH2 } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoMcp(page: Page): Promise<void> {
  await page.goto('/mcp');
  await waitForH2(page, 'MCP');
  await expect(page.getByText('该引擎尚未配置 MCP 服务器。')).toBeVisible();
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
  await page.getByRole('button', { name: '添加服务器' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await dialog.getByPlaceholder('my-server').fill('e2e-local');
  await dialog.getByPlaceholder('npx my-mcp-server --flag').fill('npx -y e2e-mcp');
  await dialog.getByRole('button', { name: '添加服务器' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByText('e2e-local')).toBeAttached();

  await page.getByRole('button', { name: '移除 e2e-local' }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: '移除' }).click();
  await expect(page.getByText('该引擎尚未配置 MCP 服务器。')).toBeVisible();
});

test('switching the engine tab highlights the selection', async ({ page }) => {
  await gotoMcp(page);
  const claudeBtn = page.getByRole('button', { name: 'Claude Code' });
  await claudeBtn.click();
  await expect(claudeBtn).toHaveClass(/bg-primary\/10/);
});
