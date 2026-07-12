import { test, expect, type Page } from '@playwright/test';
import { resetBackend } from '../lib/reset';
import { waitForH2, cardByText } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoLaunch(page: Page): Promise<void> {
  await page.goto('/launch');
  await waitForH2(page, 'Launch');
  await expect(cardByText(page, 'Claude')).toBeVisible();
}

test('clicking launch shows the launched state for that engine', async ({
  page,
}) => {
  await gotoLaunch(page);
  const claudeCard = cardByText(page, 'Claude');
  await claudeCard.getByRole('button').click();
  await expect(claudeCard).toContainText('已启动 ✓', { timeout: 15000 });
});

test('each engine card is independently launchable', async ({ page }) => {
  await gotoLaunch(page);
  for (const name of ['Claude', 'Gemini', 'OpenCode', 'Codex']) {
    const card = cardByText(page, name);
    await card.getByRole('button').click();
    await expect(card).toContainText('已启动 ✓', { timeout: 15000 });
  }
});
