import React, { createContext, useContext, useState, useEffect, useCallback, useMemo, useRef } from 'react';
import type { ReactNode } from 'react';
import { closePtyTerminal } from '../api/pty';

export interface TerminalTab {
  id: string;
  engine: string;
  cwd: string;
  sessionId?: string;
  attachId?: string;
  /**
   * First message for a brand-new engine session. Held in memory only: it is
   * not persisted with the tabs, so reloading the page cannot type it again
   * into a session that no longer exists.
   */
  prompt?: string;
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
  /** Where the active terminal should sit instead of the bottom drawer. */
  terminalSlot: HTMLElement | null;
  setTerminalSlot: (el: HTMLElement | null) => void;
  openTab: (engine: string, cwd: string, sessionId?: string, attachId?: string, prompt?: string) => void;
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
  terminalSlot: null,
  setTerminalSlot: () => {},
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
  const [terminalSlot, setTerminalSlot] = useState<HTMLElement | null>(null);
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

  const tabsRef = useRef(tabs);
  const activeTabIdRef = useRef(activeTabId);

  useEffect(() => {
    tabsRef.current = tabs;
  }, [tabs]);

  useEffect(() => {
    activeTabIdRef.current = activeTabId;
  }, [activeTabId]);

  const selectActiveTab = useCallback((id: string | null) => {
    activeTabIdRef.current = id;
    setActiveTabId(id);
  }, []);

  useEffect(() => {
    // The first message is deliberately left out: see TerminalTab.prompt.
    const persisted = tabs.map(tab => {
      const copy = { ...tab };
      delete copy.prompt;
      return copy;
    });
    try {
      localStorage.setItem('codeagent.terminalTabs', JSON.stringify(persisted));
    } catch {
      // Ignore storage quota/access errors (e.g. private browsing).
    }
  }, [tabs]);

  useEffect(() => {
    try {
      if (activeTabId) {
        localStorage.setItem('codeagent.activeTabId', activeTabId);
      } else {
        localStorage.removeItem('codeagent.activeTabId');
      }
    } catch {
      // Ignore storage quota/access errors.
    }
  }, [activeTabId]);

  useEffect(() => {
    try {
      localStorage.setItem('codeagent.terminalFontSize', String(fontSize));
    } catch {
      // Ignore storage quota/access errors.
    }
  }, [fontSize]);

  useEffect(() => {
    try {
      localStorage.setItem('codeagent.terminalCopyOnSelect', String(copyOnSelect));
    } catch {
      // Ignore storage quota/access errors.
    }
  }, [copyOnSelect]);

  const openTab = useCallback((engine: string, cwd: string, sessionId?: string, attachId?: string, prompt?: string) => {
    const identity = attachId ?? sessionId;
    if (identity) {
      const existing = tabsRef.current.find(
        t => (attachId ? t.attachId === attachId : t.sessionId === identity) && t.engine === engine
      );
      if (existing) {
        activeTabIdRef.current = existing.id;
        setActiveTabId(existing.id);
        setIsDrawerOpen(true);
        return;
      }
    }
    const id = Math.random().toString(36).slice(2, 11);
    const trimmed = prompt?.trim();
    const nextTab: TerminalTab = { id, engine, cwd, sessionId, attachId, ...(trimmed ? { prompt: trimmed } : {}) };
    const nextTabs = [...tabsRef.current, nextTab];
    tabsRef.current = nextTabs;
    setTabs(nextTabs);
    activeTabIdRef.current = id;
    setActiveTabId(id);
    setIsDrawerOpen(true);
  }, []);

  const closeTab = useCallback((id: string) => {
    const currentTabs = tabsRef.current;
    const idx = currentTabs.findIndex(tab => tab.id === id);
    const closing = idx >= 0 ? currentTabs[idx] : undefined;
    // An attach tab is a guest on a terminal the instances page owns.
    if (closing && !closing.attachId) {
      closePtyTerminal(closing.engine, closing.cwd, closing.sessionId, closing.id).catch(() => {});
    }
    const nextTabs = currentTabs.filter(tab => tab.id !== id);
    tabsRef.current = nextTabs;
    setTabs(nextTabs);
    setRateLimitedTabIds(prev => {
      if (!prev.has(id)) return prev;
      const newSet = new Set(prev);
      newSet.delete(id);
      return newSet;
    });
    if (activeTabIdRef.current === id) {
      if (nextTabs.length > 0) {
        const fallback = currentTabs[idx > 0 ? idx - 1 : 1]?.id ?? nextTabs[0].id;
        activeTabIdRef.current = fallback;
        setActiveTabId(fallback);
      } else {
        activeTabIdRef.current = null;
        setActiveTabId(null);
        setIsDrawerOpen(false);
      }
    }
  }, []);

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

  const value = useMemo<TerminalContextValue>(() => ({
    tabs,
    activeTabId,
    rateLimitedTabIds,
    isDrawerOpen,
    isMaximized,
    fontSize,
    copyOnSelect,
    zenMode,
    terminalSlot,
    setTerminalSlot,
    openTab,
    closeTab,
    setActiveTabId: selectActiveTab,
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
  }), [
    tabs,
    activeTabId,
    rateLimitedTabIds,
    isDrawerOpen,
    isMaximized,
    fontSize,
    copyOnSelect,
    zenMode,
    terminalSlot,
    openTab,
    closeTab,
    selectActiveTab,
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
  ]);

  return (
    <TerminalContext.Provider value={value}>
      {children}
    </TerminalContext.Provider>
  );
};
