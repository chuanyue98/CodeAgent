import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
  return render(
    <SessionDetailPanel
      engine="claude"
      sessionId="session-a"
      projectPath="/workspace/project-a"
      onClose={() => {}}
    />,
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
