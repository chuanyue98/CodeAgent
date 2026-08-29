import { render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import HomePage from '../pages/HomePage';
import { SystemMetricsProvider } from '../context/SystemMetricsContext';

interface Backend {
  events?: unknown[];
  sessions?: unknown[];
  daily?: unknown[];
  runs?: unknown[];
  metrics?: Record<string, number>;
}

function jsonResponse(data: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    text: async () => JSON.stringify(data),
    json: async () => data,
  });
}

function mockBackend({ events = [], sessions = [], daily = [], runs = [], metrics }: Backend = {}) {
  globalThis.fetch = vi.fn().mockImplementation((url: string) => {
    if (url.includes('/api/history/audit')) return jsonResponse({ events, count: events.length });
    if (url.includes('/api/analytics/sessions')) return jsonResponse({ sessions, nextCursor: null });
    if (url.includes('/api/analytics/daily')) return jsonResponse(daily);
    if (url.includes('/api/tasks/runs')) return jsonResponse(runs);
    if (url.includes('/api/system/metrics')) {
      return jsonResponse(
        metrics ?? {
          cpuPercent: 12,
          memoryPercent: 40,
          memoryUsedGb: 6.4,
          memoryTotalGb: 16,
          diskPercent: 55,
          diskUsedGb: 220,
          diskTotalGb: 400,
          uptimeSeconds: 100,
          historyFileSizeMb: 1,
          logFileCount: 2,
        },
      );
    }
    return jsonResponse({});
  }) as typeof fetch;
}

function renderHome() {
  return render(
    <MemoryRouter>
      <SystemMetricsProvider>
        <HomePage />
      </SystemMetricsProvider>
    </MemoryRouter>,
  );
}

function auditEvent(overrides: Record<string, unknown> = {}) {
  return {
    eventId: 'e1',
    eventType: 'message',
    engine: 'claude',
    projectPath: '/workspace/project-a',
    sessionId: 'session-a',
    sessionTitle: 'A session',
    timestamp: new Date().toISOString(),
    role: 'user',
    model: 'claude-opus',
    contentPreview: 'Fix the launcher',
    ...overrides,
  };
}

function sessionRow(overrides: Record<string, unknown> = {}) {
  return {
    sessionId: 'session-a',
    target: 'claude',
    projectPath: '/workspace/project-a',
    inputTokens: 0,
    outputTokens: 0,
    cacheCreationTokens: 0,
    cacheReadTokens: 0,
    cost: 0,
    lastActivity: new Date().toISOString(),
    modelsUsed: [],
    modelBreakdowns: [],
    title: 'Refactor the launcher',
    ...overrides,
  };
}

const originalFetch = globalThis.fetch;

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  globalThis.fetch = originalFetch;
});

test('a run of tool calls says what each call did, not just the tool name', async () => {
  // "Bash / Bash / Bash" identifies nothing; the arguments are what separates
  // one row from the one above it.
  mockBackend({
    events: [
      auditEvent({
        eventId: 'e1',
        eventType: 'tool_call',
        toolName: 'Bash',
        argsPreview: '{"command": "uv run pytest"}',
      }),
      auditEvent({
        eventId: 'e2',
        eventType: 'tool_call',
        toolName: 'Bash',
        argsPreview: '{"command": "uv run ruff check ."}',
      }),
    ],
  });
  renderHome();

  expect(await screen.findByText('Bash · uv run pytest')).toBeInTheDocument();
  expect(screen.getByText('Bash · uv run ruff check .')).toBeInTheDocument();
});

test('a preview truncated mid-JSON still reads as text, not as braces and quotes', async () => {
  // Parsers cut args_preview at 200 chars, so the JSON often stops mid-string.
  mockBackend({
    events: [
      auditEvent({
        eventType: 'tool_call',
        toolName: 'Edit',
        argsPreview: '{"file_path": "core/services/agent_gateway.py", "old_string": "def start',
      }),
    ],
  });
  renderHome();

  expect(
    await screen.findByText('Edit · core/services/agent_gateway.py'),
  ).toBeInTheDocument();
});

test('a tool call with no readable arguments falls back to the tool name', async () => {
  mockBackend({
    events: [auditEvent({ eventType: 'tool_call', toolName: 'Read', argsPreview: '{}' })],
  });
  renderHome();

  expect(await screen.findByText('Read')).toBeInTheDocument();
});

test('a message with no content falls back to the session title', async () => {
  mockBackend({
    events: [auditEvent({ contentPreview: '   ', sessionTitle: 'Nightly review' })],
  });
  renderHome();

  expect(await screen.findByText('Nightly review')).toBeInTheDocument();
});

test('an empty timeline says so rather than sitting on the loading line', async () => {
  mockBackend({ events: [] });
  renderHome();

  expect(
    await screen.findByText('No activity yet — start a session to see it here.'),
  ).toBeInTheDocument();
});

test('a failed timeline lookup lands on the empty state, not a permanent spinner', async () => {
  globalThis.fetch = vi.fn().mockRejectedValue(new Error('unreachable')) as typeof fetch;
  renderHome();

  await waitFor(() =>
    expect(
      screen.getByText('No activity yet — start a session to see it here.'),
    ).toBeInTheDocument(),
  );
});

test('"continue where you left off" opens the terminal, not the detail page', async () => {
  // The label is a verb. It used to land on the object view, two clicks short
  // of the conversation it promised.
  mockBackend({ sessions: [sessionRow({ target: 'codex' })] });
  renderHome();

  const link = await screen.findByRole('link', { name: /Refactor the launcher/ });
  expect(link).toHaveAttribute(
    'href',
    '/agent/terminal?engine=codex&cwd=%2Fworkspace%2Fproject-a&session=session-a',
  );
});

test('an untitled session is named by its workspace', async () => {
  mockBackend({ sessions: [sessionRow({ title: '   ' })] });
  renderHome();

  const list = (await screen.findByText('Continue where you left off')).closest('section')!;
  expect(within(list).getAllByText('project-a').length).toBeGreaterThan(0);
});

test('only running tasks reach the dashboard', async () => {
  mockBackend({
    runs: [
      { taskId: 'review_1', engine: 'claude', status: 'completed' },
      { taskId: 'deploy_2', engine: 'codex', status: 'running' },
    ],
  });
  renderHome();

  expect(await screen.findByText('deploy_2')).toBeInTheDocument();
  expect(screen.queryByText('review_1')).not.toBeInTheDocument();
});

test('no running task offers the way to start one', async () => {
  mockBackend({ runs: [{ taskId: 'review_1', engine: 'claude', status: 'completed' }] });
  renderHome();

  expect(await screen.findByText('Nothing running right now.')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /Run a task/ })).toBeInTheDocument();
});

test('the activity strip plots the days it claims to plot', async () => {
  const today = new Date();
  const key = (offset: number) => {
    const day = new Date(today);
    day.setDate(day.getDate() - offset);
    return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`;
  };
  mockBackend({
    daily: [
      { date: key(0), cost: 4, inputTokens: 0, outputTokens: 0 },
      { date: key(3), cost: 1, inputTokens: 0, outputTokens: 0 },
    ],
  });
  renderHome();

  const strip = await screen.findByTitle('Cost per day, last 12 days');
  const bars = strip.querySelectorAll('span');
  expect(bars).toHaveLength(12);
  // The busiest day is full height; a day with no work keeps a 6% stub so the
  // strip stays a calendar rather than silently shortening.
  expect((bars[11] as HTMLElement).style.height).toBe('100%');
  expect((bars[8] as HTMLElement).style.height).toBe('25%');
  expect((bars[0] as HTMLElement).style.height).toBe('6%');
});

test('the system card reads from the shared metrics subscription', async () => {
  mockBackend();
  renderHome();

  expect(await screen.findByText('12%')).toBeInTheDocument();
  expect(screen.getByText('6.4 / 16.0 GB')).toBeInTheDocument();
  expect(screen.getByText('220 / 400 GB')).toBeInTheDocument();
});
