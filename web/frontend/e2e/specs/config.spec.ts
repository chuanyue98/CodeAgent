import { test, expect, type Page } from '@playwright/test';
import { resetBackend } from '../lib/reset';
import { waitForH2 } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoConfig(page: Page): Promise<void> {
  await page.goto('/config');
  await waitForH2(page, 'Configuration');
  await expect(page.getByRole('button', { name: 'Save All Changes' })).toBeVisible();
}

const save = (page: Page) =>
  page.getByRole('button', { name: 'Save All Changes' }).click();

const modeSelect = (page: Page) =>
  page.locator('select').filter({ has: page.locator('option[value="cloud"]') });
const langSelect = (page: Page) =>
  page.locator('select').filter({ has: page.locator('option[value="zh"]') });

test('changing Operation Mode and saving persists across reload', async ({
  page,
}) => {
  await gotoConfig(page);
  await modeSelect(page).selectOption('cloud');
  await save(page);
  await page.reload();
  await waitForH2(page, 'Configuration');
  await expect(modeSelect(page)).toHaveValue('cloud');
});

test('changing Language and saving persists across reload', async ({ page }) => {
  await gotoConfig(page);
  await langSelect(page).selectOption('zh');
  await save(page);
  await page.reload();
  await waitForH2(page, 'Configuration');
  await expect(langSelect(page)).toHaveValue('zh');
});

test('unsaved changes are lost on reload', async ({ page }) => {
  await gotoConfig(page);
  await modeSelect(page).selectOption('hybrid');
  await page.reload();
  await waitForH2(page, 'Configuration');
  await expect(modeSelect(page)).toHaveValue('local');
});

test('adding a project then saving persists the row', async ({ page }) => {
  await gotoConfig(page);
  await page.getByRole('button', { name: 'Add Project' }).click();
  const registry = page.locator('section', { hasText: 'Project Registry' });
  await registry.locator('input[placeholder="E:/your/project/path"]').last().fill('/tmp/e2e-project');
  await save(page);
  await page.reload();
  await waitForH2(page, 'Configuration');
  // The project path lives in an <input> value (not text content), so assert
  // the persisted value rather than visible text.
  await expect(
    page.locator('input[placeholder="E:/your/project/path"]').last(),
  ).toHaveValue('/tmp/e2e-project');
});

test('New Group inline input: Enter confirms, Escape cancels', async ({ page }) => {
  await gotoConfig(page);
  await page.getByRole('button', { name: 'New Group' }).click();
  const input = page.locator('input[placeholder="group-name"]');
  await expect(input).toBeVisible();

  // Escape cancels without creating a group.
  await input.fill('e2e-cancelled');
  await input.press('Escape');
  await expect(input).toHaveCount(0);
  await expect(page.locator('main')).not.toContainText('e2e-cancelled');

  // Enter confirms and creates the group.
  await page.getByRole('button', { name: 'New Group' }).click();
  await page.locator('input[placeholder="group-name"]').fill('e2e-team');
  await page.locator('input[placeholder="group-name"]').press('Enter');
  await expect(page.locator('main')).toContainText('e2e-team');
});

test('Deleting a (non-default) group confirms via dialog', async ({ page }) => {
  await gotoConfig(page);
  // Create a group first, since the baseline group can't be deleted.
  await page.getByRole('button', { name: 'New Group' }).click();
  await page.locator('input[placeholder="group-name"]').fill('e2e-team');
  await page.locator('input[placeholder="group-name"]').press('Enter');
  await expect(page.locator('main')).toContainText('e2e-team');

  const groupsSection = page.locator('section', { hasText: 'Resource Groups' });
  page.once('dialog', (d) => d.accept());
  await groupsSection.locator('button').last().click();
  await expect(page.locator('main')).not.toContainText('e2e-team');
});
