import React, { type ReactNode } from 'react';
import { render, screen, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import GlobalTerminalDrawer from '../components/GlobalTerminalDrawer';
import type { BrowserTerminalProps } from '../components/BrowserTerminal';
import { TerminalProvider, useTerminal } from '../context/TerminalContext';

// Mock BrowserTerminal to avoid testing xterm
vi.mock('../components/BrowserTerminal', () => ({
  default: ({ engine, cwd }: BrowserTerminalProps) => <div data-testid={`mock-terminal-${engine}`}>{cwd}</div>
}));

const TestWrapper = ({ children, addTab }: { children: ReactNode; addTab?: boolean }) => {
  const ctx = useTerminal();
  React.useEffect(() => {
    if (addTab && ctx.tabs.length === 0) {
      ctx.openTab('test-engine', '/test');
    }
  }, []);

  return <>{children}</>;
};

describe('GlobalTerminalDrawer', () => {
  vi.mock('../context/TerminalContext', async (importOriginal) => {
    const mod = await importOriginal<typeof import('../context/TerminalContext')>();
    return mod;
  });

  beforeEach(() => {
    localStorage.clear();
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

    // Initial state after opening a tab is drawerOpen=true (from openTab behavior)
    // Let's close it first
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
});
