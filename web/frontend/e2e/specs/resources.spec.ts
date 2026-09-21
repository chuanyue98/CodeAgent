import { test, expect } from '../lib/test-base';
import { resetBackend } from '../lib/reset';
import { gotoResource, resourceCard, resourceKind } from '../lib/ui';

/**
 * 资源页的渲染与交互逻辑（分类过滤、跨类搜索、详情视图、启停开关）已由
 * vitest 组件测试覆盖（ResourceHub.test.tsx、useResourceToggle.test.tsx），
 * 那里用 mock API，跑得快且不脆。只有「夹具经真实后端 API 真的到达页面」
 * 必须在浏览器里验证——留这一条冒烟即可。
 */

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

test('the sidebar lists every kind with its item count', async ({ page }) => {
  await page.goto('/settings/resources');

  // 3 skills, 2 hooks, 2 plugins, 2 prompt groups in the fixtures.
  await expect(resourceKind(page, 'Skills')).toContainText('3');
  await expect(resourceKind(page, 'Hooks')).toContainText('2');
  await expect(resourceKind(page, 'Plugins')).toContainText('2');
  await expect(resourceKind(page, 'Prompts')).toContainText('2');
});

/**
 * 只有真实浏览器能证明主题 CSS 真的生效：vitest 里 CSS 是被 stub 掉的，
 * 组件测试能看到 `hljs-*` 类名，却看不到颜色。这里断的是 highlight.js
 * github-dark 主题给关键字的 `#ff7b72`；主题若没加载，该 span 只会继承代码块
 * 的 slate-100，这条就会红。
 */
test('a code fence in a resource doc is syntax highlighted', async ({ page }) => {
  await gotoResource(page, 'Skills', 'web');
  await resourceCard(page, 'e2e-fetch-skill').click();

  const keyword = page.locator('.hljs-keyword').first();
  await expect(keyword).toHaveText('const');
  await expect(keyword).toHaveCSS('color', 'rgb(255, 123, 114)');
});
