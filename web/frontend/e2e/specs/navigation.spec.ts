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
  const primaryNav = page.getByRole('navigation', { name: '主导航' });
  const agentLink = primaryNav.getByRole('link', { name: 'Agent', exact: true });
  await agentLink.click();
  await waitForH2(page, 'Web Agent');
  await expect(agentLink).toHaveClass(/bg-primary\/10/);
});

test('legacy routes redirect into the new hierarchy', async ({ page }) => {
  await page.goto('/skills');
  await waitForH2(page, '技能');
  await expect(page).toHaveURL(/\/settings\/skills$/);
  await expect(page.getByRole('navigation', { name: '设置分区' })).toBeVisible();
  // Capabilities was flattened from a nested tab row into the Settings row.
  await expect(page.getByRole('navigation', { name: '能力分区' })).toHaveCount(0);

  await page.goto('/settings/capabilities/plugins');
  await waitForH2(page, '插件');
  await expect(page).toHaveURL(/\/settings\/plugins$/);
});

test('Agent workspace combines Web Agent and Local Terminal modes', async ({ page }) => {
  await page.goto('/chat');
  await waitForH2(page, 'Web Agent');
  const sections = page.getByRole('navigation', { name: 'Agent分区' });
  await expect(sections.getByRole('link', { name: 'Web Agent' })).toHaveAttribute('aria-current', 'page');

  await sections.getByRole('link', { name: '本地终端' }).click();
  await waitForH2(page, '本地终端');
  await expect(page).toHaveURL(/\/agent\/terminal$/);
  await expect(page.getByText('在浏览器终端中打开引擎 CLI，运行在托管 CodeAgent 的本机上。')).toBeVisible();
});

test('command palette opens via Ctrl/Cmd+K, filters, and navigates', async ({ page }) => {
  await page.goto('/home');
  await page.keyboard.press('ControlOrMeta+k');
  const palette = page.getByTestId('command-palette');
  await expect(palette).toBeVisible();

  await page.getByLabel('命令面板搜索').fill('mcp');
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
  await waitForH2(page, '首页');
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
