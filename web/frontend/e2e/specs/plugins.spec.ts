import { test, expect, type Page } from '../lib/test-base';
import { resetBackend } from '../lib/reset';
import {
  waitForH2,
  typeSearch,
  cardByText,
  toggleInCard,
  openCard,
  backFromDetail,
} from '../lib/ui';
import { PLUGINS } from '../lib/fixtures';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoPlugins(page: Page): Promise<void> {
  await page.goto('/plugins');
  await waitForH2(page, '插件');
  // Categories render in API order; explicitly select "base".
  await page.getByRole('button', { name: /^base/i }).click();
  await expect(cardByText(page, PLUGINS.base)).toBeVisible();
}

test('categories render and switch', async ({ page }) => {
  await gotoPlugins(page);
  const devopsBtn = page.getByRole('button', { name: /^devops/i });
  await expect(devopsBtn).toBeVisible();
  await devopsBtn.click();
  await expect(cardByText(page, PLUGINS.devops)).toBeVisible();
  await expect(cardByText(page, PLUGINS.base)).toHaveCount(0);
});

test('search filters the current category', async ({ page }) => {
  await gotoPlugins(page);
  await typeSearch(page, PLUGINS.base);
  await expect(cardByText(page, PLUGINS.base)).toBeVisible();
});

test('card and detail toggles flip active state', async ({ page }) => {
  await gotoPlugins(page);
  const card = cardByText(page, PLUGINS.base);
  await expect(card).toHaveClass(/bg-slate-50\/60/);
  await toggleInCard(card);
  await expect(card).not.toHaveClass(/bg-slate-50\/60/);

  await openCard(page, PLUGINS.base);
  await expect(page.locator('main')).toContainText('插件详情');
  const detailToggle = page.locator('div', { hasText: '中启用' }).last().locator('button');
  await expect(detailToggle).toHaveClass(/bg-primary/);
  await backFromDetail(page);
  await expect(cardByText(page, PLUGINS.base)).toBeVisible();
});
