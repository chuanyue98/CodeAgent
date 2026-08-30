import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';
import TaskList from '../components/TaskDashboard/TaskList';
import type { RunStatus } from '../components/TaskDashboard/types';
import type { Task } from '../components/TaskDashboard/types';

function makeTask(name: string, title: string, description = ''): Task {
  return { name, title, description, hasStages: false, stages: [] };
}

// The search box only appears once the list is long enough to need one.
const MANY_TASKS: Task[] = [
  makeTask('code_review', 'Code Review', 'Review the working diff'),
  makeTask('refactor', 'Refactor', 'Restructure without changing behavior'),
  makeTask('create_pr', 'Create PR', 'Open a pull request'),
  makeTask('write_tests', 'Write Tests', 'Fill in missing coverage'),
  makeTask('fix_bug', 'Fix Bug', 'Diagnose a reported failure'),
  makeTask('dependency_check', 'Dependency Check', 'Audit outdated packages'),
];

describe('TaskList search', () => {
  test('search box is hidden for short lists', () => {
    render(
      <TaskList
        tasks={MANY_TASKS.slice(0, 3)}
        runs={[]}
        onSelect={vi.fn()}
        onGenerateClick={vi.fn()}
        onManualCreateClick={vi.fn()}
      />,
    );
    expect(screen.queryByLabelText('Search tasks')).not.toBeInTheDocument();
  });

  test('filters the visible tasks by name, title, or description', () => {
    render(
      <TaskList
        tasks={MANY_TASKS}
        runs={[]}
        onSelect={vi.fn()}
        onGenerateClick={vi.fn()}
        onManualCreateClick={vi.fn()}
      />,
    );

    expect(screen.getByText('Code Review')).toBeVisible();
    expect(screen.getByText('Fix Bug')).toBeVisible();

    fireEvent.change(screen.getByLabelText('Search tasks'), { target: { value: 'diagnose' } });

    expect(screen.getByText('Fix Bug')).toBeVisible();
    expect(screen.queryByText('Code Review')).not.toBeInTheDocument();
  });

  test('shows an empty state when nothing matches', () => {
    render(
      <TaskList
        tasks={MANY_TASKS}
        runs={[]}
        onSelect={vi.fn()}
        onGenerateClick={vi.fn()}
        onManualCreateClick={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText('Search tasks'), { target: { value: 'nonexistent' } });

    expect(screen.getByText('No tasks match your search.')).toBeVisible();
  });
});

describe('TaskList run activity feed', () => {
  test('shows recent runs and opens the task on click', () => {
    const onSelect = vi.fn();
    const run: RunStatus = {
      taskId: 'code_review-1725000000',
      engine: 'claude',
      status: 'completed',
      logPath: '/tmp/run.log',
      startTime: Date.now() / 1000 - 3600,
      endTime: Date.now() / 1000 - 3500,
      taskName: 'code_review',
    };
    render(
      <TaskList
        tasks={MANY_TASKS}
        runs={[run]}
        onSelect={onSelect}
        onGenerateClick={vi.fn()}
        onManualCreateClick={vi.fn()}
      />,
    );

    const feed = screen.getByRole('complementary', { name: 'Run activity' });
    expect(within(feed).getByText('Code Review')).toBeVisible();
    expect(screen.getByText('Completed')).toBeVisible();

    fireEvent.click(within(feed).getAllByRole('button')[0]);
    expect(onSelect).toHaveBeenCalledWith('code_review');
  });
});
