import { test, expect, type Page } from '../lib/test-base';
import { resetBackend } from '../lib/reset';
import { waitForH2 } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoChat(page: Page): Promise<void> {
  await page.goto('/chat');
  await waitForH2(page, 'Web Agent');
  await expect(page.getByLabel('Workspace')).not.toHaveValue('');
}

const input = (page: Page) => page.locator('textarea');
const selectProvider = (page: Page, provider: string) => page.getByLabel('Engine').selectOption(provider);

test('selecting an engine shows an empty conversation list when none exist', async ({
  page,
}) => {
  await gotoChat(page);
  await selectProvider(page, 'fake');
  // No sessions exist in the isolated backend -> empty state shown.
  await expect(page.locator('main')).toContainText('No conversations yet');
});

test('sending a message streams an assistant reply', async ({ page }) => {
  await gotoChat(page);
  await selectProvider(page, 'fake');
  await input(page).fill('hello e2e');
  await input(page).press('Enter');
  await expect(page.locator('main')).toContainText('Echo: hello e2e', {
    timeout: 20000,
  });
});

test('New session clears the conversation', async ({ page }) => {
  await gotoChat(page);
  await selectProvider(page, 'fake');
  await input(page).fill('hello e2e');
  await input(page).press('Enter');
  await expect(page.locator('main')).toContainText('Echo: hello e2e', {
    timeout: 20000,
  });
  await page.getByRole('button', { name: 'New', exact: true }).click();
  await expect(page.getByText(/Start a new conversation/i)).toBeVisible();
});

test('an active session locks workspace and provider selection until New is clicked', async ({ page }) => {
  await gotoChat(page);
  await selectProvider(page, 'fake');
  await input(page).fill('hello e2e');
  await input(page).press('Enter');
  await expect(page.locator('main')).toContainText('Echo: hello e2e', {
    timeout: 20000,
  });

  await expect(page.getByLabel('Workspace')).toBeDisabled();
  await expect(page.getByLabel('Engine')).toBeDisabled();

  await page.getByRole('button', { name: 'New', exact: true }).click();
  await expect(page.getByLabel('Workspace')).toBeEnabled();
  await expect(page.getByLabel('Engine')).toBeEnabled();
});

test('sessions from unregistered workspaces are listed but cannot be opened', async ({ page }) => {
  await page.route(/\/api\/history\?engine=fake/, async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        sessions: [{
          session_id: 'legacy-session',
          engine: 'fake',
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

  await gotoChat(page);
  await selectProvider(page, 'fake');

  await page.getByRole('button', { name: /Unavailable workspaces/ }).click();
  const entry = page.getByText('unregistered-project');
  await expect(entry).toBeVisible();
  await expect(page.getByRole('button', { name: 'Register' })).toBeVisible();

  // The entry is inert (not a button) — clicking it must not open a session.
  await entry.click();
  await expect(page.getByText(/Start a new conversation/i)).toBeVisible();
});

test('Shift+Enter inserts a newline without sending; Enter sends', async ({
  page,
}) => {
  await gotoChat(page);
  await selectProvider(page, 'fake');
  await input(page).click();
  await input(page).pressSequentially('line one');
  await input(page).press('Shift+Enter');
  await input(page).pressSequentially('line two');
  await expect(input(page)).toHaveValue(/line one.*line two/s);
  // Still not sent.
  await expect(page.locator('main')).not.toContainText(/Echo:/i);
  await input(page).press('Enter');
  await expect(page.locator('main')).toContainText(/Echo:/i, { timeout: 20000 });
});

test('renders markdown and provides copy-to-clipboard for code blocks', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await gotoChat(page);
  await selectProvider(page, 'fake');

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
