import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import HomePage from '../pages/HomePage';
import { ProjectProvider } from '../context/ProjectContext';
import { TerminalProvider, useTerminal } from '../context/TerminalContext';
import type { SessionUsage } from '../api/analytics';
import { jsonResponse, session as baseSession } from './factories';

interface Backend {
  sessions?: unknown[];
  daily?: unknown[];
  runs?: unknown[];
  schedules?: unknown[];
}

function mockBackend({ sessions = [], daily = [], runs = [], schedules = [] }: Backend = {}) {
  globalThis.fetch = vi.fn().mockImplementation((url: string) => {
    if (url.includes('/api/projects')) {
      return jsonResponse([{ path: '/workspace/project-a', group: 'common', available: true }]);
    }
    if (url.includes('/api/analytics/sessions')) return jsonResponse({ sessions, nextCursor: null });
    if (url.includes('/api/analytics/daily')) return jsonResponse(daily);
    if (url.includes('/api/tasks/runs')) return jsonResponse(runs);
    if (url.includes('/api/schedules')) return jsonResponse(schedules);
    return jsonResponse({});
  }) as typeof fetch;
}

/** Shows the open terminal tabs as JSON, so a test can read what Start opened. */
function TabsProbe() {
  const { tabs } = useTerminal();
  return <pre data-testid="tabs">{JSON.stringify(tabs)}</pre>;
}

function renderHome() {
  return render(
    <MemoryRouter>
      <ProjectProvider>
        <TerminalProvider>
          <HomePage />
          <TabsProbe />
        </TerminalProvider>
      </ProjectProvider>
    </MemoryRouter>,
  );
}

function sessionRow(overrides: Partial<SessionUsage> = {}): SessionUsage {
  return baseSession({
    inputTokens: 1000,
    outputTokens: 500,
    lastActivity: new Date().toISOString(),
    modelsUsed: [],
    title: 'Refactor the launcher',
    ...overrides,
  });
}

function schedule(overrides: Record<string, unknown> = {}) {
  return {
    id: 's1',
    taskName: 'Nightly dependency check',
    engine: 'claude',
    group: 'common',
    workspace: '/workspace/project-a',
    cronExpr: '0 9 * * *',
    enabled: true,
    createdAt: 0,
    lastRunAt: null,
    lastRunStatus: null,
    nextRunAt: Math.floor(Date.now() / 1000) + 3 * 3600,
    ...overrides,
  };
}

const originalFetch = globalThis.fetch;

beforeEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

afterEach(() => {
  globalThis.fetch = originalFetch;
});

test('offers a session in each engine, and none of them is the plain shell', async () => {
  mockBackend();
  renderHome();

  const group = await screen.findByRole('group', { name: /engine for the new session|新会话使用的引擎/i });
  const names = within(group).getAllByRole('button').map(button => button.textContent);
  expect(names).toEqual(['Claude', 'OpenCode', 'Codex', 'CodeBuddy', 'Antigravity']);
});

function openedTabs(): Array<{ engine: string; cwd: string; prompt?: string }> {
  return JSON.parse(screen.getByTestId('tabs').textContent ?? '[]');
}

test('Start opens a session in the chosen engine with the typed first message', async () => {
  mockBackend();
  renderHome();

  const group = await screen.findByRole('group', { name: /engine for the new session|新会话使用的引擎/i });
  fireEvent.click(within(group).getByRole('button', { name: 'Codex' }));
  expect(within(group).getByRole('button', { name: 'Codex' })).toHaveAttribute('aria-pressed', 'true');
  expect(within(group).getByRole('button', { name: 'Claude' })).toHaveAttribute('aria-pressed', 'false');

  fireEvent.change(screen.getByLabelText(/first message|第一条消息/i), {
    target: { value: '  fix the login redirect  ' },
  });
  await waitFor(() => expect(screen.getByRole('button', { name: /^(Start|开始)$/ })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: /^(Start|开始)$/ }));

  await waitFor(() => expect(openedTabs()).toHaveLength(1));
  expect(openedTabs()[0]).toMatchObject({
    engine: 'codex',
    cwd: '/workspace/project-a',
    prompt: 'fix the login redirect',
  });
});

test('Ctrl+Enter in the box starts the session, and an empty box starts a blank one', async () => {
  mockBackend();
  renderHome();

  const box = await screen.findByLabelText(/first message|第一条消息/i);
  await waitFor(() => expect(screen.getByRole('button', { name: /^(Start|开始)$/ })).toBeEnabled());
  fireEvent.keyDown(box, { key: 'Enter', ctrlKey: true });

  await waitFor(() => expect(openedTabs()).toHaveLength(1));
  expect(openedTabs()[0].engine).toBe('claude');
  expect(openedTabs()[0].prompt).toBeUndefined();
});

test('the first message is not saved with the tabs, so a reload cannot resend it', async () => {
  mockBackend();
  renderHome();

  fireEvent.change(await screen.findByLabelText(/first message|第一条消息/i), { target: { value: 'secret plan' } });
  await waitFor(() => expect(screen.getByRole('button', { name: /^(Start|开始)$/ })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: /^(Start|开始)$/ }));

  await waitFor(() => expect(openedTabs()).toHaveLength(1));
  const saved = localStorage.getItem('codeagent.terminalTabs') ?? '';
  expect(saved).toContain('"engine":"claude"');
  expect(saved).not.toContain('secret plan');
});

test('a recent session resumes in a terminal through its own engine', async () => {
  mockBackend({
    sessions: [sessionRow({ sessionId: 'abc', target: 'codex', projectPath: '/workspace/project-a' })],
  });
  renderHome();

  const link = await screen.findByRole('link', { name: /Refactor the launcher/ });
  const href = new URL(link.getAttribute('href') ?? '', 'http://localhost');
  expect(href.pathname).toBe('/agent/terminal');
  expect(href.searchParams.get('engine')).toBe('codex');
  expect(href.searchParams.get('session')).toBe('abc');
  expect(href.searchParams.get('cwd')).toBe('/workspace/project-a');
});

test('a session without a title is labelled by its workspace', async () => {
  mockBackend({ sessions: [sessionRow({ title: '', projectPath: '/work/blog-site' })] });
  renderHome();

  const link = await screen.findByRole('link', { name: /blog-site/ });
  expect(link).toBeInTheDocument();
});

test('with no sessions it says so instead of rendering an empty list', async () => {
  mockBackend({ sessions: [] });
  renderHome();
  expect(await screen.findByText(/no sessions yet/i)).toBeInTheDocument();
});

test('running tasks are listed under In progress; finished ones are not', async () => {
  mockBackend({
    runs: [
      { taskId: 'db-migrate', engine: 'claude', status: 'running' },
      { taskId: 'old-report', engine: 'codex', status: 'completed' },
    ],
  });
  renderHome();

  expect(await screen.findByText('db-migrate')).toBeInTheDocument();
  expect(screen.queryByText('old-report')).toBeNull();
});

test('with nothing open or running, In progress points at starting a session', async () => {
  mockBackend();
  renderHome();
  expect(await screen.findByText(/nothing is running/i)).toBeInTheDocument();
});

test('the next enabled schedule shows with a countdown; disabled ones are skipped', async () => {
  mockBackend({
    schedules: [
      schedule({ id: 'a', taskName: 'Nightly dependency check' }),
      schedule({ id: 'b', taskName: 'Paused weekly report', enabled: false }),
    ],
  });
  renderHome();

  expect(await screen.findByText('Nightly dependency check')).toBeInTheDocument();
  expect(screen.queryByText('Paused weekly report')).toBeNull();
  expect(screen.getByText(/in 2h|in 3h|2 ?小时后|3 ?小时后/)).toBeInTheDocument();
});

test('a schedule whose last run failed is raised above the lists', async () => {
  mockBackend({ schedules: [schedule({ taskName: 'Migrate database', lastRunStatus: 'failed' })] });
  renderHome();

  expect(await screen.findByText(/Migrate database failed on its last run|Migrate database 上次运行失败/)).toBeInTheDocument();
});

test('token totals count today and the last seven days across engines', async () => {
  const now = new Date();
  const iso = (offset: number) => {
    const d = new Date(now);
    d.setDate(d.getDate() - offset);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  };
  const row = (date: string, input: number, output: number, target = 'claude') => ({
    date, target, inputTokens: input, outputTokens: output,
    cacheCreationTokens: 0, cacheReadTokens: 0, modelsUsed: [], modelBreakdowns: [],
  });
  mockBackend({
    daily: [row(iso(0), 1000, 500), row(iso(0), 200, 300, 'codex'), row(iso(3), 4000, 0), row(iso(20), 90000, 0)],
  });
  renderHome();

  // today: 1000+500+200+300 = 2.0K; week adds 4000 but not the 20-day-old row.
  expect(await screen.findByText('2.0K')).toBeInTheDocument();
  expect(screen.getByText('6.0K')).toBeInTheDocument();
});
