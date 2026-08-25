import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import SessionsPage from '../components/SessionsPage';
import { ProjectProvider } from '../context/ProjectContext';
import type { SessionUsage } from '../api/analytics';

function session(sessionId: string): SessionUsage {
  return {
    sessionId,
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
  };
}

function jsonResponse(data: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    text: async () => JSON.stringify(data),
    json: async () => data,
  });
}

let sessionUrls: string[];

/** Serves page 1 with a cursor, page 2 without. */
function mockPages() {
  sessionUrls = [];
  globalThis.fetch = vi.fn().mockImplementation((url: string) => {
    if (url.includes('/api/config')) return jsonResponse({});
    if (url.includes('/api/projects')) return jsonResponse([]);
    if (url.includes('/api/groups')) return jsonResponse({});
    if (url.includes('/api/analytics/sessions')) {
      sessionUrls.push(url);
      const isSecondPage = url.includes('cursor=');
      return jsonResponse({
        sessions: isSecondPage ? [session('older-1')] : [session('newest-1')],
        nextCursor: isSecondPage ? null : 'CURSOR-1',
        total: 2,
      });
    }
    return Promise.reject(new Error(`Unhandled fetch to ${url}`));
  }) as typeof fetch;
}

const originalFetch = globalThis.fetch;

beforeEach(() => {
  mockPages();
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

function renderSessions(entry = '/activity/sessions') {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <ProjectProvider>
        <SessionsPage />
      </ProjectProvider>
    </MemoryRouter>,
  );
}

describe('SessionsPage paging', () => {
  test('asks for a page, not a hard-coded 500', async () => {
    renderSessions();

    await waitFor(() => expect(sessionUrls.length).toBeGreaterThan(0));
    expect(sessionUrls[0]).toContain('limit=100');
    expect(sessionUrls[0]).not.toContain('limit=500');
  });

  test('load more appends the next page and then disappears', async () => {
    renderSessions();

    const loadMore = await screen.findByRole('button', { name: 'Load more' });
    expect(screen.getByText(/Showing 1 of 2 matching sessions/)).toBeInTheDocument();

    fireEvent.click(loadMore);

    // The second request carries the cursor the first response handed back.
    await waitFor(() => expect(sessionUrls.length).toBe(2));
    expect(sessionUrls[1]).toContain('cursor=CURSOR-1');

    // Both pages are on screen, and there is nothing left to fetch.
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument(),
    );
    expect(screen.getByText('2 sessions')).toBeInTheDocument();
  });

  test('the query goes to the server rather than filtering a partial window', async () => {
    renderSessions('/activity/sessions?q=refactor');

    await waitFor(() => expect(sessionUrls.length).toBeGreaterThan(0));
    expect(sessionUrls[0]).toContain('search=refactor');
  });
});
