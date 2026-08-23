import { test, expect } from '../lib/test-base';
import { resetBackend } from '../lib/reset';
import { waitForH2 } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

/** Opens the header language menu and picks one of its two options. */
async function chooseLanguage(page: import('@playwright/test').Page, name: string): Promise<void> {
  await page.getByTestId('language-switcher').click();
  await page.getByRole('option', { name }).click();
}

test('the UI starts in the browser language when config expresses no preference', async ({ page }) => {
  // The seeded config.json has no `language`, and Playwright's browser asks
  // for en-US, so the English dictionary is what should paint.
  await page.goto('/home');
  await waitForH2(page, 'Home');
  await expect(page.getByRole('navigation', { name: 'Primary navigation' })).toBeVisible();
});

test('switching language repaints the whole shell, not just the switcher', async ({ page }) => {
  await page.goto('/home');
  await waitForH2(page, 'Home');

  await chooseLanguage(page, '中文');

  // Heading, sidebar nav and section descriptions all come from the same
  // dictionary — if any of them were still hardcoded this fails.
  await waitForH2(page, '首页');
  const nav = page.getByRole('navigation', { name: '主导航' });
  await expect(nav.getByRole('link', { name: '自动化', exact: true })).toBeVisible();
  await expect(nav.getByRole('link', { name: '设置', exact: true })).toBeVisible();
});

test('the choice is written to config.json, so the CLI and a reload agree', async ({ page, baseURL }) => {
  await page.goto('/home');
  await waitForH2(page, 'Home');
  await chooseLanguage(page, '中文');
  await waitForH2(page, '首页');

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
  await waitForH2(page, '首页');
});

test('a language switch survives navigation across sections', async ({ page }) => {
  await page.goto('/home');
  await waitForH2(page, 'Home');
  await chooseLanguage(page, '中文');
  await waitForH2(page, '首页');

  await page.getByRole('navigation', { name: '主导航' })
    .getByRole('link', { name: '动态', exact: true })
    .click();
  await waitForH2(page, '会话');
  await expect(page.getByRole('navigation', { name: '动态分区' })).toBeVisible();

  // And back again, to prove the switch is not one-way.
  await chooseLanguage(page, 'English');
  await waitForH2(page, 'Sessions');
  await expect(page.getByRole('navigation', { name: 'Activity sections' })).toBeVisible();
});
