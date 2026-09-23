import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import DelegationsPage from '../components/DelegationsPage';
import { createQueryClient } from '../utils/queryClient';

function run(overrides: Record<string, unknown> = {}) {
  return {
    runId: 'claude-20260923-141420-b4f2f2',
    engine: 'claude',
    mode: 'review',
    status: 'completed',
    instruction: 'review the diff\nsecond line',
    workspace: '/workspace/proj',
    outputLog: '/home/u/.codeagent/delegations/x/output.log',
    elapsedSeconds: 89.4,
    ...overrides,
  };
}

function mockApi(runs: ReturnType<typeof run>[], detail: Record<string, unknown> = {}) {
  globalThis.fetch = vi.fn().mockImplementation((url: string) => {
    const body = url.endsWith('/api/delegations') ? { runs } : { ...runs[0], outputTail: '', ...detail };
    return Promise.resolve({
      ok: true,
      status: 200,
      text: async () => JSON.stringify(body),
      json: async () => body,
    });
  }) as typeof fetch;
}

function renderPage() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <DelegationsPage />
    </QueryClientProvider>,
  );
}

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

test('rows show the first line of the instruction and only live runs can be stopped', async () => {
  mockApi([
    run(),
    run({ runId: 'codex-20260923-150000-aaaaaa', engine: 'codex', status: 'running', instruction: 'fix it', elapsedSeconds: 5 }),
  ]);
  renderPage();

  expect(await screen.findByText('review the diff')).toBeInTheDocument();
  expect(screen.getByText('1 running · 2 listed')).toBeInTheDocument();
  expect(screen.getByText('1min 29s')).toBeInTheDocument();
  expect(screen.getAllByRole('button', { name: 'Stop' })).toHaveLength(1);
});

test('expanding a finished run shows its result and changed files', async () => {
  mockApi([run()], {
    result: {
      success: true,
      exitCode: 0,
      summary: 'LGTM, one nit',
      summaryTruncated: false,
      filesChanged: ['core/a.py'],
      diff: '',
      diffTruncated: false,
      branch: null,
      isolatedWorktree: false,
      durationSeconds: 89.4,
      error: null,
    },
  });
  renderPage();

  fireEvent.click(await screen.findByRole('button', { expanded: false }));

  expect(await screen.findByText('LGTM, one nit')).toBeInTheDocument();
  expect(screen.getByText('core/a.py')).toBeInTheDocument();
});
