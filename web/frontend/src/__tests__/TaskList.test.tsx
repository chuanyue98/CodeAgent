import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';
import TaskList from '../components/TaskDashboard/TaskList';
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
    expect(screen.queryByLabelText('搜索任务')).not.toBeInTheDocument();
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

    fireEvent.change(screen.getByLabelText('搜索任务'), { target: { value: 'diagnose' } });

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

    fireEvent.change(screen.getByLabelText('搜索任务'), { target: { value: 'nonexistent' } });

    expect(screen.getByText('没有匹配的任务。')).toBeVisible();
  });
});
