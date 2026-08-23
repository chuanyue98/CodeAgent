import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
  session({ sessionId: 'session-b', target: 'gemini', projectPath: '/workspace/project-b' }),
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
let sessionsFixture: SessionUsage[];

beforeEach(() => {
  deleteCalls = [];
  sessionsFixture = SESSIONS;
  globalThis.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    // SessionsPage now reads the workspace through ProjectProvider.
    if (url.includes('/api/config')) return jsonResponse({});
    if (url.includes('/api/projects')) return jsonResponse([]);
    if (url.includes('/api/groups')) return jsonResponse({});
    if (url.includes('/api/analytics/sessions')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        text: async () => JSON.stringify(sessionsFixture),
        json: async () => sessionsFixture,
      });
    }
    // Opening a row loads that session's transcript in the detail panel.
    if (url.startsWith('/api/history/') && init?.method !== 'DELETE') {
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

    await screen.findByText('2 个会话');

    fireEvent.click(screen.getByLabelText('选择会话 session-a'));

    expect(await screen.findByText('已选择 1 个')).toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: /删除所选/ }));

    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: '删除' }));

    await waitFor(() => {
      expect(deleteCalls).toHaveLength(1);
    });
    expect(deleteCalls[0]).toContain('/api/history/claude/session-a');

    await screen.findByText('1 个会话');
    expect(screen.queryByText('/workspace/project-a')).not.toBeInTheDocument();
    expect(screen.getByText('/workspace/project-b')).toBeVisible();
  });

  test('select-all-filtered then delete removes every visible session', async () => {
    renderSessionsPage();

    await screen.findByText('2 个会话');

    fireEvent.click(screen.getByLabelText('选择当前筛选条件下的全部会话'));
    expect(await screen.findByText('已选择 2 个')).toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: /删除所选/ }));
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: '删除' }));

    await waitFor(() => {
      expect(deleteCalls).toHaveLength(2);
    });
    await screen.findByText('没有符合筛选条件的会话');
  });
});

describe('SessionsPage session detail', () => {
  test('one click on a row shows the conversation, not a link to another tab', async () => {
    renderSessionsPage();
    await screen.findByText('2 个会话');

    fireEvent.click(screen.getByRole('button', { name: '打开会话 session-a' }));

    const panel = await screen.findByTestId('session-detail');
    expect(await within(panel).findByText('how do I ship this')).toBeVisible();

    // Reading a transcript used to require hopping to the Events tab.
    expect(screen.queryByText(/在事件页中查看/)).not.toBeInTheDocument();
  });

  test('the panel carries the usage figures and both session actions', async () => {
    renderSessionsPage();
    await screen.findByText('2 个会话');

    fireEvent.click(screen.getByRole('button', { name: '打开会话 session-a' }));
    const panel = await screen.findByTestId('session-detail');

    expect(within(panel).getByText('用量')).toBeVisible();
    expect(within(panel).getByText('$0.12')).toBeVisible();
    // Convert lives here now instead of only in Events…
    expect(within(panel).getByRole('button', { name: /Gemini/ })).toBeVisible();
    // …and so does deleting this one session.
    expect(within(panel).getByRole('button', { name: '删除此会话' })).toBeVisible();
  });

  test('closing the panel returns to the plain list', async () => {
    renderSessionsPage();
    await screen.findByText('2 个会话');

    fireEvent.click(screen.getByRole('button', { name: '打开会话 session-a' }));
    const panel = await screen.findByTestId('session-detail');

    fireEvent.click(within(panel).getByLabelText('关闭会话详情'));

    await waitFor(() => {
      expect(screen.queryByTestId('session-detail')).not.toBeInTheDocument();
    });
  });

  test('deleting from the panel drops the row and closes the panel', async () => {
    renderSessionsPage();
    await screen.findByText('2 个会话');

    fireEvent.click(screen.getByRole('button', { name: '打开会话 session-a' }));
    const panel = await screen.findByTestId('session-detail');
    fireEvent.click(within(panel).getByRole('button', { name: '删除此会话' }));

    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: '删除' }));

    await screen.findByText('1 个会话');
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

    await screen.findByText('2 个会话');
    expect(screen.getByText('/workspace/via-claude')).toBeVisible();
    expect(screen.getByText('/workspace/via-codex')).toBeVisible();
  });

  test('opening one row leaves the other unselected', async () => {
    renderSessionsPage();
    await screen.findByText('2 个会话');

    const rows = screen.getAllByRole('button', { name: `打开会话 ${SHARED_ID}` });
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
    await screen.findByText('2 个会话');

    const checkboxes = screen.getAllByLabelText(`选择会话 ${SHARED_ID}`);
    expect(checkboxes).toHaveLength(2);

    fireEvent.click(checkboxes[0]);

    expect(await screen.findByText('已选择 1 个')).toBeVisible();
  });
});
