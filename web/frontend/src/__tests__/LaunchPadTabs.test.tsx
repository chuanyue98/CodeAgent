import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import LaunchPad from '../components/LaunchPad';
import { ProjectProvider } from '../context/ProjectContext';

// The real one opens a WebSocket and an xterm instance. What matters here is
// that it stays mounted while its tab is in the background -- unmounting would
// close its socket, and the PTY endpoint spawns a process per connection.
const { mounted, unmounted } = vi.hoisted(() => ({
  mounted: [] as string[],
  unmounted: [] as string[],
}));

vi.mock('../components/BrowserTerminal', async () => {
  const { useEffect } = await import('react');
  const MockTerminal = ({ engine, sessionId }: { engine: string; sessionId?: string }) => {
    const key = `${engine}:${sessionId ?? 'new'}`;
    useEffect(() => {
      mounted.push(key);
      return () => {
        unmounted.push(key);
      };
    }, [key]);
    return <div data-testid={`term-${key}`}>terminal {key}</div>;
  };
  return { default: MockTerminal };
});

const SIDEBAR_SESSIONS = [
  {
    sessionId: 'ses_abc',
    target: 'opencode',
    projectPath: '/workspace/proj',
    title: '\u4fee\u590d\u767b\u5f55',
    lastActivity: '2026-08-27T10:00:00Z',
    inputTokens: 0,
    outputTokens: 0,
    cacheCreationTokens: 0,
    cacheReadTokens: 0,
    cost: 0,
    modelsUsed: [],
    modelBreakdowns: [],
  },
];

function jsonResponse(data: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    text: async () => JSON.stringify(data),
    json: async () => data,
  });
}

beforeEach(() => {
  mounted.length = 0;
  unmounted.length = 0;
  // The sidebar remembers being collapsed, so one test could otherwise hide
  // the session list from every test after it.
  localStorage.clear();
  globalThis.fetch = vi.fn().mockImplementation((url: string) => {
    if (url.includes('/api/pty/status')) return jsonResponse({ available: true, reason: null });
    if (url.includes('/api/projects')) {
      return jsonResponse([{ path: '/workspace/proj', group: 'codeagent', available: true }]);
    }
    if (url.includes('/api/config')) return jsonResponse({});
    if (url.includes('/api/groups')) return jsonResponse({});
    if (url.includes('/api/analytics/sessions')) {
      return jsonResponse({ sessions: SIDEBAR_SESSIONS, nextCursor: null });
    }
    return jsonResponse({});
  });
});

function renderLaunchPad(initialEntry = '/agent/terminal') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <ProjectProvider>
        <LaunchPad />
      </ProjectProvider>
    </MemoryRouter>,
  );
}

async function openEngine(name: string) {
  fireEvent.click(await launchCard(name));
}

/** Each engine card is itself the launch button. */
function launchCard(name: string) {
  return screen.findByRole('button', { name: new RegExp(`open terminal · ${name}`, 'i') });
}

describe('LaunchPad terminal tabs', () => {
  test('opening a second engine keeps the first terminal mounted', async () => {
    renderLaunchPad();
    await openEngine('Claude');
    await screen.findByTestId('term-claude:new');

    fireEvent.click(screen.getByLabelText(/new terminal/i));
    await openEngine('Codex');
    await screen.findByTestId('term-codex:new');

    // Both terminals are in the DOM; the background one was never torn down.
    expect(screen.getByTestId('term-claude:new')).toBeTruthy();
    expect(unmounted).toEqual([]);
    expect(screen.getAllByRole('tab')).toHaveLength(2);
  });

  test('the inactive tab is hidden rather than removed', async () => {
    renderLaunchPad();
    await openEngine('Claude');
    fireEvent.click(screen.getByLabelText(/new terminal/i));
    await openEngine('Codex');

    const claudePane = screen.getByTestId('term-claude:new').parentElement;
    const codexPane = screen.getByTestId('term-codex:new').parentElement;
    expect(claudePane?.className).toContain('hidden');
    expect(codexPane?.className).not.toContain('hidden');

    fireEvent.click(screen.getAllByRole('tab')[0]);
    await waitFor(() => {
      expect(screen.getByTestId('term-claude:new').parentElement?.className).not.toContain('hidden');
    });
  });

  test('closing the active tab lands on a neighbour, not the launcher', async () => {
    renderLaunchPad();
    await openEngine('Claude');
    fireEvent.click(screen.getByLabelText(/new terminal/i));
    await openEngine('Codex');

    const closeButtons = screen.getAllByLabelText(/close terminal/i);
    fireEvent.click(closeButtons[1]);

    await waitFor(() => expect(screen.getAllByRole('tab')).toHaveLength(1));
    expect(screen.queryByTestId('term-codex:new')).toBeNull();
    expect(screen.getByTestId('term-claude:new').parentElement?.className).not.toContain('hidden');
  });

  test('an unregistered directory can be typed in and launched', async () => {
    // On a fresh install nothing is registered. As a <select> that left the
    // picker empty and every launch button disabled -- the page was a dead
    // end for exactly the person meeting it first.
    renderLaunchPad();
    const field = await screen.findByLabelText(/workspace/i);
    fireEvent.change(field, { target: { value: '/somewhere/brand-new' } });

    const launch = (await launchCard('Claude')) as HTMLButtonElement;
    expect(launch.disabled).toBe(false);
    fireEvent.click(launch);

    await screen.findByTestId('term-claude:new');
  });

  test('a resume deep link opens as its own tab', async () => {
    renderLaunchPad('/agent/terminal?engine=opencode&cwd=/workspace/proj&session=ses_abc');
    await screen.findByTestId('term-opencode:ses_abc');
    expect(screen.getAllByRole('tab')).toHaveLength(1);
  });

  test('picking a session from the sidebar resumes it in a terminal', async () => {
    renderLaunchPad();
    fireEvent.click(await screen.findByTitle('修复登录'));
    await screen.findByTestId('term-opencode:ses_abc');
  });

  test('the sidebar is there before any terminal is open', async () => {
    renderLaunchPad();
    // The launcher used to be the whole screen until you opened a terminal,
    // which is why there was no way to reach a session from here.
    expect(await screen.findByTitle('修复登录')).toBeTruthy();
    expect(screen.queryAllByRole('tab')).toHaveLength(0);
  });

  test('the session list collapses to a rail, and stays collapsed next time', async () => {
    const first = renderLaunchPad();
    await screen.findByTitle('修复登录');

    fireEvent.click(screen.getByLabelText(/collapse the session list/i));
    expect(screen.queryByTitle('修复登录')).toBeNull();
    // The rail keeps the way back: collapsing must not hide its own control.
    expect(screen.getByLabelText(/show the session list/i)).toBeTruthy();

    first.unmount();
    renderLaunchPad();
    expect(await screen.findByLabelText(/show the session list/i)).toBeTruthy();
  });

  test('resuming a session that already has a tab focuses it instead of forking a second PTY', async () => {
    renderLaunchPad();
    fireEvent.click(await screen.findByTitle('修复登录'));
    await screen.findByTestId('term-opencode:ses_abc');

    fireEvent.click(screen.getByLabelText(/new terminal/i));
    fireEvent.click(screen.getByTitle('修复登录'));

    await waitFor(() => expect(screen.getAllByRole('tab')).toHaveLength(1));
    expect(screen.getAllByTestId('term-opencode:ses_abc')).toHaveLength(1);
  });
});
