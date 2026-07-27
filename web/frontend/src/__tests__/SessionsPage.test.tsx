import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import SessionsPage from '../components/SessionsPage';
import type { SessionUsage } from '../api/analytics';

function session(overrides: Partial<SessionUsage>): SessionUsage {
  return {
    sessionId: 'session-a',
    target: 'claude',
    projectPath: '/workspace/project-a',
    inputTokens: 100,
    outputTokens: 50,
    cacheCreationTokens: 0,
    cacheReadTokens: 0,
    cost: 0.12,
    lastActivity: '2026-07-20T10:00:00Z',
    modelsUsed: ['claude-opus'],
    modelBreakdowns: [],
    ...overrides,
  };
}

const SESSIONS: SessionUsage[] = [
  session({ sessionId: 'session-a', target: 'claude', projectPath: '/workspace/project-a' }),
  session({ sessionId: 'session-b', target: 'gemini', projectPath: '/workspace/project-b' }),
];

let deleteCalls: string[];

beforeEach(() => {
  deleteCalls = [];
  globalThis.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (url.includes('/api/analytics/sessions')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        text: async () => JSON.stringify(SESSIONS),
        json: async () => SESSIONS,
      });
    }
    if (url.startsWith('/api/history/') && init?.method === 'DELETE') {
      deleteCalls.push(url);
      const body = { status: 'deleted', session_id: 'deleted' };
      return Promise.resolve({
        ok: true,
        status: 200,
        text: async () => JSON.stringify(body),
        json: async () => body,
      });
    }
    return Promise.reject(new Error(`Unhandled fetch to ${url}`));
  }) as unknown as typeof fetch;
});

afterEach(() => {
  vi.restoreAllMocks();
});

function renderSessionsPage() {
  return render(
    <MemoryRouter>
      <SessionsPage />
    </MemoryRouter>,
  );
}

describe('SessionsPage batch delete', () => {
  test('selecting sessions and confirming deletes only the selected ones', async () => {
    renderSessionsPage();

    await screen.findByText('2 sessions');

    fireEvent.click(screen.getByLabelText('Select session session-a'));

    expect(await screen.findByText('1 selected')).toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: /Delete selected/ }));

    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));

    await waitFor(() => {
      expect(deleteCalls).toHaveLength(1);
    });
    expect(deleteCalls[0]).toContain('/api/history/claude/session-a');

    await screen.findByText('1 session');
    expect(screen.queryByText('/workspace/project-a')).not.toBeInTheDocument();
    expect(screen.getByText('/workspace/project-b')).toBeVisible();
  });

  test('select-all-filtered then delete removes every visible session', async () => {
    renderSessionsPage();

    await screen.findByText('2 sessions');

    fireEvent.click(screen.getByLabelText('Select all sessions matching the current filters'));
    expect(await screen.findByText('2 selected')).toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: /Delete selected/ }));
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));

    await waitFor(() => {
      expect(deleteCalls).toHaveLength(2);
    });
    await screen.findByText('No sessions match your filters');
  });
});
