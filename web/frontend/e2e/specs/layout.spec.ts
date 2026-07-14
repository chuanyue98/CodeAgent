import { expect, test } from '@playwright/test';
import { resetBackend } from '../lib/reset';
import { waitForH2 } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

test('laptop layout keeps session controls inside their panels and metrics out of the content', async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto('/sessions');
  await waitForH2(page, 'History');

  const filters = page.getByTestId('session-filters');
  const list = page.getByTestId('session-list');
  await expect(filters).toBeVisible();
  await expect(list).toBeVisible();
  expect(await filters.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
  expect(await list.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);

  const statusButton = page.getByTestId('system-status-button');
  await expect(statusButton).toBeVisible();
  await statusButton.click();
  const metricsPanel = page.getByTestId('system-metrics');
  await expect(metricsPanel).toBeVisible();
  const metricsBox = await metricsPanel.boundingBox();
  expect(metricsBox).not.toBeNull();
  expect(metricsBox!.x + metricsBox!.width).toBeLessThanOrEqual(1366 + 1);
  await statusButton.click();
});

test('compact layout stacks session filters above results', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 768 });
  await page.goto('/sessions');
  await waitForH2(page, 'History');

  const navBox = await page.locator('aside').first().boundingBox();
  const filtersBox = await page.getByTestId('session-filters').boundingBox();
  const listBox = await page.getByTestId('session-list').boundingBox();
  expect(navBox).not.toBeNull();
  expect(filtersBox).not.toBeNull();
  expect(listBox).not.toBeNull();
  expect(navBox!.width).toBeLessThanOrEqual(96);
  expect(listBox!.y).toBeGreaterThan(filtersBox!.y + filtersBox!.height);
});

test('nested workspace routes avoid page-level overflow at supported widths', async ({ page }) => {
  const routes = [
    { path: '/agent/web', label: 'Web Agent' },
    { path: '/automations/tasks', label: 'Tasks' },
    { path: '/activity/history', label: 'History' },
    { path: '/settings/capabilities/plugins', label: 'Plugins' },
    { path: '/settings/system', label: 'System' },
  ];

  for (const width of [1366, 1024, 768]) {
    await page.setViewportSize({ width, height: 768 });
    for (const route of routes) {
      await page.goto(route.path);
      await waitForH2(page, route.label);
      const hasPageOverflow = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
      );
      expect(hasPageOverflow, `${route.path} overflowed at ${width}px`).toBe(false);
    }
  }
});
