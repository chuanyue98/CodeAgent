import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import SessionDetailPanel from '../components/SessionDetailPanel';

function message(index: number) {
  return {
    role: index % 2 === 0 ? 'user' : 'assistant',
    content: `message-${index}`,
    timestamp: `2026-07-20T10:${String(index % 60).padStart(2, '0')}:00Z`,
    model: 'claude-opus',
    tool_calls: [],
  };
}

function mockTranscript(count: number) {
  const detail = {
    session_id: 'session-a',
    engine: 'claude',
    project_path: '/workspace/project-a',
    title: 'Long session',
    messages: Array.from({ length: count }, (_, i) => message(i)),
  };
  globalThis.fetch = vi.fn().mockImplementation((url: string) => {
    if (url.includes('/api/history/')) {
      const text = JSON.stringify(detail);
      return Promise.resolve({ ok: true, status: 200, text: async () => text, json: async () => detail });
    }
    return Promise.reject(new Error(`Unhandled fetch to ${url}`));
  }) as typeof fetch;
}

function renderPanel() {
  // The Continue button navigates to the terminal page, so the panel needs a
  // router in context.
  return render(
    <MemoryRouter>
      <SessionDetailPanel
        engine="claude"
        sessionId="session-a"
        projectPath="/workspace/project-a"
        onClose={() => {}}
      />
    </MemoryRouter>,
  );
}

const originalFetch = globalThis.fetch;

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe('SessionDetailPanel transcript window', () => {
  test('a long transcript opens on the latest messages, not the first', async () => {
    mockTranscript(120);
    renderPanel();

    // The end of the conversation is what you opened it to read.
    expect(await screen.findByText('message-119')).toBeInTheDocument();
    expect(screen.queryByText('message-0')).not.toBeInTheDocument();
  });

  test('earlier messages load on request', async () => {
    mockTranscript(120);
    renderPanel();

    const loadEarlier = await screen.findByRole('button', {
      name: /Load earlier — showing the last 50 of 120/,
    });

    fireEvent.click(loadEarlier);

    await waitFor(() => expect(screen.getByText('message-69')).toBeInTheDocument());
    expect(
      screen.getByRole('button', { name: /showing the last 100 of 120/ }),
    ).toBeInTheDocument();
  });

  test('a short transcript renders whole, with no paging control', async () => {
    mockTranscript(5);
    renderPanel();

    expect(await screen.findByText('message-0')).toBeInTheDocument();
    expect(screen.getByText('message-4')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Load earlier/ })).not.toBeInTheDocument();
  });

  test('the jump controls are offered once there is a transcript', async () => {
    mockTranscript(120);
    renderPanel();

    expect(await screen.findByRole('button', { name: 'Jump to the latest' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Jump to the start' })).toBeInTheDocument();
  });
});


describe('SessionDetailPanel resume', () => {
  test('Continue asks the server, then opens the browser terminal', async () => {
    const detail = {
      session_id: 'session-a',
      engine: 'claude',
      project_path: '/workspace/project-a',
      title: 'A session',
      messages: [message(0)],
    };
    const calls: string[] = [];
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      calls.push(url);
      if (url.includes('/continue')) {
        const target = {
          status: 'ready',
          engine: 'claude',
          sessionId: 'session-a',
          project: '/workspace/project-a',
        };
        return Promise.resolve({
          ok: true,
          status: 200,
          text: async () => JSON.stringify(target),
          json: async () => target,
        });
      }
      if (url.includes('/api/history/')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: async () => JSON.stringify(detail),
          json: async () => detail,
        });
      }
      return Promise.reject(new Error(`Unhandled fetch to ${url}`));
    }) as typeof fetch;

    let location = '';
    function LocationProbe() {
      const current = useLocation();
      location = `${current.pathname}${current.search}`;
      return null;
    }

    render(
      <MemoryRouter initialEntries={['/activity/sessions']}>
        <LocationProbe />
        <SessionDetailPanel
          engine="claude"
          sessionId="session-a"
          projectPath="/workspace/project-a"
          onClose={() => {}}
        />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole('button', { name: /Continue in terminal/ }));

    await waitFor(() =>
      expect(calls.some(url => url.includes('/continue'))).toBe(true),
    );

    // Lands on the in-page terminal, not on anything the server opened for
    // itself.
    await waitFor(() => expect(location).toContain('/agent/terminal'));
    expect(location).toContain('engine=claude');
    expect(location).toContain('session=session-a');
    expect(location).toContain(encodeURIComponent('/workspace/project-a'));
  });
});

describe('SessionDetailPanel progress', () => {
  test('summarizes turns, duration and the last actions above the transcript', async () => {
    const detail = {
      session_id: 'session-a',
      engine: 'claude',
      project_path: '/workspace/project-a',
      title: 'A session',
      messages: [
        { ...message(0), timestamp: '2026-07-20T10:00:00Z' },
        {
          ...message(1),
          timestamp: '2026-07-20T11:23:00Z',
          tool_calls: [
            { name: 'Edit', args_preview: '{"file_path": "core/web/routers/history.py"}', result_preview: '' },
            { name: 'Bash', args_preview: '{"command": "pytest -q"}', result_preview: '' },
          ],
        },
      ],
    };
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/history/')) {
        const text = JSON.stringify(detail);
        return Promise.resolve({ ok: true, status: 200, text: async () => text, json: async () => detail });
      }
      return Promise.reject(new Error(`Unhandled fetch to ${url}`));
    }) as typeof fetch;

    renderPanel();

    const strip = await screen.findByTestId('session-progress');
    expect(strip).toHaveTextContent('1 turns');
    expect(strip).toHaveTextContent('1h23m');
    expect(strip).toHaveTextContent('1 files');
    // Newest action first, and a file operand is shown as the path rather
    // than the raw argument JSON.
    expect(strip).toHaveTextContent('Bash');
    expect(strip).toHaveTextContent('core/web/routers/history.py');
  });

  test('renders nothing when there is no transcript to summarize', async () => {
    const detail = {
      session_id: 'session-a',
      engine: 'claude',
      project_path: '/workspace/project-a',
      title: 'A session',
      messages: [],
    };
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/history/')) {
        const text = JSON.stringify(detail);
        return Promise.resolve({ ok: true, status: 200, text: async () => text, json: async () => detail });
      }
      return Promise.reject(new Error(`Unhandled fetch to ${url}`));
    }) as typeof fetch;

    renderPanel();

    await screen.findByText('This session has no messages.');
    expect(screen.queryByTestId('session-progress')).not.toBeInTheDocument();
  });
});
