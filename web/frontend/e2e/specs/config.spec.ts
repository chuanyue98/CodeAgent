import { test, expect, type Page } from '../lib/test-base';
import { resetBackend } from '../lib/reset';
import { waitForH2 } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoConfig(page: Page): Promise<void> {
  await page.goto('/config');
  await waitForH2(page, '工作区');
  await expect(page.getByRole('button', { name: '保存全部修改' })).toBeVisible();
}

const save = (page: Page) =>
  page.getByRole('button', { name: '保存全部修改' }).click();

test('describes the local runtime model', async ({ page }) => {
  await gotoConfig(page);
  await expect(page.getByText(/CodeAgent 在本地运行/)).toBeVisible();
});

test('adding a project then saving persists the row', async ({ page }) => {
  await gotoConfig(page);
  await page.getByRole('button', { name: '添加工作区' }).click();
  const registry = page.locator('section', { hasText: '工作区' });
  await registry.locator('input[placeholder="/absolute/path/to/your/project"]').last().fill('/tmp/e2e-project');
  await save(page);
  await page.reload();
  await waitForH2(page, '工作区');
  // The project path lives in an <input> value (not text content), so assert
  // the persisted value rather than visible text.
  await expect(
    page.locator('input[placeholder="/absolute/path/to/your/project"]').last(),
  ).toHaveValue('/tmp/e2e-project');
});

test('empty project rows cannot be saved', async ({ page }) => {
  await gotoConfig(page);
  await page.getByRole('button', { name: '添加工作区' }).click();
  await save(page);
  await expect(page.getByText(/工作区路径和资源组为必填/)).toBeVisible();
});

test('New Group inline input: Enter confirms, Escape cancels', async ({ page }) => {
  await gotoConfig(page);
  await page.getByRole('button', { name: '新建资源组' }).click();
  const input = page.locator('input[placeholder="group-name"]');
  await expect(input).toBeVisible();

  // Escape cancels without creating a group.
  await input.fill('e2e-cancelled');
  await input.press('Escape');
  await expect(input).toHaveCount(0);
  await expect(page.locator('main')).not.toContainText('e2e-cancelled');

  // Enter confirms and creates the group.
  await page.getByRole('button', { name: '新建资源组' }).click();
  await page.locator('input[placeholder="group-name"]').fill('e2e-team');
  await page.locator('input[placeholder="group-name"]').press('Enter');
  await expect(page.locator('main')).toContainText('e2e-team');
});

test('Deleting a (non-default) group confirms via dialog', async ({ page }) => {
  await gotoConfig(page);
  // Create a group first, since the baseline group can't be deleted.
  await page.getByRole('button', { name: '新建资源组' }).click();
  await page.locator('input[placeholder="group-name"]').fill('e2e-team');
  await page.locator('input[placeholder="group-name"]').press('Enter');
  await expect(page.locator('main')).toContainText('e2e-team');

  const groupsSection = page.locator('section', { hasText: '资源组' });
  page.once('dialog', (d) => d.accept());
  await groupsSection.locator('button').last().click();
  await expect(page.locator('main')).not.toContainText('e2e-team');
});
