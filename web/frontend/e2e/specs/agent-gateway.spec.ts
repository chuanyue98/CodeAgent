import { test, expect, type Page } from '../lib/test-base';
import { resetBackend } from '../lib/reset';
import { waitForH2 } from '../lib/ui';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoAgent(page: Page): Promise<void> {
  await page.goto('/agent/web');
  await waitForH2(page, 'Web Agent');
  await expect(page.getByPlaceholder(/发消息/)).toBeVisible();
  await expect(page.getByLabel('工作区', { exact: true })).not.toHaveValue('');
  await expect(page.getByLabel('引擎')).toHaveValue('fake');
}

test('creates a structured session and streams provider-neutral events', async ({ page }) => {
  await gotoAgent(page);
  const composer = page.getByPlaceholder(/发消息/);
  await composer.fill('hello gateway');
  await composer.press('Enter');

  await expect(page.locator('main')).toContainText('Echo: hello gateway');
  await expect(page.locator('main')).toContainText('已连接');
  await expect(page.getByLabel('工作区', { exact: true })).toBeDisabled();
  await expect(page.getByLabel('引擎')).toBeDisabled();
});

test('activity drawer keeps protocol details out of the conversation by default', async ({ page }) => {
  await gotoAgent(page);
  const composer = page.getByPlaceholder(/发消息/);
  await composer.fill('show activity');
  await composer.press('Enter');
  await expect(page.locator('main')).toContainText('Echo: show activity');

  await page.getByRole('button', { name: '查看回合事件' }).click();
  await expect(page.getByRole('main').getByText('回合事件', { exact: true })).toBeVisible();
  await expect(page.getByText(/message\.delta/)).toBeVisible();
  await page.getByRole('button', { name: '关闭回合事件' }).click();
  await expect(page.getByText('工具、diff、用量和协议事件')).not.toBeVisible();
});

test('replays a stored conversation when a session is resumed', async ({ page }) => {
  await gotoAgent(page);
  const composer = page.getByPlaceholder(/发消息/);
  await composer.fill('persist me');
  await composer.press('Enter');
  await expect(page.locator('main')).toContainText('Echo: persist me');

  await page.getByRole('button', { name: '新建', exact: true }).click();
  await page.getByRole('button', { name: /persist me/i }).click();
  await expect(page.locator('main')).toContainText('Echo: persist me');
});

test('groups conversations by workspace across providers', async ({ page, baseURL }) => {
  const projectsResponse = await fetch(`${baseURL}/api/projects`, {
    headers: { 'X-CA-Token': 'codeagent-e2e-token' },
  });
  const [firstProject] = await projectsResponse.json() as Array<{ path: string; group: string; available: boolean }>;
  const secondProject = { path: '/tmp/e2e-second-workspace', group: 'work', available: true };
  await page.route('**/api/projects', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify([firstProject, secondProject]),
  }));
  await page.route('**/api/agent/providers', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify([
      { providerId: 'fake', displayName: 'Fake', available: true },
      { providerId: 'codex', displayName: 'Codex', available: true },
    ]),
  }));
  await page.route('**/api/history?engine=*&limit=500', route => {
    const engine = new URL(route.request().url()).searchParams.get('engine');
    const session = engine === 'codex'
      ? {
        session_id: 'codex-second-workspace', engine: 'codex', project_path: secondProject.path,
        started_at: '2026-07-02T00:00:00.000Z', ended_at: null, message_count: 4,
        title: 'Codex in second workspace', model: 'test',
      }
      : {
        session_id: 'fake-first-workspace', engine: 'fake', project_path: firstProject.path,
        started_at: '2026-07-01T00:00:00.000Z', ended_at: null, message_count: 2,
        title: 'Fake in first workspace', model: 'test',
      };
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ sessions: [session] }) });
  });

  await gotoAgent(page);
  // Scoped to the sidebar: the header's workspace switcher carries the same
  // path in its title attribute, so an unscoped getByTitle matches both.
  const sidebar = page.getByRole('complementary', { name: '会话列表' });
  const firstWorkspace = sidebar.getByTitle(firstProject.path);
  const secondWorkspace = sidebar.getByTitle(secondProject.path);
  await expect(firstWorkspace).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByText('Fake in first workspace', { exact: true })).toBeVisible();
  await expect(secondWorkspace).toHaveAttribute('aria-expanded', 'false');
  await expect(page.getByText('Codex in second workspace', { exact: true })).not.toBeVisible();

  await page.getByLabel('引擎').selectOption('codex');
  await expect(firstWorkspace).toBeVisible();
  await secondWorkspace.click();
  await expect(page.getByText('Codex in second workspace', { exact: true })).toBeVisible();
});

test('removes the selected local conversation without deleting provider history', async ({ page }) => {
  await gotoAgent(page);
  const composer = page.getByPlaceholder(/发消息/);
  await composer.fill('remove local mapping');
  await composer.press('Enter');
  await expect(page.getByRole('button', { name: '移除当前会话' })).toBeVisible();
  // Wait for the turn to actually finish before removing. The banner (and an
  // enabled Remove button) appear as soon as the session exists, which is
  // before turn.start arrives over the socket — clicking inside that window
  // removes a conversation the gateway still considers busy, and the removal
  // is rejected. See the note in the PR: that race is a real product bug, but
  // it is not what this test is about.
  await expect(page.locator('main')).toContainText('Echo: remove local mapping');

  await page.getByRole('button', { name: '移除当前会话' }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: '移除' }).click();

  await expect(page.getByRole('button', { name: '移除当前会话' })).not.toBeVisible();
  await expect(page.locator('main')).not.toContainText('Echo: remove local mapping');
});

test('searches provider history and reveals additional pages on demand', async ({ page, baseURL }) => {
  const projectsResponse = await fetch(`${baseURL}/api/projects`, {
    headers: { 'X-CA-Token': 'codeagent-e2e-token' },
  });
  const projects = await projectsResponse.json() as Array<{ path: string }>;
  const history = Array.from({ length: 45 }, (_, index) => ({
    session_id: `native-${index}`,
    engine: 'fake',
    project_path: projects[0].path,
    started_at: `2026-07-01T00:${String(index).padStart(2, '0')}:00.000Z`,
    ended_at: null,
    message_count: index + 1,
    title: `Provider conversation ${index}`,
    model: 'fake-model',
  }));
  await page.route('**/api/history?engine=fake&limit=500', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ sessions: history, count: history.length }),
  }));

  await gotoAgent(page);
  await expect(page.getByRole('button', { name: '加载更多历史记录（25）' })).toBeVisible();
  await expect(page.getByText('Provider conversation 19', { exact: true })).toBeVisible();
  await expect(page.getByText('Provider conversation 20', { exact: true })).not.toBeVisible();

  await page.getByRole('button', { name: '加载更多历史记录（25）' }).click();
  await expect(page.getByText('Provider conversation 39', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '加载更多历史记录（5）' })).toBeVisible();

  await page.getByPlaceholder('搜索会话').fill('conversation 44');
  await expect(page.getByText('Provider conversation 44', { exact: true })).toBeVisible();
});

test('keeps unavailable workspace history collapsed until requested', async ({ page }) => {
  await page.route('**/api/history?engine=fake&limit=500', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      sessions: [{
        session_id: 'native-unavailable',
        engine: 'fake',
        project_path: '/tmp/not-registered',
        started_at: '2026-07-01T00:00:00.000Z',
        ended_at: null,
        message_count: 2,
        title: 'Unavailable provider conversation',
        model: 'fake-model',
      }],
      count: 1,
    }),
  }));

  await gotoAgent(page);
  const unavailable = page.getByRole('button', { name: '不可用工作区（1）' });
  await expect(unavailable).toHaveAttribute('aria-expanded', 'false');
  await expect(page.getByText('not-registered', { exact: true })).not.toBeVisible();

  await unavailable.click();
  await expect(page.getByText('not-registered', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '注册' })).toBeVisible();
});

test('shows a retry action when provider history fails', async ({ page }) => {
  let shouldFail = true;
  await page.route('**/api/history?engine=fake&limit=500', route => {
    if (shouldFail) return route.abort('failed');
    return route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ sessions: [], count: 0 }),
    });
  });

  await gotoAgent(page);
  await expect(page.getByText('Provider history could not be loaded.')).toBeVisible();

  shouldFail = false;
  await page.getByRole('button', { name: '重试' }).click();
  await expect(page.getByText('Provider history could not be loaded.')).not.toBeVisible();
});

test('a fast double-submit on a brand-new conversation creates only one session', async ({ page }) => {
  // Regression test: send() used to gate on `connecting`, which is only
  // set once connect() runs -- but a new conversation first awaits
  // createAgentSession() *before* connect() is ever called, leaving a
  // window where a second rapid submit raced a second POST /sessions.
  let createSessionRequests = 0;
  await page.route('**/api/agent/sessions', async route => {
    if (route.request().method() === 'POST') {
      createSessionRequests += 1;
      // Widen the race window: without this, the real gateway round trip
      // is fast enough locally that the second submit's send() call
      // always sees state.session already populated, masking the race.
      await new Promise(resolve => setTimeout(resolve, 300));
    }
    return route.continue();
  });

  await gotoAgent(page);
  const composer = page.getByPlaceholder(/发消息/);
  // Two distinct messages submitted back to back, before the first
  // createAgentSession() round trip can possibly resolve and populate
  // state.session -- both see state.session === null and, without the
  // fix, both fire their own POST /sessions.
  await composer.fill('first message');
  await composer.press('Enter');
  await composer.fill('second message');
  await composer.press('Enter');

  await expect(page.locator('main')).toContainText('Echo: first message');
  // The second submit is correctly rejected while the first is still in
  // flight (sendingRef guard) rather than firing a second session -- the
  // typed text stays put in the composer instead of being silently lost,
  // so the user can just press Enter again once the first turn lands.
  await expect(composer).toHaveValue('second message');
  expect(createSessionRequests).toBe(1);
});

test('restoring a conversation restores its workspace resource group', async ({ page, baseURL }) => {
  const projectsResponse = await fetch(`${baseURL}/api/projects`, {
    headers: { 'X-CA-Token': 'codeagent-e2e-token' },
  });
  const projects = await projectsResponse.json() as Array<{ path: string }>;
  await fetch(`${baseURL}/api/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CA-Token': 'codeagent-e2e-token' },
    body: JSON.stringify({ path: projects[0].path, group: 'work' }),
  });

  await gotoAgent(page);
  await expect(page.getByRole('button', { name: '资源组：work' })).toBeVisible();
  const composer = page.getByPlaceholder(/发消息/);
  await composer.fill('group aware session');
  await composer.press('Enter');
  await expect(page.locator('main')).toContainText('Echo: group aware session');

  await page.getByRole('button', { name: '资源组：work' }).click();
  await page.getByRole('option', { name: 'codeagent', exact: true }).click();
  await page.getByRole('button', { name: '新建', exact: true }).click();
  await page.getByRole('button', { name: /group aware session/i }).click();

  await expect(page.getByRole('button', { name: '资源组：work' })).toBeVisible();
});
