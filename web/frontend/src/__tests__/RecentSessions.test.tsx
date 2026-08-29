import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import RecentSessions from '../components/RecentSessions';
import type { SessionUsage } from '../api/analytics';
import { jsonResponse, session as baseSession } from './factories';

/** Recent-session rows are shown by recency and title, so both are fixed here. */
function session(overrides: Partial<SessionUsage> = {}): SessionUsage {
  return baseSession({
    cost: 0.1,
    lastActivity: new Date().toISOString(),
    title: 'Refactor the launcher',
    ...overrides,
  });
}

/** Answers /api/analytics/sessions differently depending on ?project=. */
function mockPages(byProject: Record<string, SessionUsage[]>, anywhere: SessionUsage[] = []) {
  const calls: string[] = [];
  globalThis.fetch = vi.fn().mockImplementation((url: string) => {
    calls.push(url);
    const project = new URL(url, 'http://test').searchParams.get('project');
    const sessions = project === null ? anywhere : (byProject[project] ?? []);
    return jsonResponse({ sessions, nextCursor: null });
  }) as typeof fetch;
  return calls;
}

const originalFetch = globalThis.fetch;

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  globalThis.fetch = originalFetch;
});

test('renders nothing at all until a workspace is chosen', () => {
  const calls = mockPages({});
  const { container } = render(<RecentSessions workspace="" onOpen={() => {}} />);

  expect(container).toBeEmptyDOMElement();
  expect(calls).toEqual([]);
});

test('lists the sessions of the workspace it was pointed at', async () => {
  mockPages({ '/workspace/project-a': [session()] });
  render(<RecentSessions workspace="/workspace/project-a" onOpen={() => {}} />);

  expect(await screen.findByText('Refactor the launcher')).toBeInTheDocument();
  expect(screen.getByText('Recent in this workspace')).toBeInTheDocument();
});

test('falls back to work from anywhere rather than showing a blank half-screen', async () => {
  // The case this exists for: a workspace opened for the first time. An empty
  // state here puts the launcher back to the emptiness it was built to fill.
  const calls = mockPages(
    { '/workspace/fresh': [] },
    [session({ sessionId: 'elsewhere', projectPath: '/workspace/other', title: 'Older work' })],
  );
  render(<RecentSessions workspace="/workspace/fresh" onOpen={() => {}} />);

  expect(await screen.findByText('Older work')).toBeInTheDocument();
  expect(screen.getByText('Recent in other workspaces')).toBeInTheDocument();
  // Which project a row belongs to only earns its space once the list stops
  // being about one project.
  expect(screen.getByText('other')).toBeInTheDocument();
  expect(calls.some(url => !url.includes('project='))).toBe(true);
});

test('the workspace name stays out of the way while the list is scoped', async () => {
  mockPages({ '/workspace/project-a': [session()] });
  render(<RecentSessions workspace="/workspace/project-a" onOpen={() => {}} />);

  await screen.findByText('Refactor the launcher');
  expect(screen.queryByText('project-a')).not.toBeInTheDocument();
});

test('opening a row hands back the engine, project and session', async () => {
  mockPages({ '/workspace/project-a': [session({ target: 'codex' })] });
  const onOpen = vi.fn();
  render(<RecentSessions workspace="/workspace/project-a" onOpen={onOpen} />);

  fireEvent.click(await screen.findByRole('button', { name: 'Resume Refactor the launcher' }));

  expect(onOpen).toHaveBeenCalledWith('codex', '/workspace/project-a', 'session-a');
});

test('an untitled session is still openable', async () => {
  mockPages({ '/workspace/project-a': [session({ title: undefined })] });
  render(<RecentSessions workspace="/workspace/project-a" onOpen={() => {}} />);

  expect(await screen.findByRole('button', { name: 'Resume (untitled)' })).toBeInTheDocument();
});

test('a slow answer for the previous workspace never lands on the new one', async () => {
  const resolvers: Array<(sessions: SessionUsage[]) => void> = [];
  globalThis.fetch = vi.fn().mockImplementation(
    () =>
      new Promise(resolve => {
        resolvers.push(sessions => resolve(jsonResponse({ sessions, nextCursor: null }) as never));
      }),
  ) as typeof fetch;

  const { rerender } = render(<RecentSessions workspace="/workspace/slow" onOpen={() => {}} />);
  rerender(<RecentSessions workspace="/workspace/fast" onOpen={() => {}} />);

  // Second request answers first, then the abandoned one arrives.
  resolvers[1]?.([session({ sessionId: 'fast', title: 'The current workspace' })]);
  await screen.findByText('The current workspace');
  resolvers[0]?.([session({ sessionId: 'slow', title: 'The abandoned workspace' })]);

  await waitFor(() =>
    expect(screen.queryByText('The abandoned workspace')).not.toBeInTheDocument(),
  );
  expect(screen.getByText('The current workspace')).toBeInTheDocument();
});

test('a failed lookup says so instead of pretending the workspace is empty', async () => {
  globalThis.fetch = vi.fn().mockRejectedValue(new Error('history unreadable')) as typeof fetch;
  render(<RecentSessions workspace="/workspace/project-a" onOpen={() => {}} />);

  expect(await screen.findByText('history unreadable')).toBeInTheDocument();
});

test('an empty result everywhere gets an empty state, not a spinner forever', async () => {
  mockPages({ '/workspace/project-a': [] }, []);
  render(<RecentSessions workspace="/workspace/project-a" onOpen={() => {}} />);

  expect(
    await screen.findByText('No sessions in this workspace yet — open one above.'),
  ).toBeInTheDocument();
});
