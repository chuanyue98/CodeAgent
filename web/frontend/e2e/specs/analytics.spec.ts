import { test, expect } from '../lib/test-base';
import { resetBackend } from '../lib/reset';
import { waitForPage } from '../lib/ui';

/**
 * 用量页的全部展示与统计逻辑（时间范围、模型明细展开、工具排行、空态）
 * 由 vitest 组件测试覆盖（Analytics.test.tsx）。这里只留一条路由级冒烟：
 * 真实后端的数据能到达页面、图表能渲染。
 */

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

test('every section renders on one page instead of behind sub-tabs', async ({ page }) => {
  await page.goto('/analytics');
  await waitForPage(page, 'Usage');
  const main = page.locator('main');
  await expect(main).toContainText('Total Cost');
  await expect(main).toContainText('Cost by engine');
  await expect(main).toContainText('Tokens by engine');
  await expect(main).toContainText('Model Breakdown');
  await expect(page.locator('svg.recharts-surface').first()).toBeVisible();
});
