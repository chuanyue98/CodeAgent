import { test, expect, type Page } from '@playwright/test';
import { resetBackend } from '../lib/reset';
import { waitForH2 } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoChat(page: Page): Promise<void> {
  await page.goto('/chat');
  await waitForH2(page, 'Chat');
  await expect(page.getByPlaceholder('Message the engine...')).toBeVisible();
}

const input = (page: Page) => page.getByPlaceholder('Message the engine...');

test('selecting an engine that supports resume lists prior sessions', async ({
  page,
}) => {
  await gotoChat(page);
  await page.getByRole('button', { name: 'Claude Code' }).click();
  // No sessions exist in the isolated backend -> empty state shown.
  await expect(page.locator('main')).toContainText('No prior sessions');
});

test('sending a message streams an assistant reply', async ({ page }) => {
  await gotoChat(page);
  await page.getByRole('button', { name: 'Claude Code' }).click();
  await input(page).fill('hello e2e');
  await input(page).press('Enter');
  await expect(page.locator('main')).toContainText('You said: hello e2e', {
    timeout: 20000,
  });
});

test('New session clears the conversation', async ({ page }) => {
  await gotoChat(page);
  await page.getByRole('button', { name: 'Claude Code' }).click();
  await input(page).fill('hello e2e');
  await input(page).press('Enter');
  await expect(page.locator('main')).toContainText('You said: hello e2e', {
    timeout: 20000,
  });
  await page.getByRole('button', { name: 'New session' }).click();
  await expect(page.getByText(/Start a conversation/i)).toBeVisible();
});

test('Shift+Enter inserts a newline without sending; Enter sends', async ({
  page,
}) => {
  await gotoChat(page);
  await page.getByRole('button', { name: 'Claude Code' }).click();
  await input(page).click();
  await input(page).pressSequentially('line one');
  await input(page).press('Shift+Enter');
  await input(page).pressSequentially('line two');
  await expect(input(page)).toHaveValue(/line one.*line two/s);
  // Still not sent.
  await expect(page.locator('main')).not.toContainText(/You said/i);
  await input(page).press('Enter');
  await expect(page.locator('main')).toContainText(/You said/i, { timeout: 20000 });
});

test('switching engine resets the conversation', async ({ page }) => {
  await gotoChat(page);
  await page.getByRole('button', { name: 'Claude Code' }).click();
  await input(page).fill('hello e2e');
  await input(page).press('Enter');
  await expect(page.locator('main')).toContainText('You said: hello e2e', {
    timeout: 20000,
  });
  await page.getByRole('button', { name: 'OpenAI Codex' }).click();
  await expect(page.getByText(/Start a conversation/i)).toBeVisible();
});
