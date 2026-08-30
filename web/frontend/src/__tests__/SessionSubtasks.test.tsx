import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import SessionsPage from '../components/SessionsPage';
import SessionDetailPanel from '../components/SessionDetailPanel';
import { ProjectProvider } from '../context/ProjectContext';
import type { SessionUsage } from '../api/analytics';
import { jsonResponse, session } from './factories';

/** A parent session whose two subagent runs are folded into it. */
function parentWithSubtasks(): SessionUsage {
  return session({
    sessionId: 'session-parent',
    title: 'Review 两个修复提交',
    inputTokens: 300,
    outputTokens: 100,
    cost: 6.85,
    own: {
      inputTokens: 100,
      outputTokens: 30,
      cacheCreationTokens: 0,
      cacheReadTokens: 0,
      cost: 0.85,
      lastActivity: '2026-07-20T10:00:00Z',
    },
    subtasks: [
      session({
        sessionId: 'agent-frontend',
        title: '前端代码质量检查',
        agent: 'explore',
        inputTokens: 120,
        outputTokens: 40,
        cost: 3.0,
      }),
      session({
        sessionId: 'agent-backend',
        title: '后端与工程化审查',
        agent: 'explore',
        inputTokens: 80,
        outputTokens: 30,
        cost: 3.0,
      }),
    ],
  });
}

const transcripts: Record<string, unknown> = {
  'session-parent': {
    sessionId: 'session-parent',
    engine: 'claude',
    projectPath: '/workspace/project-a',
    title: 'Review 两个修复提交',
    messages: [
      {
        role: 'user',
        content: 'review the two fixes',
        timestamp: '2026-07-20T10:00:00Z',
        model: 'claude-opus',
        toolCalls: [],
      },
    ],
  },
  'agent-frontend': {
    sessionId: 'agent-frontend',
    engine: 'claude',
    projectPath: '/workspace/project-a',
    title: '前端代码质量检查',
    messages: [
      {
        role: 'user',
        content: 'check the frontend',
        timestamp: '2026-07-20T10:05:00Z',
        model: 'claude-opus',
        toolCalls: [],
      },
    ],
  },
};

let sessionsFixture: SessionUsage[];

beforeEach(() => {
  sessionsFixture = [parentWithSubtasks()];
  globalThis.fetch = vi.fn().mockImplementation((url: string) => {
    if (url.includes('/api/config')) return jsonResponse({});
    if (url.includes('/api/projects')) return jsonResponse([]);
    if (url.includes('/api/groups')) return jsonResponse({});
    if (url.includes('/api/analytics/sessions')) {
      return jsonResponse({
        sessions: sessionsFixture,
        nextCursor: null,
        total: sessionsFixture.length,
      });
    }
    if (url.startsWith('/api/history/')) {
      const id = url.split('/api/history/claude/')[1]?.split('?')[0] ?? '';
      return jsonResponse(transcripts[id] ?? transcripts['session-parent']);
    }
    return Promise.reject(new Error(`Unhandled fetch to ${url}`));
  }) as unknown as typeof fetch;
});

afterEach(() => {
  vi.restoreAllMocks();
});

function renderPanel(usage: SessionUsage) {
  return render(
    <MemoryRouter>
      <SessionDetailPanel
        engine="claude"
        sessionId={usage.sessionId}
        projectPath={usage.projectPath}
        usage={usage}
        onClose={() => {}}
      />
    </MemoryRouter>,
  );
}

describe('subagent runs in the session list', () => {
  test('a session carrying subtasks says so, and counts as one row', async () => {
    render(
      <MemoryRouter initialEntries={['/activity/sessions']}>
        <ProjectProvider>
          <SessionsPage />
        </ProjectProvider>
      </MemoryRouter>,
    );

    // Two subagent runs, one row: the whole point of the roll-up.
    await screen.findByText('1 session');
    expect(await screen.findByText('2 subtasks')).toBeVisible();
  });

  test('a subtask whose parent is gone is marked rather than hidden', async () => {
    sessionsFixture = [
      session({
        sessionId: 'agent-orphan',
        title: 'a pruned parent',
        agent: 'explore',
        parentSessionId: 'session-long-gone',
      }),
    ];

    render(
      <MemoryRouter initialEntries={['/activity/sessions']}>
        <ProjectProvider>
          <SessionsPage />
        </ProjectProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText('Subtask · parent pruned')).toBeVisible();
  });
});

describe('subagent runs in the detail panel', () => {
  test('usage splits the main thread from what the subagents spent', async () => {
    renderPanel(parentWithSubtasks());

    expect(await screen.findByText(/Main thread 130 · \$0.85/)).toBeVisible();
    expect(screen.getByText(/Subtasks 270 · \$6.00/)).toBeVisible();
  });

  test('opening a subtask swaps the panel and offers a way back', async () => {
    renderPanel(parentWithSubtasks());

    fireEvent.click(await screen.findByRole('button', { name: /前端代码质量检查/ }));

    // The child's own transcript, with a breadcrumb back to its parent.
    await waitFor(() => expect(screen.getByText('check the frontend')).toBeInTheDocument());
    expect(
      screen.getByRole('button', { name: /Review 两个修复提交/ }),
    ).toBeVisible();

    // A subagent run has no context of its own to resume or convert into
    // another engine, so those actions are gone.
    expect(screen.queryByRole('button', { name: /Continue in terminal/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Delete/i })).toBeNull();
  });

  test('going back returns to the parent session', async () => {
    renderPanel(parentWithSubtasks());

    fireEvent.click(await screen.findByRole('button', { name: /前端代码质量检查/ }));
    await waitFor(() => expect(screen.getByText('check the frontend')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /Review 两个修复提交/ }));

    await waitFor(() =>
      expect(screen.getByText('review the two fixes')).toBeInTheDocument(),
    );
    expect(screen.getByText('Subtasks (2)')).toBeVisible();
  });
});
