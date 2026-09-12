import React, { type ReactNode } from 'react';
import { render, screen, act, fireEvent } from '@testing-library/react';
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
  }, []);

  return <>{children}</>;
};

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
});

