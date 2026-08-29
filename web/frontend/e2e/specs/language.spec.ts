import { test, expect } from '../lib/test-base';
import { resetBackend } from '../lib/reset';
import { waitForPage } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

/**
 * Picks a language on Settings > Workspace, where the setting lives — it is a
 * config.json field, and a one-time preference does not earn permanent space
 * in the app header. Navigates there and leaves the browser on that page.
 */
async function chooseLanguage(page: import('@playwright/test').Page, name: string): Promise<void> {
  await page.goto('/settings/workspace');
  await page.getByTestId('language-switcher').getByRole('radio', { name }).click();
}

test('the UI starts in the browser language when config expresses no preference', async ({ page }) => {
  // The seeded config.json has no `language`, and Playwright's browser asks
  // for en-US, so the English dictionary is what should paint.
  await page.goto('/home');
  await waitForPage(page, 'Home');
  await expect(page.getByRole('navigation', { name: 'Primary navigation' })).toBeVisible();
});

test('switching language repaints the whole shell, not just the control', async ({ page }) => {
  await page.goto('/home');
  await waitForPage(page, 'Home');

  await chooseLanguage(page, '中文');

  // Heading, sidebar nav and section descriptions all come from the same
  // dictionary — if any of them were still hardcoded this fails.
  await waitForPage(page, '工作区');
  const nav = page.getByRole('navigation', { name: '主导航' });
  await expect(nav.getByRole('link', { name: '自动化', exact: true })).toBeVisible();
  await expect(nav.getByRole('link', { name: '设置', exact: true })).toBeVisible();
});

test('the choice is written to config.json, so the CLI and a reload agree', async ({ page, baseURL }) => {
  await page.goto('/home');
  await waitForPage(page, 'Home');
  await chooseLanguage(page, '中文');
  await waitForPage(page, '工作区');

  // config.json is the shared setting core/i18n.py reads; browser storage
  // alone would leave the CLI in another language.
  await expect.poll(async () => {
    const response = await fetch(`${baseURL}/api/config`, {
      headers: { 'X-CA-Token': 'codeagent-e2e-token' },
    });
    const config = await response.json() as { language?: string };
    return config.language;
  }).toBe('zh');

  await page.reload();
  await waitForPage(page, '工作区');
});

test('a language switch survives navigation across sections', async ({ page }) => {
  await page.goto('/home');
  await waitForPage(page, 'Home');
  await chooseLanguage(page, '中文');
  await waitForPage(page, '工作区');

  await page.getByRole('navigation', { name: '主导航' })
    .getByRole('link', { name: '动态', exact: true })
    .click();
  await waitForPage(page, '会话');
  await expect(page.getByRole('navigation', { name: '动态分区' })).toBeVisible();

  // And back again, to prove the switch is not one-way. Picking a language
  // lands you on Settings, so that is the section that has to have repainted.
  await chooseLanguage(page, 'English');
  await waitForPage(page, 'Workspace');
  await expect(page.getByRole('navigation', { name: 'Settings sections' })).toBeVisible();
});
