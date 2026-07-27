import { fireEvent, render, screen } from '@testing-library/react';
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
    task_name: 'code_review',
    engine: 'claude',
    group: 'codeagent',
    workspace: '/workspace/proj',
    cron_expr: '0 9 * * *',
    enabled: true,
    created_at: 0,
    last_run_at: null,
    last_run_status: null,
    next_run_at: null,
    ...overrides,
  };
}

const SCHEDULES: Schedule[] = [
  makeSchedule({ id: 'sched-1', task_name: 'code_review' }),
  makeSchedule({ id: 'sched-2', task_name: 'dependency_check', engine: 'gemini', cron_expr: '0 0 * * 1' }),
];

beforeEach(() => {
  globalThis.fetch = vi.fn().mockImplementation((url: string) => {
    if (url.includes('/api/config')) return jsonResponse({});
    if (url.includes('/api/projects')) {
      return jsonResponse([{ path: '/workspace/proj', group: 'codeagent', available: true }]);
    }
    if (url.includes('/api/groups')) return jsonResponse({});
    if (url === '/api/schedules') return jsonResponse(SCHEDULES);
    if (url.startsWith('/api/schedules/preview')) return jsonResponse({ valid: true, next_runs: [] });
    if (url.endsWith('/api/tasks')) return jsonResponse([{ name: 'code_review', title: 'Code Review' }]);
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

    fireEvent.change(screen.getByLabelText('Search schedules'), { target: { value: 'gemini' } });

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
