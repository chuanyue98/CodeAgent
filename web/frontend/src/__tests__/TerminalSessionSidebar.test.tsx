import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import TerminalSessionSidebar from '../components/TerminalSessionSidebar';
import type { SessionUsage } from '../api/analytics';
import { jsonResponse, session as baseSession } from './factories';

const COLLAPSED_KEY = 'ca.terminalSidebar.collapsed';

/** The sidebar lists sessions by title and recency; token totals never show. */
function session(overrides: Partial<SessionUsage> = {}): SessionUsage {
  return baseSession({
    inputTokens: 0,
    outputTokens: 0,
    cost: 0,
    lastActivity: new Date().toISOString(),
    modelsUsed: [],
    title: 'Session A',
    ...overrides,
  });
}

/** Records every /api/analytics/sessions URL and answers each with one page. */
function mockPages(pages: Array<{ sessions: SessionUsage[]; nextCursor?: string | null }>) {
  const calls: string[] = [];
  let index = 0;
  globalThis.fetch = vi.fn().mockImplementation((url: string) => {
    calls.push(url);
    const page = pages[Math.min(index++, pages.length - 1)];
    return jsonResponse({ sessions: page.sessions, nextCursor: page.nextCursor ?? null });
  }) as typeof fetch;
  return calls;
}

function renderSidebar(props: Partial<React.ComponentProps<typeof TerminalSessionSidebar>> = {}) {
  return render(
    <TerminalSessionSidebar
      currentWorkspace="/workspace/project-a"
      launcherActive={false}
      onOpenSession={() => {}}
      onNewSession={() => {}}
      {...props}
    />,
  );
}

const originalFetch = globalThis.fetch;

beforeEach(() => {
  vi.restoreAllMocks();
  localStorage.removeItem(COLLAPSED_KEY);
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  localStorage.removeItem(COLLAPSED_KEY);
});

test('the workspace the launcher points at leads the list', async () => {
  mockPages([
    {
      sessions: [
        session({ sessionId: 'elsewhere', projectPath: '/workspace/other', title: 'Elsewhere' }),
        session({ sessionId: 'here', title: 'Here' }),
      ],
    },
  ]);
  renderSidebar();

  await screen.findByText('Here');
  const headers = screen.getAllByRole('button', { name: /project-a|other/ });
  expect(headers[0]).toHaveTextContent('project-a');
});

test('only the pointed-at workspace is expanded, so a handful of projects is not a wall', async () => {
  mockPages([
    {
      sessions: [
        session({ sessionId: 'here', title: 'Here' }),
        session({ sessionId: 'elsewhere', projectPath: '/workspace/other', title: 'Elsewhere' }),
      ],
    },
  ]);
  renderSidebar();

  expect(await screen.findByText('Here')).toBeInTheDocument();
  expect(screen.queryByText('Elsewhere')).not.toBeInTheDocument();
});

test('a closed group speaks for what it hides', async () => {
  mockPages([
    {
      sessions: [
        session({ sessionId: 'here' }),
        session({ sessionId: 'e1', projectPath: '/workspace/other' }),
        session({ sessionId: 'e2', projectPath: '/workspace/other' }),
      ],
    },
  ]);
  renderSidebar();

  const closed = await screen.findByRole('button', { name: /other/ });
  expect(closed).toHaveTextContent('2 ·');
});

test('clicking a group header opens it', async () => {
  mockPages([
    {
      sessions: [
        session({ sessionId: 'here' }),
        session({ sessionId: 'elsewhere', projectPath: '/workspace/other', title: 'Elsewhere' }),
      ],
    },
  ]);
  renderSidebar();

  fireEvent.click(await screen.findByRole('button', { name: /other/ }));

  expect(screen.getByText('Elsewhere')).toBeInTheDocument();
});

test('when the pointed-at workspace has nothing, the most recent work opens instead', async () => {
  // Otherwise the sidebar greets you as a list of folder names with no content.
  mockPages([
    { sessions: [session({ sessionId: 'elsewhere', projectPath: '/workspace/other', title: 'Elsewhere' })] },
  ]);
  renderSidebar();

  expect(await screen.findByText('Elsewhere')).toBeInTheDocument();
});

test('searching opens every group, wherever the match lives', async () => {
  const calls = mockPages([
    { sessions: [session({ sessionId: 'here', title: 'Here' })] },
    {
      sessions: [
        session({ sessionId: 'm1', title: 'Matched here' }),
        session({ sessionId: 'm2', projectPath: '/workspace/other', title: 'Matched elsewhere' }),
      ],
    },
  ]);
  vi.useFakeTimers();
  renderSidebar();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });

  fireEvent.change(screen.getByPlaceholderText('Search sessions'), {
    target: { value: 'matched' },
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(300);
  });
  vi.useRealTimers();

  // A search is a request to see what matched -- including in the workspaces
  // that stay collapsed when you are just browsing.
  expect(await screen.findByText('Matched elsewhere')).toBeInTheDocument();
  expect(screen.getByText('Matched here')).toBeInTheDocument();
  expect(calls.some(url => url.includes('search=matched'))).toBe(true);
});

test('opening a session hands back the engine, project and id', async () => {
  mockPages([{ sessions: [session({ target: 'opencode' })] }]);
  const onOpenSession = vi.fn();
  renderSidebar({ onOpenSession });

  fireEvent.click(await screen.findByText('Session A'));

  expect(onOpenSession).toHaveBeenCalledWith('opencode', '/workspace/project-a', 'session-a');
});

test('load more appends instead of replacing', async () => {
  mockPages([
    { sessions: [session({ sessionId: 'first', title: 'First' })], nextCursor: 'cursor-1' },
    { sessions: [session({ sessionId: 'second', title: 'Second' })], nextCursor: null },
  ]);
  renderSidebar();

  fireEvent.click(await screen.findByRole('button', { name: 'Load more' }));

  expect(await screen.findByText('Second')).toBeInTheDocument();
  expect(screen.getByText('First')).toBeInTheDocument();
});

test('collapsing keeps a rail of one dot per session, not two bare icons', async () => {
  mockPages([
    { sessions: [session({ sessionId: 'a', title: 'Alpha' }), session({ sessionId: 'b', title: 'Beta' })] },
  ]);
  renderSidebar();
  await screen.findByText('Alpha');

  fireEvent.click(screen.getByRole('button', { name: 'Collapse the session list' }));

  const rail = screen.getByRole('button', { name: 'Show the session list' }).closest('aside')!;
  expect(within(rail).getByRole('button', { name: 'Alpha' })).toBeInTheDocument();
  expect(within(rail).getByRole('button', { name: 'Beta' })).toBeInTheDocument();
});

test('a session is still openable from the collapsed rail', async () => {
  mockPages([{ sessions: [session({ target: 'codex', title: 'Alpha' })] }]);
  const onOpenSession = vi.fn();
  renderSidebar({ onOpenSession });
  await screen.findByText('Alpha');
  fireEvent.click(screen.getByRole('button', { name: 'Collapse the session list' }));

  fireEvent.click(screen.getByRole('button', { name: 'Alpha' }));

  expect(onOpenSession).toHaveBeenCalledWith('codex', '/workspace/project-a', 'session-a');
});

test('the collapsed choice survives a remount', async () => {
  mockPages([{ sessions: [session()] }]);
  const { unmount } = renderSidebar();
  await screen.findByText('Session A');
  fireEvent.click(screen.getByRole('button', { name: 'Collapse the session list' }));
  unmount();

  renderSidebar();

  expect(screen.getByRole('button', { name: 'Show the session list' })).toBeInTheDocument();
});

test('unreadable site data just means the sidebar opens', async () => {
  const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
    throw new Error('site data blocked');
  });
  mockPages([{ sessions: [session()] }]);

  renderSidebar();

  expect(screen.getByRole('button', { name: 'Collapse the session list' })).toBeInTheDocument();
  getItem.mockRestore();
});

test('a failed lookup says so instead of showing an empty list', async () => {
  globalThis.fetch = vi.fn().mockRejectedValue(new Error('history unreadable')) as typeof fetch;
  renderSidebar();

  expect(await screen.findByText('history unreadable')).toBeInTheDocument();
  expect(screen.queryByText('No sessions yet. Start one from the launcher.')).not.toBeInTheDocument();
});

test('no sessions at all gets the empty state', async () => {
  mockPages([{ sessions: [] }]);
  renderSidebar();

  await waitFor(() =>
    expect(screen.getByText('No sessions yet. Start one from the launcher.')).toBeInTheDocument(),
  );
});
