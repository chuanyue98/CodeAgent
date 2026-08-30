import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, test, vi } from 'vitest';
import EditTaskModal from '../components/TaskDashboard/EditTaskModal';
import GenerateTaskModal from '../components/TaskDashboard/GenerateTaskModal';
import NewTaskModal from '../components/TaskDashboard/NewTaskModal';
import type { Task } from '../components/TaskDashboard/types';

function jsonResponse(data: unknown) {
  const text = JSON.stringify(data);
  return {
    ok: true,
    status: 200,
    text: async () => text,
    json: async () => data,
  };
}

/** Routes fetch calls per (url-substring, method) so each test controls its
    own API surface; anything unhandled resolves to an empty object. */
function routeFetch(
  handlers: Array<[match: string, method: string, response: unknown]>,
) {
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? 'GET').toUpperCase();
    for (const [match, matchMethod, response] of handlers) {
      if (url.includes(match) && method === matchMethod) {
        return jsonResponse(response);
      }
    }
    return jsonResponse({});
  });
  // setupTests installs globalThis.fetch as a vi.fn already, so vi.spyOn
  // hands back that same mock — clear it so calls only reflect this test.
  const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(spy as never);
  fetchSpy.mockClear();
  return fetchSpy;
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe('NewTaskModal', () => {
  test('an invalid file name shows the rule and blocks submit', () => {
    render(<NewTaskModal onClose={vi.fn()} onCreated={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('File name'), {
      target: { value: 'bad name!' },
    });
    expect(
      screen.getByText('Letters, digits, dot, dash, underscore only.'),
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'Create Task' })).toBeDisabled();
  });

  test('missing title keeps submit disabled', () => {
    render(<NewTaskModal onClose={vi.fn()} onCreated={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('File name'), {
      target: { value: 'daily-audit' },
    });
    expect(screen.getByRole('button', { name: 'Create Task' })).toBeDisabled();
  });

  test('creating posts the sections and reports the name', async () => {
    const fetchSpy = routeFetch([['/api/tasks', 'POST', { name: 'daily-audit' }]]);
    const onCreated = vi.fn();
    render(<NewTaskModal onClose={vi.fn()} onCreated={onCreated} />);

    fireEvent.change(screen.getByLabelText('File name'), {
      target: { value: 'daily-audit' },
    });
    fireEvent.change(screen.getByLabelText('Title'), {
      target: { value: 'Daily Audit' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Create Task' }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith('daily-audit'));
    const [, init] = fetchSpy.mock.calls[0];
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body.name).toBe('daily-audit');
    expect(body.title).toBe('Daily Audit');
  });

  test('a failed create surfaces the error and keeps the modal open', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => {
      throw new Error('taken');
    });
    const onClose = vi.fn();
    render(<NewTaskModal onClose={onClose} onCreated={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('File name'), {
      target: { value: 'daily-audit' },
    });
    fireEvent.change(screen.getByLabelText('Title'), {
      target: { value: 'Daily Audit' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Create Task' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('taken'));
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe('EditTaskModal', () => {
  const task: Task = {
    name: 'refactor',
    title: 'Refactor',
    description: '',
    hasStages: false,
    stages: [],
    content: '# Original content',
  };

  test('prefills the current markdown', () => {
    render(<EditTaskModal task={task} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.getByLabelText('Task content (Markdown)')).toHaveValue(
      '# Original content',
    );
  });

  test('saving PUTs the content and returns the updated task', async () => {
    const updated: Task = { ...task, content: '# Edited' };
    const fetchSpy = routeFetch([['/api/tasks/refactor', 'PUT', updated]]);
    const onSaved = vi.fn();
    render(<EditTaskModal task={task} onClose={vi.fn()} onSaved={onSaved} />);

    fireEvent.change(screen.getByLabelText('Task content (Markdown)'), {
      target: { value: '# Edited' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(updated));
    const [, init] = fetchSpy.mock.calls[0];
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      content: '# Edited',
    });
  });

  test('blank content disables saving', () => {
    render(
      <EditTaskModal task={{ ...task, content: '' }} onClose={vi.fn()} onSaved={vi.fn()} />,
    );
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  });
});

describe('GenerateTaskModal', () => {
  const engines = [{ id: 'claude', name: 'Claude Code', description: '' }];

  test('needs name, title, and description before enabling Generate', () => {
    render(
      <GenerateTaskModal engines={engines} onClose={vi.fn()} onCreated={vi.fn()} />,
    );
    const generate = () => screen.getByRole('button', { name: 'Generate' });
    expect(generate()).toBeDisabled();
    fireEvent.change(screen.getByLabelText('File name'), {
      target: { value: 'nightly-sweep' },
    });
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Sweep' } });
    expect(generate()).toBeDisabled();
    fireEvent.change(
      screen.getByLabelText('Describe what this task should do'),
      { target: { value: 'audit dependencies' } },
    );
    expect(generate()).toBeEnabled();
  });

  test('polls the run and reports success once the task exists', async () => {
    vi.useFakeTimers();
    routeFetch([
      ['/api/tasks/generate', 'POST', { taskId: 'gen-1' }],
      ['/api/tasks/runs/gen-1', 'GET', {
        status: { taskId: 'gen-1', status: 'completed' },
        progress: {},
      }],
      ['/api/tasks', 'GET', [{ name: 'nightly-sweep', title: 'Sweep' }]],
    ]);
    const onCreated = vi.fn();
    render(
      <GenerateTaskModal engines={engines} onClose={vi.fn()} onCreated={onCreated} />,
    );

    fireEvent.change(screen.getByLabelText('File name'), {
      target: { value: 'nightly-sweep' },
    });
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Sweep' } });
    fireEvent.change(
      screen.getByLabelText('Describe what this task should do'),
      { target: { value: 'audit dependencies' } },
    );
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Generate' }));
    });
    // The generating view replaces the form while the run is tracked.
    expect(screen.getByText(/is writing tasks\/nightly-sweep\.md/)).toBeVisible();
    // The run is already completed, so the poll chain resolves through
    // microtasks alone — flush them. waitFor cannot be used here: under fake
    // timers its internal interval never fires.
    await act(async () => {});
    await act(async () => {});
    expect(onCreated).toHaveBeenCalledWith('nightly-sweep');
  });

  test('a run that ends without the task file shows the failure message', async () => {
    routeFetch([
      ['/api/tasks/generate', 'POST', { taskId: 'gen-2' }],
      ['/api/tasks/runs/gen-2', 'GET', {
        status: { taskId: 'gen-2', status: 'failed' },
        progress: {},
      }],
      ['/api/tasks', 'GET', []],
    ]);
    render(
      <GenerateTaskModal engines={engines} onClose={vi.fn()} onCreated={vi.fn()} />,
    );
    fireEvent.change(screen.getByLabelText('File name'), {
      target: { value: 'nightly-sweep' },
    });
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Sweep' } });
    fireEvent.change(
      screen.getByLabelText('Describe what this task should do'),
      { target: { value: 'audit dependencies' } },
    );
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Generate' }));
    });
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(
        'AI did not finish writing the task file',
      ),
    );
    // Failure flips the primary action to a retry.
    expect(screen.getByRole('button', { name: 'Try Again' })).toBeVisible();
  });

  test('cancelling generation stops the run and returns to the form', async () => {
    const fetchSpy = routeFetch([
      ['/api/tasks/generate', 'POST', { taskId: 'gen-3' }],
      ['/api/tasks/runs/gen-3', 'GET', {
        status: { taskId: 'gen-3', status: 'running' },
        progress: {},
      }],
    ]);
    render(
      <GenerateTaskModal engines={engines} onClose={vi.fn()} onCreated={vi.fn()} />,
    );
    fireEvent.change(screen.getByLabelText('File name'), {
      target: { value: 'nightly-sweep' },
    });
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Sweep' } });
    fireEvent.change(
      screen.getByLabelText('Describe what this task should do'),
      { target: { value: 'audit dependencies' } },
    );
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Generate' }));
    });
    await act(async () => {});

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    });

    // The stop request went out and the form is editable again.
    expect(
      fetchSpy.mock.calls.some(([url, init]) =>
        String(url).includes('/api/tasks/runs/gen-3/stop') &&
        (init as RequestInit).method === 'POST',
      ),
    ).toBe(true);
    expect(screen.getByLabelText('File name')).toBeVisible();
  });
});
