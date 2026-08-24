import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import CronPage from '../components/CronPage';
import { ProjectProvider } from '../context/ProjectContext';
import type { Schedule } from '../api/schedules';

function jsonResponse(data: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    text: async () => JSON.stringify(data),
    json: async () => data,
  });
}

function makeSchedule(overrides: Partial<Schedule>): Schedule {
  return {
    id: 'sched-1',
    taskName: 'code_review',
    engine: 'claude',
    group: 'codeagent',
    workspace: '/workspace/proj',
    cronExpr: '0 9 * * *',
    enabled: true,
    createdAt: 0,
    lastRunAt: null,
    lastRunStatus: null,
    nextRunAt: null,
    ...overrides,
  };
}

let taskLibrary: { name: string; title: string }[];
let createdTasks: Record<string, unknown>[];

const SCHEDULES: Schedule[] = [
  makeSchedule({ id: 'sched-1', taskName: 'code_review' }),
  makeSchedule({ id: 'sched-2', taskName: 'dependency_check', engine: 'codebuddy', cronExpr: '0 0 * * 1' }),
];

let schedulesFixture: Schedule[];

beforeEach(() => {
  taskLibrary = [{ name: 'code_review', title: 'Code Review' }];
  createdTasks = [];
  schedulesFixture = SCHEDULES;
  globalThis.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (url.includes('/api/config')) return jsonResponse({});
    if (url.includes('/api/projects')) {
      return jsonResponse([{ path: '/workspace/proj', group: 'codeagent', available: true }]);
    }
    if (url.includes('/api/groups')) return jsonResponse({});
    if (url === '/api/schedules') return jsonResponse(schedulesFixture);
    if (url.startsWith('/api/schedules/preview')) return jsonResponse({ valid: true, nextRuns: [] });
    if (url.endsWith('/api/tasks') && init?.method === 'POST') {
      const body = JSON.parse(String(init.body)) as Record<string, unknown>;
      createdTasks.push(body);
      taskLibrary = [...taskLibrary, { name: String(body.name), title: String(body.title) }];
      return jsonResponse({ name: body.name });
    }
    if (url.endsWith('/api/tasks')) return jsonResponse(taskLibrary);
    if (url.includes('/api/engines')) return jsonResponse([{ id: 'claude', name: 'Claude' }]);
    return Promise.reject(new Error(`Unhandled fetch to ${url}`));
  }) as unknown as typeof fetch;
});

function renderCronPage() {
  return render(
    <ProjectProvider>
      <CronPage />
    </ProjectProvider>,
  );
}

describe('CronPage schedule search', () => {
  test('filters schedules by task name, engine, or cron expression', async () => {
    renderCronPage();

    await screen.findByText('code_review');
    expect(screen.getByText('dependency_check')).toBeVisible();

    fireEvent.change(screen.getByLabelText('Search schedules'), { target: { value: 'codebuddy' } });

    expect(screen.getByText('dependency_check')).toBeVisible();
    expect(screen.queryByText('code_review')).not.toBeInTheDocument();
  });

  test('shows an empty state when no schedule matches', async () => {
    renderCronPage();

    await screen.findByText('code_review');
    fireEvent.change(screen.getByLabelText('Search schedules'), { target: { value: 'nonexistent' } });

    expect(screen.getByText('No schedules match your search.')).toBeVisible();
  });
});

describe('CronPage task templates', () => {
  // The empty state used to be one sentence. The obstacle to using schedules
  // was never the form -- it was not knowing what is worth scheduling.
  test('an empty schedule list offers templates instead of a bare sentence', async () => {
    schedulesFixture = [];
    renderCronPage();

    expect(await screen.findByText('Start from a template')).toBeVisible();
    expect(screen.getByText('Weekly code review')).toBeVisible();
    expect(screen.getByText('Security scan')).toBeVisible();
  });

  test('using a template writes the blueprint and prefills the form, but creates no schedule', async () => {
    schedulesFixture = [];
    renderCronPage();

    const card = (await screen.findByText('Weekly code review')).closest('div');
    fireEvent.click(within(card as HTMLElement).getByRole('button', { name: /Use this template/ }));

    await waitFor(() => expect(createdTasks).toHaveLength(1));

    // The four sections POST /api/tasks already accepts -- no new format.
    expect(createdTasks[0]).toMatchObject({
      name: 'weekly-code-review',
      title: 'Weekly code review',
    });
    for (const section of ['objective', 'context', 'instructions', 'verification']) {
      expect(String(createdTasks[0][section]).length).toBeGreaterThan(0);
    }

    // Prefilled, not applied: one click on a card must not put a recurring
    // job on the user's machine.
    const cronField = await screen.findByDisplayValue('0 9 * * 1');
    expect(cronField).toBeVisible();
    const scheduleWrites = (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mock.calls
      .filter(([url, init]) => String(url) === '/api/schedules' && (init as RequestInit | undefined)?.method === 'POST');
    expect(scheduleWrites).toHaveLength(0);
  });

  test('a template whose task already exists selects it instead of failing', async () => {
    schedulesFixture = [];
    taskLibrary = [{ name: 'weekly-code-review', title: 'Weekly code review' }];
    renderCronPage();

    const card = (await screen.findByText('Weekly code review')).closest('div');
    fireEvent.click(within(card as HTMLElement).getByRole('button', { name: /Use this template/ }));

    expect(await screen.findByText(/already exists/)).toBeVisible();
    expect(createdTasks).toHaveLength(0);
  });
});
