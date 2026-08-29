import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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

/**
 * Scoped to the sidebar on purpose: the launcher's recent-session cards carry
 * the same titles, so an unscoped query is a race between the two lists.
 */
async function sidebarSession(title: string) {
  const sidebar = await screen.findByRole('complementary');
  return within(sidebar).findByTitle(title);
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

  test('the launcher opens in the workspace the header selected', async () => {
    // This page carried its own workspace field until the header switcher
    // took over the "any existing directory" case, so one screen had two
    // controls writing one value. What is left has to still show which
    // directory a terminal will open in -- the header shows only its name.
    renderLaunchPad();
    expect(await screen.findByText('/workspace/proj')).toBeTruthy();
    expect(screen.queryByLabelText(/workspace/i)).toBeNull();

    const launch = (await launchCard('Claude')) as HTMLButtonElement;
    expect(launch.disabled).toBe(false);
    fireEvent.click(launch);

    await screen.findByTestId('term-claude:new');
  });

  test('with no workspace at all the cards say why they are dead', async () => {
    // Five tiles at half opacity used to be the entire explanation.
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/pty/status')) return jsonResponse({ available: true, reason: null });
      if (url.includes('/api/projects')) return jsonResponse([]);
      if (url.includes('/api/analytics/sessions')) {
        return jsonResponse({ sessions: [], nextCursor: null });
      }
      return jsonResponse({});
    });
    renderLaunchPad();

    const launch = (await launchCard('Claude')) as HTMLButtonElement;
    expect(launch.disabled).toBe(true);
    expect(screen.getByRole('status').textContent).toMatch(/pick a workspace/i);
  });

  test('a resume deep link opens as its own tab', async () => {
    renderLaunchPad('/agent/terminal?engine=opencode&cwd=/workspace/proj&session=ses_abc');
    await screen.findByTestId('term-opencode:ses_abc');
    expect(screen.getAllByRole('tab')).toHaveLength(1);
  });

  test('picking a session from the sidebar resumes it in a terminal', async () => {
    renderLaunchPad();
    fireEvent.click(await sidebarSession('修复登录'));
    await screen.findByTestId('term-opencode:ses_abc');
  });

  test('the launcher offers recent work in the current workspace', async () => {
    // The launcher used to be an engine picker on a mostly empty screen, with
    // resuming reachable only through the 256px sidebar.
    renderLaunchPad();
    fireEvent.click(await screen.findByRole('button', { name: /resume 修复登录/i }));
    await screen.findByTestId('term-opencode:ses_abc');
  });

  test('an unworked workspace falls back to recent work anywhere', async () => {
    // Scoping the list to the current workspace is the point of it, but
    // answering "nothing here yet" leaves the launcher staring at the blank
    // half of the screen this block exists to fill.
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/pty/status')) return jsonResponse({ available: true, reason: null });
      if (url.includes('/api/projects')) {
        return jsonResponse([{ path: '/workspace/fresh', group: 'codeagent', available: true }]);
      }
      if (url.includes('/api/analytics/sessions')) {
        // Scoped to /workspace/fresh: nothing. Unscoped: the session below,
        // which lives in a different project.
        return jsonResponse({
          sessions: url.includes('project=') ? [] : SIDEBAR_SESSIONS,
          nextCursor: null,
        });
      }
      return jsonResponse({});
    });
    renderLaunchPad();

    const card = await screen.findByRole('button', { name: /resume 修复登录/i });
    // Whose project it is only matters once the list stops being about one.
    expect(card.textContent).toContain('proj');
    fireEvent.click(card);
    await screen.findByTestId('term-opencode:ses_abc');
  });

  test('the sidebar is there before any terminal is open', async () => {
    renderLaunchPad();
    // The launcher used to be the whole screen until you opened a terminal,
    // which is why there was no way to reach a session from here.
    expect(await sidebarSession('修复登录')).toBeTruthy();
    expect(screen.queryAllByRole('tab')).toHaveLength(0);
  });

  test('the session list collapses to a rail, and stays collapsed next time', async () => {
    const first = renderLaunchPad();
    await sidebarSession('修复登录');

    fireEvent.click(screen.getByLabelText(/collapse the session list/i));
    expect(within(screen.getByRole('complementary')).queryByTitle('修复登录')).toBeNull();
    // The rail keeps the way back: collapsing must not hide its own control.
    expect(screen.getByLabelText(/show the session list/i)).toBeTruthy();

    first.unmount();
    renderLaunchPad();
    expect(await screen.findByLabelText(/show the session list/i)).toBeTruthy();
  });

  test('resuming a session that already has a tab focuses it instead of forking a second PTY', async () => {
    renderLaunchPad();
    fireEvent.click(await sidebarSession('修复登录'));
    await screen.findByTestId('term-opencode:ses_abc');

    fireEvent.click(screen.getByLabelText(/new terminal/i));
    fireEvent.click(await sidebarSession('修复登录'));

    await waitFor(() => expect(screen.getAllByRole('tab')).toHaveLength(1));
    expect(screen.getAllByTestId('term-opencode:ses_abc')).toHaveLength(1);
  });
});
