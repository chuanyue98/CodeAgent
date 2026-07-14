import { expect, test } from '@playwright/test';
import { resetBackend } from '../lib/reset';
import { waitForH2 } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

test('laptop layout keeps session controls inside their panels and metrics out of the content', async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto('/sessions');
  await waitForH2(page, 'Sessions');

  const filters = page.getByTestId('session-filters');
  const list = page.getByTestId('session-list');
  await expect(filters).toBeVisible();
  await expect(list).toBeVisible();
  expect(await filters.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
  expect(await list.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);

  const metrics = page.getByTestId('system-metrics');
  await expect(metrics).toBeVisible();
  const shellBox = await page.getByTestId('app-shell').boundingBox();
  const metricsBox = await metrics.boundingBox();
  expect(shellBox).not.toBeNull();
  expect(metricsBox).not.toBeNull();
  expect(shellBox!.y + shellBox!.height).toBeLessThanOrEqual(metricsBox!.y + 1);
});

test('compact layout stacks session filters above results', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 768 });
  await page.goto('/sessions');
  await waitForH2(page, 'Sessions');

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
    { path: '/agent/web', label: 'Chat' },
    { path: '/automations/tasks', label: 'Dashboard' },
    { path: '/activity/history', label: 'Sessions' },
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
