import React, { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react';

export interface TerminalTab {
  id: string;
  engine: string;
  cwd: string;
  sessionId?: string;
  attachId?: string;
}

export interface TerminalContextValue {
  tabs: TerminalTab[];
  activeTabId: string | null;
  rateLimitedTabIds: Set<string>;
  isDrawerOpen: boolean;
  isMaximized: boolean;
  openTab: (engine: string, cwd: string, sessionId?: string, attachId?: string) => void;
  closeTab: (id: string) => void;
  setActiveTabId: (id: string | null) => void;
  toggleDrawer: () => void;
  openDrawer: () => void;
  closeDrawer: () => void;
  toggleMaximize: () => void;
  markRateLimited: (tabId: string) => void;
  clearRateLimited: (tabId: string) => void;
}

const TerminalContext = createContext<TerminalContextValue | undefined>(undefined);

export const useTerminal = () => {
  const context = useContext(TerminalContext);
  if (!context) {
    throw new Error('useTerminal must be used within a TerminalProvider');
  }
  return context;
};

export const TerminalProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [tabs, setTabs] = useState<TerminalTab[]>([]);
  const [activeTabId, setActiveTabId] = useState<string | null>(null);
  const [rateLimitedTabIds, setRateLimitedTabIds] = useState<Set<string>>(new Set());
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [isMaximized, setIsMaximized] = useState(false);

  const openTab = useCallback((engine: string, cwd: string, sessionId?: string, attachId?: string) => {
    const id = Math.random().toString(36).substr(2, 9);
    setTabs(prev => [...prev, { id, engine, cwd, sessionId, attachId }]);
    setActiveTabId(id);
    setIsDrawerOpen(true);
  }, []);

  const closeTab = useCallback((id: string) => {
    setTabs(prev => {
      const newTabs = prev.filter(tab => tab.id !== id);
      if (activeTabId === id) {
        if (newTabs.length > 0) {
          setActiveTabId(newTabs[newTabs.length - 1].id);
        } else {
          setActiveTabId(null);
          setIsDrawerOpen(false); // Optionally close drawer if no tabs left
        }
      }
      return newTabs;
    });
    setRateLimitedTabIds(prev => {
      const newSet = new Set(prev);
      newSet.delete(id);
      return newSet;
    });
  }, [activeTabId]);

  const toggleDrawer = useCallback(() => setIsDrawerOpen(prev => !prev), []);
  const openDrawer = useCallback(() => setIsDrawerOpen(true), []);
  const closeDrawer = useCallback(() => setIsDrawerOpen(false), []);
  const toggleMaximize = useCallback(() => setIsMaximized(prev => !prev), []);

  const markRateLimited = useCallback((tabId: string) => {
    setRateLimitedTabIds(prev => {
      const newSet = new Set(prev);
      newSet.add(tabId);
      return newSet;
    });
  }, []);

  const clearRateLimited = useCallback((tabId: string) => {
    setRateLimitedTabIds(prev => {
      const newSet = new Set(prev);
      newSet.delete(tabId);
      return newSet;
    });
  }, []);

  // Keyboard shortcut Ctrl+` or Cmd+`
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === '`') {
        e.preventDefault();
        toggleDrawer();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [toggleDrawer]);

  const value = {
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
  };

  return (
    <TerminalContext.Provider value={value}>
      {children}
    </TerminalContext.Provider>
  );
};
