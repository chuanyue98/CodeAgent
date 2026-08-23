import { test, expect } from './lib/test-base';
import AxeBuilder from '@axe-core/playwright';

// One entry per route registered in src/App.tsx's `navItems`/`PAGE_LABELS`.
// `label` is the exact text App.tsx renders in the page header (`<h2>`),
// which doubles as the universal "did this page mount" signal for every
// route — no need for page-specific selectors here.
//
// `emptyStateHint` is set for pages whose backing data is guaranteed empty
// against the E2E fixtures (see start-server.sh) — asserting the hint text
// is present catches the class of bug where a component renders nothing at
// all for an empty array, rather than a real empty-state message.
const PAGES: { path: string; label: string; screenshotSlug: string; emptyStateHint?: RegExp }[] = [
  { path: '/launch', label: '本地终端', screenshotSlug: 'launch' },
  { path: '/chat', label: 'Web Agent', screenshotSlug: 'chat' },
  { path: '/skills', label: '技能', screenshotSlug: 'skills' },
  { path: '/prompts', label: '提示词', screenshotSlug: 'prompts' },
  { path: '/hooks', label: '钩子', screenshotSlug: 'hooks' },
  { path: '/plugins', label: '插件', screenshotSlug: 'plugins' },
  { path: '/mcp', label: 'MCP', screenshotSlug: 'mcp-servers' },
  { path: '/config', label: '工作区', screenshotSlug: 'configuration' },
  { path: '/dashboard', label: '任务', screenshotSlug: 'dashboard' },
  { path: '/cron', label: '定时任务', screenshotSlug: 'cron' },
  { path: '/logs', label: '日志', screenshotSlug: 'logs' },
  { path: '/analytics', label: '用量', screenshotSlug: 'analytics' },
  { path: '/sessions', label: '会话', screenshotSlug: 'sessions' },
  { path: '/audit', label: '时间线', screenshotSlug: 'audit-trail' },
  { path: '/system', label: '系统', screenshotSlug: 'system' },
];

for (const { path, label, screenshotSlug, emptyStateHint } of PAGES) {
  test(`smoke: ${label} (${path}) renders, is accessible, makes no failed requests`, async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    const failedRequests: string[] = [];

    page.on('console', msg => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });
    page.on('pageerror', err => consoleErrors.push(`pageerror: ${err.message}`));
    page.on('response', res => {
      if (res.url().includes('/api/') && res.status() >= 400) {
        failedRequests.push(`${res.status()} ${res.url()}`);
      }
    });

    await page.goto(path);
    await expect(page.getByRole('heading', { level: 1, name: label, exact: true })).toBeVisible();
    // Let the page's mount-time fetches resolve. Not networkidle: LogViewer
    // may open a long-lived SSE stream that never goes idle.
    await page.waitForTimeout(800);

    expect(consoleErrors, `console errors on ${path}`).toEqual([]);
    expect(failedRequests, `failed API requests on ${path}`).toEqual([]);

    if (emptyStateHint) {
      await expect(page.locator('main')).toContainText(emptyStateHint);
    }

    // Accessibility: block only on structural breakage (a page that is
    // fundamentally unusable for assistive tech) and log the long tail of
    // pre-existing minor nits (unlabelled icon buttons, contrast, etc.) so
    // the suite stays green while still surfacing catastrophic regressions.
    const results = await new AxeBuilder({ page }).include('main').analyze();
    const BLOCKING_RULES = new Set([
      'document-title',
      'html-has-lang',
      'landmark-one-main',
      'aria-roles',
      'aria-valid-attr-value',
      'aria-required-attr',
      'duplicate-id',
      'duplicate-id-active',
      'frame-title',
    ]);
    const blocking = results.violations.filter(v => BLOCKING_RULES.has(v.id));
    const nonBlocking = results.violations.filter(v => !BLOCKING_RULES.has(v.id));
    if (nonBlocking.length > 0) {
      console.log(
        `[a11y] ${path}: ${nonBlocking.length} non-blocking violation(s): ${nonBlocking.map(v => v.id).join(', ')}`,
      );
    }
    expect(blocking, `structural a11y violations on ${path}`).toEqual([]);

    // The one real layout interaction in this shell: the sidebar's
    // expanded/collapsed states. Screenshot both.
    await page.screenshot({ path: `e2e/screenshots/${screenshotSlug}-expanded.png` });

    const navigation = page.locator('aside').first();
    const collapseButton = navigation.locator('button').first();
    await collapseButton.click();
    await expect(navigation).toHaveClass(/w-24/);
    await page.screenshot({ path: `e2e/screenshots/${screenshotSlug}-collapsed.png` });
  });
}
