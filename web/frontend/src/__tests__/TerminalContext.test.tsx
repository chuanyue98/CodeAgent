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
    fontSize,
    increaseFontSize,
    decreaseFontSize,
    resetFontSize,
    copyOnSelect,
    toggleCopyOnSelect,
    zenMode,
    toggleZenMode,
  } = useTerminal();

  return (
    <div>
      <div data-testid="tabs-count">{tabs.length}</div>
      <div data-testid="active-tab">{activeTabId || 'none'}</div>
      <div data-testid="rate-limited">{Array.from(rateLimitedTabIds).join(',')}</div>
      <div data-testid="drawer-open">{isDrawerOpen.toString()}</div>
      <div data-testid="maximized">{isMaximized.toString()}</div>
      <div data-testid="font-size">{fontSize}</div>
      <div data-testid="copy-on-select">{copyOnSelect.toString()}</div>
      <div data-testid="zen-mode">{zenMode.toString()}</div>

      <button onClick={() => openTab('test-engine', '/test/cwd')}>Open Tab</button>
      <button onClick={() => closeTab(tabs[0]?.id)}>Close Tab 1</button>
      <button onClick={() => setActiveTabId('some-id')}>Set Active Tab</button>
      <button onClick={toggleDrawer}>Toggle Drawer</button>
      <button onClick={openDrawer}>Open Drawer</button>
      <button onClick={closeDrawer}>Close Drawer</button>
      <button onClick={toggleMaximize}>Toggle Maximize</button>
      <button onClick={() => { if(tabs[0]) markRateLimited(tabs[0].id) }}>Mark Rate Limited</button>
      <button onClick={() => { if(tabs[0]) clearRateLimited(tabs[0].id) }}>Clear Rate Limited</button>
      <button onClick={increaseFontSize}>Increase Font</button>
      <button onClick={decreaseFontSize}>Decrease Font</button>
      <button onClick={resetFontSize}>Reset Font</button>
      <button onClick={toggleCopyOnSelect}>Toggle Copy On Select</button>
      <button onClick={toggleZenMode}>Toggle Zen Mode</button>
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

  it('manages font size zooming and reset', () => {
    render(
      <TerminalProvider>
        <TestComponent />
      </TerminalProvider>
    );

    expect(screen.getByTestId('font-size')).toHaveTextContent('13');

    act(() => {
      screen.getByText('Increase Font').click();
    });
    expect(screen.getByTestId('font-size')).toHaveTextContent('14');

    act(() => {
      screen.getByText('Decrease Font').click();
    });
    expect(screen.getByTestId('font-size')).toHaveTextContent('13');

    act(() => {
      screen.getByText('Increase Font').click();
      screen.getByText('Increase Font').click();
    });
    expect(screen.getByTestId('font-size')).toHaveTextContent('15');

    act(() => {
      screen.getByText('Reset Font').click();
    });
    expect(screen.getByTestId('font-size')).toHaveTextContent('13');
  });

  it('manages copyOnSelect and zenMode toggles', () => {
    render(
      <TerminalProvider>
        <TestComponent />
      </TerminalProvider>
    );

    expect(screen.getByTestId('copy-on-select')).toHaveTextContent('true');
    expect(screen.getByTestId('zen-mode')).toHaveTextContent('false');

    act(() => {
      screen.getByText('Toggle Copy On Select').click();
      screen.getByText('Toggle Zen Mode').click();
    });

    expect(screen.getByTestId('copy-on-select')).toHaveTextContent('false');
    expect(screen.getByTestId('zen-mode')).toHaveTextContent('true');
  });

  it('supports font zoom keyboard shortcuts when drawer is open', () => {
    render(
      <TerminalProvider>
        <TestComponent />
      </TerminalProvider>
    );

    // Open drawer first
    act(() => {
      screen.getByText('Open Drawer').click();
    });

    act(() => {
      fireEvent.keyDown(window, { key: '+', ctrlKey: true });
    });
    expect(screen.getByTestId('font-size')).toHaveTextContent('14');

    act(() => {
      fireEvent.keyDown(window, { key: '-', ctrlKey: true });
    });
    expect(screen.getByTestId('font-size')).toHaveTextContent('13');

    act(() => {
      fireEvent.keyDown(window, { key: '+', ctrlKey: true });
      fireEvent.keyDown(window, { key: '+', ctrlKey: true });
    });
    expect(screen.getByTestId('font-size')).toHaveTextContent('15');

    act(() => {
      fireEvent.keyDown(window, { key: '0', ctrlKey: true });
    });
    expect(screen.getByTestId('font-size')).toHaveTextContent('13');
  });
});
