import { test, expect, type Page } from '@playwright/test';
import { resetBackend } from '../lib/reset';
import { waitForH2 } from '../lib/ui';
import { cardByText, toggleInCard } from '../lib/ui';
import { SKILLS } from '../lib/fixtures';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoChat(page: Page): Promise<void> {
  await page.goto('/chat');
  await waitForH2(page, 'Web Agent');
  await page.getByRole('button', { name: /Open legacy chat/i }).click();
  await expect(page.getByPlaceholder('Message the engine...')).toBeVisible();
  await expect(page.getByLabel('Workspace')).not.toHaveValue('');
}

const input = (page: Page) => page.getByPlaceholder('Message the engine...');
const selectProvider = (page: Page, provider: string) => page.getByLabel('Provider').selectOption(provider);

test('selecting an engine that supports resume lists prior sessions', async ({
  page,
}) => {
  await gotoChat(page);
  await selectProvider(page, 'claude');
  // No sessions exist in the isolated backend -> empty state shown.
  await expect(page.locator('main')).toContainText('No prior sessions');
});

test('sending a message streams an assistant reply', async ({ page }) => {
  await gotoChat(page);
  await selectProvider(page, 'claude');
  await input(page).fill('hello e2e');
  await input(page).press('Enter');
  await expect(page.locator('main')).toContainText('You said: hello e2e', {
    timeout: 20000,
  });
});

test('New session clears the conversation', async ({ page }) => {
  await gotoChat(page);
  await selectProvider(page, 'claude');
  await input(page).fill('hello e2e');
  await input(page).press('Enter');
  await expect(page.locator('main')).toContainText('You said: hello e2e', {
    timeout: 20000,
  });
  await page.getByRole('button', { name: 'New', exact: true }).click();
  await expect(page.getByText(/Start a conversation/i)).toBeVisible();
});

test('running turn locks context controls and can be cancelled', async ({ page }) => {
  await gotoChat(page);
  await selectProvider(page, 'claude');
  await input(page).fill('slow cancellable turn');
  await input(page).press('Enter');

  await expect(page.getByLabel('Workspace')).toBeDisabled();
  await expect(page.getByLabel('Provider')).toBeDisabled();
  await expect(page.getByRole('button', { name: 'New', exact: true })).toBeDisabled();

  await page.getByRole('button', { name: 'Cancel turn' }).click();
  await expect(page.locator('main')).toContainText('Turn stopped', { timeout: 10000 });
  await expect(page.getByLabel('Provider')).toBeEnabled();
});

test('unregistered session remains readable but cannot execute', async ({ page }) => {
  await page.route(/\/api\/history\?engine=claude/, async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        sessions: [{
          session_id: 'legacy-session',
          engine: 'claude',
          project_path: '/tmp/unregistered-project',
          started_at: '2026-07-14T00:00:00Z',
          ended_at: '2026-07-14T00:01:00Z',
          message_count: 2,
          title: 'Legacy session',
          model: 'claude-test',
        }],
      }),
    });
  });
  await page.route(/\/api\/history\/claude\/legacy-session\?/, async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        messages: [
          { role: 'user', content: 'previous question' },
          { role: 'assistant', content: 'previous answer' },
        ],
      }),
    });
  });

  await gotoChat(page);
  await selectProvider(page, 'claude');
  await page.getByRole('button', { name: /Legacy session/ }).click();

  await expect(page.getByText('Viewing an existing session in read-only mode')).toBeVisible();
  await expect(page.getByRole('paragraph').filter({ hasText: '/tmp/unregistered-project' }).first()).toBeVisible();
  await expect(page.getByText('previous answer')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Send message' })).toBeDisabled();
});

test('Shift+Enter inserts a newline without sending; Enter sends', async ({
  page,
}) => {
  await gotoChat(page);
  await selectProvider(page, 'claude');
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
  await selectProvider(page, 'claude');
  await input(page).fill('hello e2e');
  await input(page).press('Enter');
  await expect(page.locator('main')).toContainText('You said: hello e2e', {
    timeout: 20000,
  });
  await selectProvider(page, 'codex');
  await expect(page.getByText(/Start a conversation/i)).toBeVisible();
});

test('shows configured resources as inactive instead of claiming they are enabled', async ({ page }) => {
  await page.goto('/skills');
  const skillCard = cardByText(page, SKILLS.web[0]);
  await toggleInCard(skillCard);

  await gotoChat(page);
  const capabilities = page.getByRole('region', { name: 'Current session capabilities' });
  await expect(capabilities).toContainText('0 CodeAgent-managed resources active');
  await capabilities.getByRole('button', { name: /Legacy Web Chat/i }).click();
  await expect(capabilities).toContainText('Configured but inactive: 1');
  await expect(capabilities).toContainText(SKILLS.web[0]);
  await expect(capabilities).toContainText('Provider-native capabilities: unknown');
});

test('renders markdown and provides copy-to-clipboard for code blocks', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await gotoChat(page);
  await selectProvider(page, 'claude');

  // Send a message containing markdown formatting and a code block
  await input(page).fill('markdown code test:\n```js\nconst val = 42;\n```');
  await input(page).press('Enter');

  // Verify markdown rendering: the code tag should be parsed
  const preElement = page.locator('main pre');
  await expect(preElement).toBeVisible({ timeout: 20000 });
  await expect(preElement).toContainText('const val = 42;');

  // Verify copy button appears on hover/focus
  const copyButton = preElement.locator('..').getByRole('button', { name: 'Copy code' });
  // Trigger hover to make it visible
  await preElement.hover();
  await expect(copyButton).toBeVisible();

  // Test copy action
  await copyButton.click();

  // Verify the check icon appears (which indicates copy succeeded and state updated)
  await expect(copyButton.locator('svg')).toHaveClass(/text-green-400/);

  // Read clipboard to confirm contents are correct
  const clipboardText = await page.evaluate(() => navigator.clipboard.readText());
  expect(clipboardText.trim()).toBe('const val = 42;');
});
