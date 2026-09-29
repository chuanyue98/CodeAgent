import React, { type ReactNode } from 'react';
import { render as rtlRender, screen, act, fireEvent } from '@testing-library/react';
import { MemoryRouter, useNavigate } from 'react-router';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import GlobalTerminalDrawer from '../components/GlobalTerminalDrawer';
import type { BrowserTerminalProps } from '../components/BrowserTerminal';
import { TerminalProvider, useTerminal } from '../context/TerminalContext';
import { convertAndLaunchSession } from '../api/audit';

// Mock BrowserTerminal to avoid testing xterm
vi.mock('../components/BrowserTerminal', () => ({
  default: ({ engine, cwd }: BrowserTerminalProps) => <div data-testid={`mock-terminal-${engine}`}>{cwd}</div>
}));

vi.mock('../api/audit', () => ({
  convertAndLaunchSession: vi.fn().mockResolvedValue({
    status: 'ready',
    engine: 'codex',
    project: '/test',
    sessionId: 'new-codex-session',
    newSessionId: 'new-codex-session',
    targetEngine: 'codex',
  }),
}));

vi.mock('../context/TerminalContext', async (importOriginal) => {
  const mod = await importOriginal<typeof import('../context/TerminalContext')>();
  return mod;
});

const TestWrapper = ({
  children,
  addTab,
  engine = 'test-engine',
}: {
  children: ReactNode;
  addTab?: boolean;
  engine?: string;
}) => {
  const ctx = useTerminal();
  React.useEffect(() => {
    if (addTab && ctx.tabs.length === 0) {
      ctx.openTab(engine, '/test');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <>{children}</>;
};

// Off the terminal page, so the drawer is a drawer rather than docked.
const render = (ui: React.ReactElement) =>
  rtlRender(<MemoryRouter initialEntries={['/activity/sessions']}>{ui}</MemoryRouter>);

describe('GlobalTerminalDrawer', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('returns null when no tabs', () => {
    const { container } = render(
      <TerminalProvider>
        <GlobalTerminalDrawer />
      </TerminalProvider>
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders dock bar when minimized with tabs', () => {
    render(
      <TerminalProvider>
        <TestWrapper addTab>
          <GlobalTerminalDrawer />
        </TestWrapper>
      </TerminalProvider>
    );

    const closeBtn = screen.getByTitle('Minimize Drawer');
    act(() => {
      closeBtn.click();
    });

    expect(screen.getByTestId('dock-bar')).toBeInTheDocument();
    expect(screen.getByText(/1.*launch.tabs|Tabs/i)).toBeInTheDocument();
  });

  it('renders expanded drawer when open', () => {
    render(
      <TerminalProvider>
        <TestWrapper addTab>
          <GlobalTerminalDrawer />
        </TestWrapper>
      </TerminalProvider>
    );

    expect(screen.getByTestId('drawer-expanded')).toBeInTheDocument();
    expect(screen.getByTestId('mock-terminal-test-engine')).toBeInTheDocument();
  });

  it('can toggle maximize', () => {
    render(
      <TerminalProvider>
        <TestWrapper addTab>
          <GlobalTerminalDrawer />
        </TestWrapper>
      </TerminalProvider>
    );

    const drawer = screen.getByTestId('drawer-expanded');
    expect(drawer).toHaveClass('h-[60vh]');
    
    act(() => {
      screen.getByTitle('Maximize').click();
    });
    
    expect(drawer).toHaveClass('top-0');
  });

  it('renders handoff button when active tab is an agent engine and can toggle dropdown', () => {
    render(
      <TerminalProvider>
        <TestWrapper addTab engine="claude">
          <GlobalTerminalDrawer />
        </TestWrapper>
      </TerminalProvider>
    );

    const handoffBtn = screen.getByTestId('handoff-button');
    expect(handoffBtn).toBeInTheDocument();
    expect(screen.queryByTestId('handoff-menu')).toBeNull();

    // Open menu
    fireEvent.click(handoffBtn);
    expect(screen.getByTestId('handoff-menu')).toBeInTheDocument();

    // Toggle menu off
    fireEvent.click(handoffBtn);
    expect(screen.queryByTestId('handoff-menu')).toBeNull();
  });

  it('does not render handoff button when active tab is shell engine', () => {
    render(
      <TerminalProvider>
        <TestWrapper addTab engine="shell">
          <GlobalTerminalDrawer />
        </TestWrapper>
      </TerminalProvider>
    );

    expect(screen.queryByTestId('handoff-button')).toBeNull();
  });

  it('clicking outside closes the handoff dropdown menu', () => {
    render(
      <TerminalProvider>
        <TestWrapper addTab engine="claude">
          <div data-testid="outside-area">Outside</div>
          <GlobalTerminalDrawer />
        </TestWrapper>
      </TerminalProvider>
    );

    const handoffBtn = screen.getByTestId('handoff-button');
    fireEvent.click(handoffBtn);
    expect(screen.getByTestId('handoff-menu')).toBeInTheDocument();

    // Click outside
    fireEvent.mouseDown(screen.getByTestId('outside-area'));
    expect(screen.queryByTestId('handoff-menu')).toBeNull();
  });

  it('clicking target engine calls convertAndLaunchSession', async () => {
    render(
      <TerminalProvider>
        <TestWrapper addTab engine="claude">
          <GlobalTerminalDrawer />
        </TestWrapper>
      </TerminalProvider>
    );

    fireEvent.click(screen.getByTestId('handoff-button'));
    const menu = screen.getByTestId('handoff-menu');
    expect(menu).toBeInTheDocument();

    // Click target 'Codex'
    const codexBtn = screen.getByRole('button', { name: /codex/i });
    await act(async () => {
      fireEvent.click(codexBtn);
    });

    expect(convertAndLaunchSession).toHaveBeenCalledWith({
      sourceEngine: 'claude',
      sessionId: undefined,
      targetEngine: 'codex',
      projectPath: '/test',
    });
  });

  it('can adjust font size via zoom controls', () => {
    render(
      <TerminalProvider>
        <TestWrapper addTab>
          <GlobalTerminalDrawer />
        </TestWrapper>
      </TerminalProvider>
    );

    fireEvent.click(screen.getByTestId('terminal-more-button'));
    const zoomInBtn = screen.getByTestId('terminal-zoom-in');
    const zoomOutBtn = screen.getByTestId('terminal-zoom-out');
    const fontBtn = screen.getByTestId('terminal-font-size-btn');

    expect(fontBtn).toHaveTextContent('13px');

    act(() => {
      zoomInBtn.click();
    });
    expect(fontBtn).toHaveTextContent('14px');

    act(() => {
      zoomOutBtn.click();
    });
    expect(fontBtn).toHaveTextContent('13px');

    // Zoom in twice then reset
    act(() => {
      zoomInBtn.click();
      zoomInBtn.click();
    });
    expect(fontBtn).toHaveTextContent('15px');

    act(() => {
      fontBtn.click();
    });
    expect(fontBtn).toHaveTextContent('13px');
  });

  it('can toggle copy on select and zen mode', () => {
    render(
      <TerminalProvider>
        <TestWrapper addTab>
          <GlobalTerminalDrawer />
        </TestWrapper>
      </TerminalProvider>
    );

    fireEvent.click(screen.getByTestId('terminal-more-button'));
    const copyToggle = screen.getByTestId('copy-on-select-toggle');
    expect(copyToggle).toBeInTheDocument();

    act(() => {
      copyToggle.click();
    });

    const zenToggle = screen.getByTestId('zen-mode-toggle');
    const drawer = screen.getByTestId('drawer-expanded');
    expect(drawer).not.toHaveClass('h-screen');

    act(() => {
      zenToggle.click();
    });
    expect(drawer).toHaveClass('h-screen');

    fireEvent.click(screen.getByTestId('terminal-more-button'));
    act(() => {
      screen.getByTestId('zen-mode-toggle').click();
    });
    expect(drawer).not.toHaveClass('h-screen');
  });

  it('goes to the dock bar when leaving the terminal page', () => {
    const Leave = () => {
      const navigate = useNavigate();
      return <button onClick={() => navigate('/settings/workspace')}>leave</button>;
    };
    rtlRender(
      <MemoryRouter initialEntries={['/agent/terminal']}>
        <TerminalProvider>
          <TestWrapper addTab>
            <Leave />
            <GlobalTerminalDrawer />
          </TestWrapper>
        </TerminalProvider>
      </MemoryRouter>
    );
    expect(screen.getByTestId('dock-bar')).toHaveClass('hidden');

    fireEvent.click(screen.getByText('leave'));
    expect(screen.getByTestId('dock-bar')).not.toHaveClass('hidden');
    expect(screen.getByTestId('drawer-expanded')).toHaveClass('invisible');
  });

  it('closing a tab stops its engine instead of leaving it running in tmux', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => '{"success":true}',
      json: async () => ({ success: true }),
    });
    globalThis.fetch = fetchMock as unknown as typeof fetch;
    render(
      <TerminalProvider>
        <TestWrapper addTab engine="claude">
          <GlobalTerminalDrawer />
        </TestWrapper>
      </TerminalProvider>
    );

    await act(async () => {
      fireEvent.click(screen.getByLabelText('Close terminal'));
    });

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/api/pty/close?');
    expect(String(url)).toContain('engine=claude');
    expect(String(url)).toMatch(/tab_key=\w+/);
    expect(init.method).toBe('POST');
  });
});

