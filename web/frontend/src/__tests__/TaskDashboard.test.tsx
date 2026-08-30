import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import TaskDashboard from '../components/TaskDashboard';
import { ProjectProvider } from '../context/ProjectContext';
import { createQueryClient } from '../utils/queryClient';
import type { RunStatus, Task } from '../components/TaskDashboard/types';

const TASKS: Task[] = [
  { name: 'code_review', title: 'Code Review', description: 'Review diffs', hasStages: false, stages: [] },
  { name: 'refactor', title: 'Refactor', description: 'Restructure', hasStages: false, stages: [] },
];

const TASK_DETAIL: Task = {
  ...TASKS[0],
  resolvedSkills: [],
  resolvedPrompts: ['base'],
};

const ENGINES = [{ id: 'opencode', name: 'OpenCode AI', description: '' }];

function makeRun(overrides: Partial<RunStatus> = {}): RunStatus {
  return {
    taskId: 'code_review-1000',
    engine: 'opencode',
    status: 'running',
    logPath: '/tmp/run.log',
    startTime: Date.now() / 1000 - 10,
    taskName: 'code_review',
    ...overrides,
  };
}

/** Full API surface for the dashboard, overridable per test. The default
    shape mirrors a quiet server: two blueprints, no runs. */
function routeFetch(overrides: {
  tasks?: Task[];
  runs?: RunStatus[];
  poll?: (call: number) => { status: RunStatus; progress: Partial<Task> };
  projects?: { path: string; group: string }[];
} = {}) {
  let pollCalls = 0;
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? 'GET').toUpperCase();
    const json = (data: unknown) => ({
      ok: true,
      status: 200,
      text: async () => JSON.stringify(data),
      json: async () => data,
    });

    if (url.includes('/api/tasks/generate')) return json({ taskId: 'gen-1' });
    if (url.includes('/api/tasks/runs/') && method === 'GET') {
      pollCalls += 1;
      return json(
        overrides.poll?.(pollCalls) ?? {
          status: makeRun(),
          progress: {},
        },
      );
    }
    if (url.includes('/api/tasks/runs/') && method === 'POST') return json({ success: true });
    if (url.includes('/api/tasks/runs')) return json(overrides.runs ?? []);
    if (/\/api\/tasks\/[^/]+\/run$/.test(url) && method === 'POST') return json(makeRun());
    if (/\/api\/tasks\/[^/]+\/runs$/.test(url)) return json([]);
    if (/\/api\/tasks\/[^/]+\?/.test(url) || /\/api\/tasks\/[^/]+$/.test(url)) {
      return json(TASK_DETAIL);
    }
    if (url.endsWith('/api/tasks')) return json(overrides.tasks ?? TASKS);
    if (url.includes('/api/engines')) return json(ENGINES);
    if (url.includes('/api/projects')) return json(overrides.projects ?? []);
    if (url.includes('/api/config')) {
      return json({ default_mode: 'local', language: 'en' });
    }
    if (url.includes('/api/groups')) {
      return json({ codeagent: { skills: [], prompts: [], hooks: [], plugins: [] } });
    }
    return json({});
  });
  // setupTests installs globalThis.fetch as a vi.fn already, so vi.spyOn
  // hands back that same mock — clear it so call counting starts at zero.
  const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(spy as never);
  fetchSpy.mockClear();
  return fetchSpy;
}

/** Flushes pending promise chains under fake timers. findByText/waitFor
    cannot be used here — their internal polling intervals never fire once
    vi.useFakeTimers is active, so the initial mount settles via flushes. */
async function settle(rounds = 3) {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {});
  }
}

function renderDashboard(initialPath = '/automations/tasks') {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[initialPath]}>
        <ProjectProvider>
          <TaskDashboard />
        </ProjectProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe('TaskDashboard list and detail', () => {
  test('lists tasks and opens the detail on click', async () => {
    const fetchSpy = routeFetch();
    renderDashboard();
    await settle();

    expect(screen.getByText('Code Review')).toBeVisible();
    expect(screen.getByText('Refactor')).toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: /Code Review/ }));
    await settle();

    expect(screen.getByText('Run Task')).toBeVisible();
    // Opening a task fetches its detail with the current group attached.
    expect(
      fetchSpy.mock.calls.some(([url]) =>
        String(url).includes('/api/tasks/code_review') && String(url).includes('group='),
      ),
    ).toBe(true);
  });

  test('deep link ?task=<name> opens the task exactly once', async () => {
    const fetchSpy = routeFetch();
    renderDashboard('/automations/tasks?task=code_review');
    await settle();

    // The detail replaces the list once the task data lands.
    expect(screen.getByText('Run Task')).toBeVisible();
    const detailCalls = () =>
      fetchSpy.mock.calls.filter(([url]) =>
        String(url).includes('/api/tasks/code_review?'),
      ).length;
    expect(detailCalls()).toBe(1);

    // Read-once semantics: the param is consumed, so a later tasks poll
    // must not reopen (and re-fetch) the deep-linked task.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(detailCalls()).toBe(1);
  });

  test('an unknown deep link leaves the list in place', async () => {
    routeFetch();
    renderDashboard('/automations/tasks?task=does_not_exist');
    await settle();
    expect(screen.getByText('Code Review')).toBeVisible();
    expect(screen.queryByText('Run Task')).not.toBeInTheDocument();
  });
});

describe('TaskDashboard polling', () => {
  test('idle dashboard re-polls tasks and runs every 5s', async () => {
    const fetchSpy = routeFetch();
    renderDashboard();
    await settle();
    expect(screen.getByText('Code Review')).toBeVisible();

    const listCalls = () =>
      fetchSpy.mock.calls.filter(([url]) => String(url).endsWith('/api/tasks')).length;
    const runCalls = () =>
      fetchSpy.mock.calls.filter(([url]) => String(url).includes('/api/tasks/runs')).length;
    const baseList = listCalls();
    const baseRuns = runCalls();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(listCalls()).toBe(baseList + 1);
    expect(runCalls()).toBe(baseRuns + 1);

    // The cadence repeats, not a one-shot timer.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(listCalls()).toBe(baseList + 2);
  });

  test('a started run switches to 2s status polling until it finishes', async () => {
    const fetchSpy = routeFetch({
      projects: [{ path: '/work/demo', group: 'web' }],
      poll: call => ({
        status: makeRun({ status: call < 2 ? 'running' : 'completed', endTime: Date.now() / 1000 }),
        progress: {},
      }),
    });
    renderDashboard();
    await settle();
    expect(screen.getByText('Code Review')).toBeVisible();

    // ProjectProvider adopts the registered workspace on first load.
    expect(window.localStorage.getItem('codeagent.selectedWorkspace')).toBe('/work/demo');

    fireEvent.click(screen.getByRole('button', { name: /Code Review/ }));
    await settle();
    expect(screen.getByText('Run Task')).toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: 'Run Task' }));
    // The run request resolves and the 2s poll starts ticking.
    await settle();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    const pollCalls = () =>
      fetchSpy.mock.calls.filter(([url]) =>
        String(url).includes('/api/tasks/runs/code_review-1000'),
      ).length;
    expect(pollCalls()).toBeGreaterThanOrEqual(1);

    const before = pollCalls();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(pollCalls()).toBeGreaterThanOrEqual(before + 1);

    // The second poll reports completion: the active run clears, so the
    // 2s poll stops entirely while the idle 5s list poll resumes.
    await settle();
    expect(screen.getByText('Run Task')).toBeVisible();
    const settled = pollCalls();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(pollCalls()).toBe(settled);
  });
});
