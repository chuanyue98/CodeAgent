import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { ReactNode } from 'react';

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

// eslint-disable-next-line react-refresh/only-export-components
export const useTerminal = () => {
  const context = useContext(TerminalContext);
  if (!context) {
    throw new Error('useTerminal must be used within a TerminalProvider');
  }
  return context;
};

export const TerminalProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [tabs, setTabs] = useState<TerminalTab[]>(() => {
    try {
      const saved = localStorage.getItem('codeagent.terminalTabs');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  const [activeTabId, setActiveTabId] = useState<string | null>(() => {
    try {
      return localStorage.getItem('codeagent.activeTabId');
    } catch {
      return null;
    }
  });
  const [rateLimitedTabIds, setRateLimitedTabIds] = useState<Set<string>>(new Set());
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [isMaximized, setIsMaximized] = useState(false);

  useEffect(() => {
    localStorage.setItem('codeagent.terminalTabs', JSON.stringify(tabs));
  }, [tabs]);

  useEffect(() => {
    if (activeTabId) {
      localStorage.setItem('codeagent.activeTabId', activeTabId);
    } else {
      localStorage.removeItem('codeagent.activeTabId');
    }
  }, [activeTabId]);

  const openTab = useCallback((engine: string, cwd: string, sessionId?: string, attachId?: string) => {
    const identity = attachId ?? sessionId;
    if (identity) {
      const existing = tabs.find(
        t => (attachId ? t.attachId === attachId : t.sessionId === identity) && t.engine === engine
      );
      if (existing) {
        setActiveTabId(existing.id);
        setIsDrawerOpen(true);
        return;
      }
    }
    const id = Math.random().toString(36).slice(2, 11);
    setTabs(prev => [...prev, { id, engine, cwd, sessionId, attachId }]);
    setActiveTabId(id);
    setIsDrawerOpen(true);
  }, [tabs]);

  const closeTab = useCallback((id: string) => {
    setTabs(prev => prev.filter(tab => tab.id !== id));
    setRateLimitedTabIds(prev => {
      const newSet = new Set(prev);
      newSet.delete(id);
      return newSet;
    });
    setActiveTabId(currentActive => {
      if (currentActive === id) {
        const idx = tabs.findIndex(t => t.id === id);
        if (tabs.length > 1) {
          return tabs[idx > 0 ? idx - 1 : 1].id;
        } else {
          setIsDrawerOpen(false);
          return null;
        }
      }
      return currentActive;
    });
  }, [tabs]);

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
