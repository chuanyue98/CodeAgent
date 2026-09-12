import { render, screen, act, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { TerminalProvider, useTerminal } from '../context/TerminalContext';

const TestComponent = () => {
  const {
    tabs,
    activeTabId,
    rateLimitedTabIds,
    isDrawerOpen,
    isMaximized,
    openTab,
    closeTab,
    setActiveTabId,
    toggleDrawer,
    openDrawer,
    closeDrawer,
    toggleMaximize,
    markRateLimited,
    clearRateLimited,
  } = useTerminal();

  return (
    <div>
      <div data-testid="tabs-count">{tabs.length}</div>
      <div data-testid="active-tab">{activeTabId || 'none'}</div>
      <div data-testid="rate-limited">{Array.from(rateLimitedTabIds).join(',')}</div>
      <div data-testid="drawer-open">{isDrawerOpen.toString()}</div>
      <div data-testid="maximized">{isMaximized.toString()}</div>

      <button onClick={() => openTab('test-engine', '/test/cwd')}>Open Tab</button>
      <button onClick={() => closeTab(tabs[0]?.id)}>Close Tab 1</button>
      <button onClick={() => setActiveTabId('some-id')}>Set Active Tab</button>
      <button onClick={toggleDrawer}>Toggle Drawer</button>
      <button onClick={openDrawer}>Open Drawer</button>
      <button onClick={closeDrawer}>Close Drawer</button>
      <button onClick={toggleMaximize}>Toggle Maximize</button>
      <button onClick={() => { if(tabs[0]) markRateLimited(tabs[0].id) }}>Mark Rate Limited</button>
      <button onClick={() => { if(tabs[0]) clearRateLimited(tabs[0].id) }}>Clear Rate Limited</button>
    </div>
  );
};

describe('TerminalContext', () => {
  it('provides default values', () => {
    render(
      <TerminalProvider>
        <TestComponent />
      </TerminalProvider>
    );

    expect(screen.getByTestId('tabs-count')).toHaveTextContent('0');
    expect(screen.getByTestId('active-tab')).toHaveTextContent('none');
    expect(screen.getByTestId('rate-limited')).toHaveTextContent('');
    expect(screen.getByTestId('drawer-open')).toHaveTextContent('false');
    expect(screen.getByTestId('maximized')).toHaveTextContent('false');
  });

  it('can open tabs and set active tab', () => {
    render(
      <TerminalProvider>
        <TestComponent />
      </TerminalProvider>
    );

    act(() => {
      screen.getByText('Open Tab').click();
    });

    expect(screen.getByTestId('tabs-count')).toHaveTextContent('1');
    expect(screen.getByTestId('active-tab')).not.toHaveTextContent('none');
    expect(screen.getByTestId('drawer-open')).toHaveTextContent('true');
  });

  it('can toggle drawer and shortcut works', () => {
    render(
      <TerminalProvider>
        <TestComponent />
      </TerminalProvider>
    );

    expect(screen.getByTestId('drawer-open')).toHaveTextContent('false');

    act(() => {
      screen.getByText('Toggle Drawer').click();
    });
    expect(screen.getByTestId('drawer-open')).toHaveTextContent('true');

    act(() => {
      screen.getByText('Close Drawer').click();
    });
    expect(screen.getByTestId('drawer-open')).toHaveTextContent('false');

    // Test shortcut
    act(() => {
      fireEvent.keyDown(window, { key: '`', ctrlKey: true });
    });
    expect(screen.getByTestId('drawer-open')).toHaveTextContent('true');
  });
  
  it('handles rate limit tracking', () => {
    render(
      <TerminalProvider>
        <TestComponent />
      </TerminalProvider>
    );

    act(() => {
      screen.getByText('Open Tab').click();
    });
    
    act(() => {
      screen.getByText('Mark Rate Limited').click();
    });
    
    expect(screen.getByTestId('rate-limited')).not.toHaveTextContent('');
    
    act(() => {
      screen.getByText('Clear Rate Limited').click();
    });
    
    expect(screen.getByTestId('rate-limited')).toHaveTextContent('');
  });
});
