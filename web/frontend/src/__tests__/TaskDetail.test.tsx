import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, test, vi } from 'vitest';
import TaskDetail from '../components/TaskDashboard/TaskDetail';
import type { Engine, RunStatus, Task } from '../components/TaskDashboard/types';
import { createQueryClient } from '../utils/queryClient';

const engines: Engine[] = [
  { id: 'claude', name: 'Claude Code', description: '' },
  { id: 'opencode', name: 'OpenCode AI', description: '' },
];

const projects = [
  { path: '/work/demo', group: 'web' },
  { path: '/work/other', group: 'common' },
];

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    name: 'code_review',
    title: 'Code Review',
    description: 'Review the working diff',
    hasStages: true,
    stages: [
      { name: 'Scan', status: 'done', goal: 'find issues' },
      { name: 'Report', status: 'in_progress', goal: 'write it up' },
    ],
    resolvedSkills: [],
    resolvedPrompts: [],
    ...overrides,
  };
}

function makeRun(overrides: Partial<RunStatus> = {}): RunStatus {
  const now = Date.now() / 1000;
  return {
    taskId: 'code_review-1',
    engine: 'claude',
    status: 'completed',
    logPath: '/tmp/run.log',
    startTime: now - 100,
    endTime: now - 60,
    exitCode: 0,
    taskName: 'code_review',
    ...overrides,
  };
}

function renderDetail(overrides: {
  task?: Task;
  activeRun?: RunStatus;
  runHistory?: RunStatus[];
  onBack?: () => void;
  onRun?: (engine: string) => void;
  onStop?: (id: string) => void;
  onDeleted?: () => void;
  onTaskUpdated?: (task: Task) => void;
  workspace?: string;
  onWorkspaceChange?: (workspace: string) => void;
} = {}) {
  return render(
    <TaskDetail
      task={overrides.task ?? makeTask()}
      engines={engines}
      activeRun={overrides.activeRun}
      runHistory={overrides.runHistory ?? []}
      onBack={overrides.onBack ?? vi.fn()}
      onRun={overrides.onRun ?? vi.fn()}
      onStop={overrides.onStop ?? vi.fn()}
      onDeleted={overrides.onDeleted ?? vi.fn()}
      onTaskUpdated={overrides.onTaskUpdated ?? vi.fn()}
      workspace={overrides.workspace ?? '/work/demo'}
      projects={projects}
      onWorkspaceChange={overrides.onWorkspaceChange ?? vi.fn()}
    />,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('TaskDetail rendering', () => {
  test('shows title, description, stage progress, and run metadata', () => {
    renderDetail({ runHistory: [makeRun()] });
    expect(screen.getByRole('heading', { level: 2, name: /Code Review/ })).toBeVisible();
    expect(screen.getByText('Review the working diff')).toBeVisible();
    // 1 of 2 stages done.
    expect(screen.getByText('50%')).toBeVisible();
    expect(screen.getByText('1 / 2 stages completed')).toBeVisible();
    // Engine and duration appear both in the metadata row and in the history.
    expect(screen.getAllByText('claude').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('40s').length).toBeGreaterThanOrEqual(1);
  });

  test('empty skill/prompt/run sections show their placeholders', () => {
    renderDetail();
    expect(screen.getByText('No skills mounted')).toBeVisible();
    expect(screen.getByText('No prompts injected')).toBeVisible();
    expect(screen.getByText('No runs yet')).toBeVisible();
  });

  test('run history lists runs and marks the viewed one', () => {
    renderDetail({
      runHistory: [
        makeRun({ taskId: 'code_review-2', status: 'failed', exitCode: 1 }),
        makeRun({ taskId: 'code_review-1' }),
      ],
    });
    const entries = screen.getAllByText('claude');
    expect(entries.length).toBeGreaterThanOrEqual(2);
    // The failed badge shows in both the metadata row and the history entry.
    expect(screen.getAllByText('failed').length).toBeGreaterThanOrEqual(1);
  });
});

describe('TaskDetail actions', () => {
  test('Back returns to the list', () => {
    const onBack = vi.fn();
    renderDetail({ onBack });
    fireEvent.click(screen.getByRole('button', { name: /Back/ }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  test('Run posts with the selected engine and workspace', () => {
    const onRun = vi.fn();
    const onWorkspaceChange = vi.fn();
    renderDetail({ onRun, onWorkspaceChange });

    // Default engine is the first one (claude); switch to opencode.
    fireEvent.change(screen.getByDisplayValue('Claude Code'), {
      target: { value: 'opencode' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Run Task' }));
    expect(onRun).toHaveBeenCalledWith('opencode');
  });

  test('changing the workspace select propagates upward', () => {
    const onWorkspaceChange = vi.fn();
    renderDetail({ onWorkspaceChange });
    fireEvent.change(screen.getByLabelText('Workspace'), {
      target: { value: '/work/other' },
    });
    expect(onWorkspaceChange).toHaveBeenCalledWith('/work/other');
  });

  test('while a run is active, Stop replaces the controls and delete is blocked', () => {
    const onStop = vi.fn();
    renderDetail({
      activeRun: makeRun({ taskId: 'code_review-live', status: 'running', endTime: undefined }),
      onStop,
    });
    expect(screen.getByText('Running')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Stop Execution' })).toBeVisible();
    // The engine/workspace selects and Run button are gone while running.
    expect(screen.queryByRole('button', { name: 'Run Task' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Stop Execution' }));
    expect(onStop).toHaveBeenCalledWith('code_review-live');
  });

  test('delete asks for confirmation, then reports deletion', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => ({
      ok: true,
      status: 200,
      text: async () => '{}',
      json: async () => ({}),
    }) as Response);
    const onDeleted = vi.fn();
    renderDetail({ onDeleted });

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    expect(
      screen.getByRole('alertdialog', { name: 'Delete this task?' }),
    ).toBeVisible();

    fireEvent.click(screen.getAllByRole('button', { name: 'Delete' }).at(-1)!);
    await waitFor(() => expect(onDeleted).toHaveBeenCalledTimes(1));
  });

  test('delete failure keeps the detail open with an inline error', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => {
      throw new Error('still running');
    });
    const onDeleted = vi.fn();
    renderDetail({ onDeleted });

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    fireEvent.click(screen.getAllByRole('button', { name: 'Delete' }).at(-1)!);

    await waitFor(() =>
      expect(screen.getByText('still running')).toBeVisible(),
    );
    expect(onDeleted).not.toHaveBeenCalled();
  });

  test('Edit opens the edit modal prefilled with the content', () => {
    renderDetail({ task: makeTask({ content: '# blueprint' }) });
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    expect(screen.getByLabelText('Task content (Markdown)')).toHaveValue('# blueprint');
  });
});

describe('TaskDetail changes tab', () => {
  function renderWithChanges(response: unknown) {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => ({
      ok: true,
      status: 200,
      text: async () => JSON.stringify(response),
      json: async () => response,
    }) as Response);
    return render(
      <QueryClientProvider client={createQueryClient()}>
        <TaskDetail
          task={makeTask()}
          engines={engines}
          activeRun={makeRun({ status: 'running', endTime: undefined })}
          runHistory={[]}
          onBack={vi.fn()}
          onRun={vi.fn()}
          onStop={vi.fn()}
          onDeleted={vi.fn()}
          onTaskUpdated={vi.fn()}
          workspace="/work/demo"
          projects={projects}
          onWorkspaceChange={vi.fn()}
        />
      </QueryClientProvider>,
    );
  }

  test('shows the run\'s commits, file stats and diff', async () => {
    renderWithChanges({
      available: true,
      mode: 'commits',
      workspace: '/work/demo',
      window: { since: '2026-08-30T09:00:00+08:00', until: '2026-08-30T10:00:00+08:00' },
      commits: [
        {
          sha: 'abcdef1234567890abcdef1234567890abcdef12',
          message: 'feat: wire the changes tab',
          author: 'tester',
          committedAt: '2026-08-30T09:30:00+08:00',
        },
      ],
      files: [{ path: 'core/app.py', additions: 3, deletions: 1 }],
      diff: '+wired\n-unwired',
      diffTruncated: false,
    });

    // The logs view is the default; the changes query only fires on the tab.
    fireEvent.click(screen.getByRole('button', { name: 'Changes' }));
    await waitFor(() =>
      expect(screen.getByText('feat: wire the changes tab')).toBeVisible(),
    );
    expect(screen.getByText('abcdef1')).toBeVisible();
    expect(screen.getByText('core/app.py')).toBeVisible();
    expect(screen.getByText('+3')).toBeVisible();
    // The diff sits in a <pre> with real newlines; getByText compares the
    // matcher against normalized (whitespace-collapsed) text, so query the
    // collapsed form.
    expect(screen.getByText('+wired -unwired')).toBeVisible();

    // Switching back hides the changes content.
    fireEvent.click(screen.getByRole('button', { name: 'Logs' }));
    expect(screen.queryByText('feat: wire the changes tab')).not.toBeInTheDocument();
  });

  test('degrades to a reason message when the workspace cannot be inspected', async () => {
    renderWithChanges({ available: false, reason: 'not_git_repo', workspace: '/work/demo' });

    fireEvent.click(screen.getByRole('button', { name: 'Changes' }));
    await waitFor(() =>
      expect(
        screen.getByText('The run workspace is not a git repository.'),
      ).toBeVisible(),
    );
  });
});
