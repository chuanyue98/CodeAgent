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
  fontSize: number;
  copyOnSelect: boolean;
  zenMode: boolean;
  openTab: (engine: string, cwd: string, sessionId?: string, attachId?: string) => void;
  closeTab: (id: string) => void;
  setActiveTabId: (id: string | null) => void;
  toggleDrawer: () => void;
  openDrawer: () => void;
  closeDrawer: () => void;
  toggleMaximize: () => void;
  increaseFontSize: () => void;
  decreaseFontSize: () => void;
  resetFontSize: () => void;
  toggleCopyOnSelect: () => void;
  toggleZenMode: () => void;
  markRateLimited: (tabId: string) => void;
  clearRateLimited: (tabId: string) => void;
}

const TerminalContext = createContext<TerminalContextValue | undefined>(undefined);

const defaultTerminalContext: TerminalContextValue = {
  tabs: [],
  activeTabId: null,
  rateLimitedTabIds: new Set(),
  isDrawerOpen: false,
  isMaximized: false,
  fontSize: 13,
  copyOnSelect: true,
  zenMode: false,
  openTab: () => {},
  closeTab: () => {},
  setActiveTabId: () => {},
  toggleDrawer: () => {},
  openDrawer: () => {},
  closeDrawer: () => {},
  toggleMaximize: () => {},
  increaseFontSize: () => {},
  decreaseFontSize: () => {},
  resetFontSize: () => {},
  toggleCopyOnSelect: () => {},
  toggleZenMode: () => {},
  markRateLimited: () => {},
  clearRateLimited: () => {},
};

// eslint-disable-next-line react-refresh/only-export-components
export const useTerminal = (): TerminalContextValue => {
  const context = useContext(TerminalContext);
  return context ?? defaultTerminalContext;
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
  const [zenMode, setZenMode] = useState(false);
  const [fontSize, setFontSize] = useState<number>(() => {
    try {
      const saved = localStorage.getItem('codeagent.terminalFontSize');
      const parsed = saved ? parseInt(saved, 10) : 13;
      return Number.isFinite(parsed) && parsed >= 10 && parsed <= 24 ? parsed : 13;
    } catch {
      return 13;
    }
  });
  const [copyOnSelect, setCopyOnSelect] = useState<boolean>(() => {
    try {
      const saved = localStorage.getItem('codeagent.terminalCopyOnSelect');
      return saved !== null ? saved === 'true' : true;
    } catch {
      return true;
    }
  });

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

  useEffect(() => {
    localStorage.setItem('codeagent.terminalFontSize', String(fontSize));
  }, [fontSize]);

  useEffect(() => {
    localStorage.setItem('codeagent.terminalCopyOnSelect', String(copyOnSelect));
  }, [copyOnSelect]);

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
  const toggleZenMode = useCallback(() => setZenMode(prev => !prev), []);

  const increaseFontSize = useCallback(() => {
    setFontSize(prev => Math.min(24, prev + 1));
  }, []);

  const decreaseFontSize = useCallback(() => {
    setFontSize(prev => Math.max(10, prev - 1));
  }, []);

  const resetFontSize = useCallback(() => {
    setFontSize(13);
  }, []);

  const toggleCopyOnSelect = useCallback(() => {
    setCopyOnSelect(prev => !prev);
  }, []);

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

  // Keyboard shortcut Ctrl+` or Cmd+`, and font zoom shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === '`') {
        e.preventDefault();
        toggleDrawer();
      } else if (isDrawerOpen && (e.ctrlKey || e.metaKey) && (e.key === '=' || e.key === '+')) {
        e.preventDefault();
        increaseFontSize();
      } else if (isDrawerOpen && (e.ctrlKey || e.metaKey) && (e.key === '-' || e.key === '_')) {
        e.preventDefault();
        decreaseFontSize();
      } else if (isDrawerOpen && (e.ctrlKey || e.metaKey) && e.key === '0') {
        e.preventDefault();
        resetFontSize();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [toggleDrawer, isDrawerOpen, increaseFontSize, decreaseFontSize, resetFontSize]);

  const value = {
    tabs,
    activeTabId,
    rateLimitedTabIds,
    isDrawerOpen,
    isMaximized,
    fontSize,
    copyOnSelect,
    zenMode,
    openTab,
    closeTab,
    setActiveTabId,
    toggleDrawer,
    openDrawer,
    closeDrawer,
    toggleMaximize,
    increaseFontSize,
    decreaseFontSize,
    resetFontSize,
    toggleCopyOnSelect,
    toggleZenMode,
    markRateLimited,
    clearRateLimited,
  };

  return (
    <TerminalContext.Provider value={value}>
      {children}
    </TerminalContext.Provider>
  );
};
