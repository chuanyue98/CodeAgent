import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import SessionsPage from '../components/SessionsPage';
import { ProjectProvider } from '../context/ProjectContext';
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
  session({ sessionId: 'session-b', target: 'codebuddy', projectPath: '/workspace/project-b' }),
];

function jsonResponse(data: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    text: async () => JSON.stringify(data),
    json: async () => data,
  });
}

let deleteCalls: string[];
let historyLoads: string[];
let sessionsLoads: number;
let sessionsFixture: SessionUsage[];

beforeEach(() => {
  deleteCalls = [];
  historyLoads = [];
  sessionsLoads = 0;
  sessionsFixture = SESSIONS;
  globalThis.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    // SessionsPage now reads the workspace through ProjectProvider.
    if (url.includes('/api/config')) return jsonResponse({});
    if (url.includes('/api/projects')) return jsonResponse([]);
    if (url.includes('/api/groups')) return jsonResponse({});
    if (url.includes('/api/analytics/sessions')) {
      sessionsLoads += 1;
      // The endpoint returns one page plus the cursor for the next, not a
      // bare array.
      const page = {
        sessions: sessionsFixture,
        nextCursor: null,
        total: sessionsFixture.length,
      };
      return Promise.resolve({
        ok: true,
        status: 200,
        text: async () => JSON.stringify(page),
        json: async () => page,
      });
    }
    // Opening a row loads that session's transcript in the detail panel.
    if (url.startsWith('/api/history/') && init?.method !== 'DELETE') {
      historyLoads.push(url);
      return jsonResponse({
        session_id: 'session-a',
        engine: 'claude',
        project_path: '/workspace/project-a',
        title: 'Session A',
        messages: [
          {
            role: 'user',
            content: 'how do I ship this',
            timestamp: '2026-07-20T10:00:00Z',
            model: 'claude-opus',
            tool_calls: [],
          },
        ],
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

function renderSessionsPage(initialEntry = '/activity/sessions') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <ProjectProvider>
        <SessionsPage />
      </ProjectProvider>
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

describe('SessionsPage session detail', () => {
  test('one click on a row shows the conversation, not a link to another tab', async () => {
    renderSessionsPage();
    await screen.findByText('2 sessions');

    fireEvent.click(screen.getByRole('button', { name: 'Open session session-a' }));

    const panel = await screen.findByTestId('session-detail');
    expect(await within(panel).findByText('how do I ship this')).toBeVisible();

    // Reading a transcript used to require hopping to the Events tab.
    expect(screen.queryByText(/View in Events/)).not.toBeInTheDocument();
  });

  test('the panel carries the usage figures and both session actions', async () => {
    renderSessionsPage();
    await screen.findByText('2 sessions');

    fireEvent.click(screen.getByRole('button', { name: 'Open session session-a' }));
    const panel = await screen.findByTestId('session-detail');

    // Scoped to the Usage section: the progress strip above it repeats the
    // headline cost, so an unscoped query matches twice.
    const usage = within(panel).getByTestId('session-usage');
    expect(within(usage).getByText('Usage')).toBeVisible();
    expect(within(usage).getByText('$0.12')).toBeVisible();
    // Convert lives here now instead of only in Events…
    expect(within(panel).getByRole('button', { name: /CodeBuddy/ })).toBeVisible();
    // …and so does deleting this one session.
    expect(within(panel).getByRole('button', { name: /Delete this session/ })).toBeVisible();
  });

  test('closing the panel returns to the plain list', async () => {
    renderSessionsPage();
    await screen.findByText('2 sessions');

    fireEvent.click(screen.getByRole('button', { name: 'Open session session-a' }));
    const panel = await screen.findByTestId('session-detail');

    fireEvent.click(within(panel).getByLabelText('Close session details'));

    await waitFor(() => {
      expect(screen.queryByTestId('session-detail')).not.toBeInTheDocument();
    });
  });

  test('refreshing the list leaves the open transcript untouched', async () => {
    renderSessionsPage();
    await screen.findByText('2 sessions');

    fireEvent.click(screen.getByRole('button', { name: 'Open session session-a' }));
    const panel = await screen.findByTestId('session-detail');
    await within(panel).findByText('how do I ship this');
    expect(historyLoads).toHaveLength(1);

    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    await waitFor(() => expect(sessionsLoads).toBe(2));

    // Refresh used to swap the whole page for the loading skeleton, which
    // unmounted this panel: the transcript was refetched and whatever you
    // had scrolled to was gone. Same DOM node, no second fetch.
    expect(screen.getByTestId('session-detail')).toBe(panel);
    expect(historyLoads).toHaveLength(1);
    expect(screen.queryByText('Loading sessions')).not.toBeInTheDocument();
  });

  test('deleting from the panel drops the row and closes the panel', async () => {
    renderSessionsPage();
    await screen.findByText('2 sessions');

    fireEvent.click(screen.getByRole('button', { name: 'Open session session-a' }));
    const panel = await screen.findByTestId('session-detail');
    fireEvent.click(within(panel).getByRole('button', { name: /Delete this session/ }));

    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));

    await screen.findByText('1 session');
    expect(deleteCalls[0]).toContain('/api/history/claude/session-a');
    expect(screen.queryByTestId('session-detail')).not.toBeInTheDocument();
  });
});

describe('SessionsPage session identity', () => {
  // The backend aggregates usage on (session_id, engine), so the same id can
  // appear under two engines. Keying rows or expansion state on the bare id
  // collided: React saw duplicate keys and expanding one row expanded both.
  const SHARED_ID = 'shared-session';

  beforeEach(() => {
    sessionsFixture = [
      session({ sessionId: SHARED_ID, target: 'claude', projectPath: '/workspace/via-claude' }),
      session({ sessionId: SHARED_ID, target: 'codex', projectPath: '/workspace/via-codex' }),
    ];
  });

  test('renders both engines rows for one shared session id', async () => {
    renderSessionsPage();

    await screen.findByText('2 sessions');
    expect(screen.getByText('/workspace/via-claude')).toBeVisible();
    expect(screen.getByText('/workspace/via-codex')).toBeVisible();
  });

  test('opening one row leaves the other unselected', async () => {
    renderSessionsPage();
    await screen.findByText('2 sessions');

    const rows = screen.getAllByRole('button', { name: `Open session ${SHARED_ID}` });
    expect(rows).toHaveLength(2);
    expect(rows.every(row => row.getAttribute('aria-pressed') === 'false')).toBe(true);

    fireEvent.click(rows[0]);

    await waitFor(() => {
      expect(rows[0]).toHaveAttribute('aria-pressed', 'true');
    });
    expect(rows[1]).toHaveAttribute('aria-pressed', 'false');
  });

  test('selecting one row selects only that engine session', async () => {
    renderSessionsPage();
    await screen.findByText('2 sessions');

    const checkboxes = screen.getAllByLabelText(`Select session ${SHARED_ID}`);
    expect(checkboxes).toHaveLength(2);

    fireEvent.click(checkboxes[0]);

    expect(await screen.findByText('1 selected')).toBeVisible();
  });
});

describe('SessionsPage stale responses', () => {
  test('a slow earlier search does not overwrite a later, narrower one', async () => {
    // Both searches are in flight at once; the first one answers last. Without
    // a latest-wins guard its wider result lands on top of the narrower one
    // the user is actually looking at.
    const pending: Array<(sessions: SessionUsage[]) => void> = [];

    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/config')) return jsonResponse({});
      if (url.includes('/api/projects')) return jsonResponse([]);
      if (url.includes('/api/groups')) return jsonResponse({});
      if (url.includes('/api/analytics/sessions')) {
        return new Promise(resolve => {
          pending.push(sessions =>
            resolve({
              ok: true,
              status: 200,
              text: async () => JSON.stringify({ sessions, nextCursor: null, total: sessions.length }),
              json: async () => ({ sessions, nextCursor: null, total: sessions.length }),
            } as Response),
          );
        });
      }
      return jsonResponse({});
    });

    renderSessionsPage();
    // The list renders a skeleton until the first response lands, and the
    // search box lives behind it.
    await waitFor(() => expect(pending).toHaveLength(1));
    pending[0]([session({ sessionId: 'seed' })]);
    await screen.findByText('1 session');

    // Two searches now go out back to back, both still in flight.
    fireEvent.change(screen.getByPlaceholderText('Project or session...'), {
      target: { value: 'a' },
    });
    await waitFor(() => expect(pending).toHaveLength(2), { timeout: 2000 });
    fireEvent.change(screen.getByPlaceholderText('Project or session...'), {
      target: { value: 'ab' },
    });
    await waitFor(() => expect(pending).toHaveLength(3), { timeout: 2000 });

    // The narrower request answers first, then the wider one straggles in.
    pending[2]([session({ sessionId: 'narrow' })]);
    await screen.findByText('1 session');
    pending[1]([session({ sessionId: 'wide-1' }), session({ sessionId: 'wide-2' })]);

    // Let the straggler's handler run before asserting it changed nothing.
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.getByText('1 session')).toBeVisible();
  });
});
