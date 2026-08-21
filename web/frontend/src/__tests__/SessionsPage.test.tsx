import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import SessionsPage from '../components/SessionsPage';
import type { NativeAgentSession } from '../types/agent';

function session(overrides: Partial<NativeAgentSession>): NativeAgentSession {
  return {
    session_id: 'session-a',
    engine: 'claude',
    project_path: '/workspace/project-a',
    started_at: '2026-07-20T10:00:00Z',
    ended_at: '2026-07-20T10:05:00Z',
    message_count: 3,
    title: 'title-a',
    model: 'claude-opus',
    ...overrides,
  };
}

const SESSIONS: NativeAgentSession[] = [
  session({ session_id: 'session-a', engine: 'claude', project_path: '/workspace/project-a', title: 'title-a' }),
  session({ session_id: 'session-b', engine: 'gemini', project_path: '/workspace/project-b', title: 'title-b' }),
];

let deleteCalls: string[];

beforeEach(() => {
  deleteCalls = [];
  globalThis.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (url.includes('/api/history') && !init?.method) {
      const body = { sessions: SESSIONS, count: SESSIONS.length };
      return Promise.resolve({
        ok: true,
        status: 200,
        text: async () => JSON.stringify(body),
        json: async () => body,
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

describe('SessionsPage session browser', () => {
  test('lists all native sessions across engines', async () => {
    renderSessionsPage();
    await screen.findByText('2 sessions');
    expect(screen.getByText('title-a')).toBeVisible();
    expect(screen.getByText('title-b')).toBeVisible();
    expect(screen.getAllByText('claude').length).toBeGreaterThan(0);
    expect(screen.getAllByText('gemini').length).toBeGreaterThan(0);
  });

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
    expect(screen.queryByText('title-a')).not.toBeInTheDocument();
    expect(screen.getByText('title-b')).toBeVisible();
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