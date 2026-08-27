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
  globalThis.fetch = vi.fn().mockImplementation((url: string) => {
    if (url.includes('/api/pty/status')) return jsonResponse({ available: true, reason: null });
    if (url.includes('/api/projects')) {
      return jsonResponse([{ path: '/workspace/proj', group: 'codeagent', available: true }]);
    }
    if (url.includes('/api/config')) return jsonResponse({});
    if (url.includes('/api/groups')) return jsonResponse({});
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
  const cards = await screen.findAllByRole('button', { name: /open terminal/i });
  const card = cards.find(button => button.closest('.glass-card')?.textContent?.includes(name));
  if (!card) throw new Error(`No launch button for ${name}`);
  fireEvent.click(card);
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

  test('a resume deep link opens as its own tab', async () => {
    renderLaunchPad('/agent/terminal?engine=opencode&cwd=/workspace/proj&session=ses_abc');
    await screen.findByTestId('term-opencode:ses_abc');
    expect(screen.getAllByRole('tab')).toHaveLength(1);
  });
});
