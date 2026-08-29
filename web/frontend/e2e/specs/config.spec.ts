import { test, expect, type Page } from '../lib/test-base';
import { resetBackend } from '../lib/reset';
import { waitForPage } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoConfig(page: Page): Promise<void> {
  await page.goto('/config');
  await waitForPage(page, 'Workspace');
  await expect(page.getByRole('button', { name: 'Save All Changes' })).toBeVisible();
}

const save = (page: Page) =>
  page.getByRole('button', { name: 'Save All Changes' }).click();

test('describes the local runtime model', async ({ page }) => {
  await gotoConfig(page);
  await expect(page.getByText(/CodeAgent runs locally/)).toBeVisible();
});

test('adding a project then saving persists the row', async ({ page }) => {
  await gotoConfig(page);
  await page.getByRole('button', { name: 'Add Workspace' }).click();
  const registry = page.locator('section', { hasText: 'Workspaces' });
  await registry.locator('input[placeholder="/absolute/path/to/your/project"]').last().fill('/tmp/e2e-project');
  await save(page);
  await page.reload();
  await waitForPage(page, 'Workspace');
  // The project path lives in an <input> value (not text content), so assert
  // the persisted value rather than visible text.
  await expect(
    page.locator('input[placeholder="/absolute/path/to/your/project"]').last(),
  ).toHaveValue('/tmp/e2e-project');
});

test('empty project rows cannot be saved', async ({ page }) => {
  await gotoConfig(page);
  await page.getByRole('button', { name: 'Add Workspace' }).click();
  await save(page);
  await expect(page.getByText(/Workspace path and resource group are required/)).toBeVisible();
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
