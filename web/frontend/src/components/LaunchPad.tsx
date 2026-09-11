import { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router';
import { AlertTriangle, ChevronDown, Loader2, Plus, Terminal, TerminalSquare, X, Zap } from 'lucide-react';
import { convertAndLaunchSession } from '../api/audit';
import { fetchPtyStatus } from '../api/pty';
import { useProject } from '../context/ProjectContext';
import { useT } from '../i18n/context';
import BrowserTerminal from './BrowserTerminal';
import RecentSessions from './RecentSessions';
import SectionLabel from './shared/SectionLabel';
import SmartHandoffBanner from './SmartHandoffBanner';
import TerminalSessionSidebar from './TerminalSessionSidebar';
import {
  AGENT_ENGINES,
  findEngine,
  SHELL_ENGINE,
  SHELL_ENGINE_ID,
  type Engine,
} from './terminalEngines';

interface TerminalTab {
  /** Stable across re-renders so React keeps the same xterm instance mounted. */
  id: string;
  engine: string;
  cwd: string;
  sessionId?: string;
  /** 重新接回一个仍在运行的终端（来自实例管理页）。 */
  attachId?: string;
}

const TABS_STORAGE_KEY = 'codeagent.terminalTabs';
const ACTIVE_TAB_STORAGE_KEY = 'codeagent.activeTabId';

let nextTabId = 0;

function loadPersistedTabs(): { tabs: TerminalTab[]; activeTabId: string | null } {
  if (typeof window === 'undefined') {
    return { tabs: [], activeTabId: null };
  }
  const search = window.location.search;
  if (search.includes('engine=') && search.includes('cwd=')) {
    return { tabs: [], activeTabId: null };
  }
  try {
    const raw = localStorage.getItem(TABS_STORAGE_KEY);
    if (!raw) return { tabs: [], activeTabId: null };
    const saved: TerminalTab[] = JSON.parse(raw);
    if (!Array.isArray(saved) || saved.length === 0) {
      return { tabs: [], activeTabId: null };
    }

    let maxId = 0;
    const restoredTabs: TerminalTab[] = saved.map(tab => {
      const match = tab.id.match(/^tab-(\d+)$/);
      if (match) {
        const num = parseInt(match[1], 10);
        if (!isNaN(num) && num >= maxId) maxId = num + 1;
      }
      return { ...tab };
    });
    nextTabId = Math.max(nextTabId, maxId);

    const savedActive = localStorage.getItem(ACTIVE_TAB_STORAGE_KEY);
    const active = savedActive && restoredTabs.some(t => t.id === savedActive)
      ? savedActive
      : (restoredTabs[0]?.id ?? null);

    return { tabs: restoredTabs, activeTabId: active };
  } catch {
    localStorage.removeItem(TABS_STORAGE_KEY);
    localStorage.removeItem(ACTIVE_TAB_STORAGE_KEY);
    return { tabs: [], activeTabId: null };
  }
}

export default function LaunchPad() {
  const t = useT();
  const { validProjects, selectedWorkspace } = useProject();

  const [available, setAvailable] = useState<boolean | null>(null);
  const [reason, setReason] = useState<string | null>(null);
  // Every open terminal stays mounted; only the active one is displayed.
  // Unmounting a tab to switch away would close its socket, and the PTY
  // endpoint spawns a process per connection -- the session would be gone,
  // not backgrounded.
  const [initialTabs] = useState(() => loadPersistedTabs());
  const [tabs, setTabs] = useState<TerminalTab[]>(initialTabs.tabs);
  // null means the launcher is showing while the open terminals sit hidden.
  const [activeTabId, setActiveTabId] = useState<string | null>(initialTabs.activeTabId);
  const [searchParams] = useSearchParams();

  const tabsRef = useRef<TerminalTab[]>([]);
  useEffect(() => {
    tabsRef.current = tabs;
  }, [tabs]);

  // Persist open tabs to localStorage so page refresh doesn't lose active terminals
  useEffect(() => {
    try {
      if (tabs.length > 0) {
        localStorage.setItem(
          TABS_STORAGE_KEY,
          JSON.stringify(
            tabs.map(({ id, engine, cwd, sessionId, attachId }) => ({
              id,
              engine,
              cwd,
              sessionId,
              attachId,
            })),
          ),
        );
        if (activeTabId) {
          localStorage.setItem(ACTIVE_TAB_STORAGE_KEY, activeTabId);
        } else {
          localStorage.removeItem(ACTIVE_TAB_STORAGE_KEY);
        }
      } else {
        localStorage.removeItem(TABS_STORAGE_KEY);
        localStorage.removeItem(ACTIVE_TAB_STORAGE_KEY);
      }
    } catch {
      // Ignore storage quota or disabled errors
    }
  }, [tabs, activeTabId]);

  const openTab = useCallback(
    (engine: string, cwd: string, sessionId?: string, attachId?: string) => {
      // Resuming a session that already has a tab focuses it. Opening a second
      // PTY on one conversation gives two terminals writing the same history;
      // attaching twice to one running terminal shares a mirrored view.
      const identity = attachId ?? sessionId;
      if (identity) {
        const existing = tabsRef.current.find(
          tab =>
            (attachId ? tab.attachId === attachId : tab.sessionId === identity) &&
            tab.engine === engine,
        );
        if (existing) {
          setActiveTabId(existing.id);
          return;
        }
      }
      const id = `tab-${nextTabId++}`;
      setTabs(previous => [...previous, { id, engine, cwd, sessionId, attachId }]);
      setActiveTabId(id);
    },
    [],
  );

  const closeTab = useCallback((id: string) => {
    setRateLimitTabId(current => (current === id ? null : current));
    setTabs(previous => {
      const index = previous.findIndex(tab => tab.id === id);
      if (index === -1) return previous;
      const remaining = previous.filter(tab => tab.id !== id);
      setActiveTabId(current => {
        if (current !== id) return current;
        // Land on the neighbour rather than dumping the user back at the
        // launcher while other terminals are still running.
        const neighbour = remaining[index] ?? remaining[index - 1];
        return neighbour?.id ?? null;
      });
      return remaining;
    });
  }, []);

  // Deep link from the session browser: `?engine=&cwd=&session=` opens that
  // session in the terminal here. Resuming used to open a GUI terminal on the
  // machine running the server, which the browser could not reach.
  // `?attach=`（实例管理页）接回一个断开但引擎仍在跑的终端。
  const openedDeepLinkRef = useRef<string | null>(null);
  useEffect(() => {
    const engine = searchParams.get('engine');
    const cwd = searchParams.get('cwd');
    if (!engine || !cwd) return;
    const sessionId = searchParams.get('session') ?? undefined;
    const attachId = searchParams.get('attach') ?? undefined;
    const key = `${engine}|${cwd}|${sessionId ?? ''}|${attachId ?? ''}`;
    if (openedDeepLinkRef.current === key) return;
    openedDeepLinkRef.current = key;
    openTab(engine, cwd, sessionId, attachId);
  }, [searchParams, openTab]);

  useEffect(() => {
    fetchPtyStatus()
      .then(status => {
        setAvailable(status.available);
        setReason(status.reason);
      })
      .catch(err => {
        setAvailable(false);
        setReason(err instanceof Error ? err.message : t('launch.detectFailed'));
      });
  }, [t]);

  // The header's workspace switcher is the only place the selection is made,
  // including for a directory that is not in the registry. This page used to
  // carry a second field for that, so one screen had two controls writing one
  // value and no way to tell which one was authoritative.
  const effectiveProject = (validProjects.some(project => project.path === selectedWorkspace)
    ? selectedWorkspace
    : (selectedWorkspace.trim() || validProjects[0]?.path || '')).trim();

  const activeTab = tabs.find(tab => tab.id === activeTabId);

  const [showHandoffMenu, setShowHandoffMenu] = useState(false);
  const [handoffLoading, setHandoffLoading] = useState<string | null>(null);
  const [handoffError, setHandoffError] = useState<string | null>(null);
  const [rateLimitTabId, setRateLimitTabId] = useState<string | null>(null);
  const handoffMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setRateLimitTabId(null);
  }, [activeTabId]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (handoffMenuRef.current && !handoffMenuRef.current.contains(event.target as Node)) {
        setShowHandoffMenu(false);
      }
    }
    if (showHandoffMenu) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showHandoffMenu]);

  const handleHandoff = async (targetEngine: string) => {
    if (!activeTab) return;
    setHandoffLoading(targetEngine);
    setHandoffError(null);
    try {
      const result = await convertAndLaunchSession({
        sourceEngine: activeTab.engine,
        sessionId: activeTab.sessionId,
        targetEngine,
        projectPath: activeTab.cwd,
      });
      setShowHandoffMenu(false);
      setRateLimitTabId(null);
      openTab(result.engine, result.project, result.sessionId);
    } catch (err) {
      setHandoffError(err instanceof Error ? err.message : String(err));
    } finally {
      setHandoffLoading(null);
    }
  };

  const engineCard = (engine: Engine) => {
    const name = engine.nameKey ? t(engine.nameKey) : engine.name;
    const description = engine.descriptionKey
      ? t(engine.descriptionKey)
      : engine.description;
    const blocked = !available || !effectiveProject;
    const Icon = engine.id === SHELL_ENGINE_ID ? Terminal : TerminalSquare;
    return (
      <button
        key={engine.id}
        type="button"
        onClick={() => openTab(engine.id, effectiveProject)}
        disabled={blocked}
        aria-label={`${t('launch.openTerminal')} · ${name}`}
        title={`${t('launch.openTerminal')} · ${name}`}
        className={`glass-card flex h-full w-full items-center gap-3 p-4 text-left transition-all ${
          blocked
            ? 'cursor-not-allowed opacity-50'
            : 'cursor-pointer hover:-translate-y-0.5 hover:shadow-lg'
        }`}
      >
        <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${engine.accent}`}>
          <Icon size={17} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate font-semibold text-slate-800">{name}</span>
          <span className="line-clamp-2 block text-xs text-slate-500">{description}</span>
        </span>
      </button>
    );
  };

  const engineLabel = (id: string): string => {
    const engine = findEngine(id);
    if (!engine) return id;
    return (engine.nameKey ? t(engine.nameKey) : engine.name) ?? id;
  };

  const launcher = (
    <div className="space-y-6">
      <div className="space-y-1">
        <p className="text-sm text-slate-600">{t('launch.intro')}</p>
        {/* The long explanation is first-run material: it stops once a
            terminal has been opened, rather than sitting above the only
            control on the page forever. */}
        {tabs.length === 0 && (
          <p className="text-xs text-slate-500">{t('launch.introDetail')}</p>
        )}
        {/* The header switcher shows only the trailing directory name, and
            which directory a terminal opens in is the one thing you must be
            able to check before launching one. */}
        {effectiveProject && (
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 pt-1 text-xs text-slate-500">
            <span>{t('launch.workspaceLabel')}</span>
            <code
              data-testid="launch-workspace"
              className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-700"
            >
              {effectiveProject}
            </code>
            <span className="text-slate-400">{t('launch.workspaceChange')}</span>
          </p>
        )}
      </div>

      {available === false && (
        <div role="status" className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-semibold">{t('launch.unavailable')}</p>
            <p className="mt-0.5 text-xs">{reason}</p>
          </div>
        </div>
      )}

      {/* Disabled cards used to be the whole message: five tiles at half
          opacity and nothing saying which of the two reasons applied. */}
      {available !== false && !effectiveProject && (
        <p role="status" className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
          {t('launch.pickWorkspace')}
        </p>
      )}

      {/* The card is the button. A small button parked at the far edge of a
          wide card left the label stranded from what it acts on, and it was
          the one target that had to survive every column width. */}
      <section className="space-y-2">
        <SectionLabel as="h2">{t('launch.engines')}</SectionLabel>
        {/* Four agents, so every column count divides the row evenly. The
            fifth card used to sit in this grid and wrap 3 + 2, leaving a
            card-shaped hole at the width the page is usually read at. */}
        <div className="grid auto-rows-fr grid-cols-1 gap-3 sm:grid-cols-2 2xl:grid-cols-4">
          {AGENT_ENGINES.map(engineCard)}
        </div>
        {/* And, separately, no agent at all. */}
        <div className="pt-1">{engineCard(SHELL_ENGINE)}</div>
      </section>

      <RecentSessions
        workspace={effectiveProject}
        activeSessionId={activeTab?.sessionId}
        onOpen={openTab}
      />
    </div>
  );


  const workspace = (
    <div className="flex min-w-0 flex-1 flex-col gap-2">
      <div className={`shrink-0 items-center justify-between gap-2 ${tabs.length === 0 ? 'hidden' : 'flex'}`}>
        <div
          role="tablist"
          aria-label={t('launch.openTerminals')}
          className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto"
        >
          {tabs.map(tab => {
            const active = tab.id === activeTabId;
            return (
              <div
                key={tab.id}
                className={`group flex shrink-0 items-center gap-2 rounded-lg px-3 py-1.5 text-xs transition-colors ${
                  active
                    ? 'bg-primary/10 font-semibold text-primary'
                    : 'text-slate-500 hover:bg-slate-50'
                }`}
              >
                <button
                  role="tab"
                  aria-selected={active}
                  onClick={() => setActiveTabId(tab.id)}
                  className="flex items-center gap-1.5"
                  title={tab.cwd}
                >
                  <TerminalSquare size={13} className="shrink-0" />
                  <span className="max-w-40 truncate">{engineLabel(tab.engine)}</span>
                  {(tab.sessionId || tab.attachId) && (
                    <span className="rounded-full bg-primary/10 px-1.5 text-[9px] font-semibold text-primary">
                      {t('launch.resumed')}
                    </span>
                  )}
                </button>
                <button
                  onClick={() => closeTab(tab.id)}
                  aria-label={t('launch.closeTerminal')}
                  title={t('launch.closeTerminal')}
                  className="rounded p-0.5 text-slate-300 transition-colors hover:bg-slate-200 hover:text-slate-700"
                >
                  <X size={12} />
                </button>
              </div>
            );
          })}
          <button
            onClick={() => setActiveTabId(null)}
            aria-label={t('launch.newTerminal')}
            title={t('launch.newTerminal')}
            className={`flex shrink-0 items-center gap-1 rounded-lg px-2 py-1.5 text-xs transition-colors ${
              activeTabId === null
                ? 'bg-primary/10 font-semibold text-primary'
                : 'text-slate-500 hover:bg-slate-50'
            }`}
          >
            <Plus size={13} />
          </button>
        </div>

        {activeTab && activeTab.engine !== SHELL_ENGINE_ID && (
          <div ref={handoffMenuRef} className="relative shrink-0">
            <button
              onClick={() => setShowHandoffMenu(prev => !prev)}
              disabled={handoffLoading !== null}
              className="flex items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50/80 px-2.5 py-1 text-xs font-medium text-amber-800 shadow-sm transition-colors hover:bg-amber-100 disabled:opacity-50"
              title={t('launch.handoffTitle')}
            >
              {handoffLoading ? (
                <Loader2 size={13} className="animate-spin text-amber-600" />
              ) : (
                <Zap size={13} className="text-amber-600 fill-amber-500/20" />
              )}
              <span className="hidden sm:inline font-semibold">
                {handoffLoading
                  ? t('launch.handoffInProgress', { engine: engineLabel(handoffLoading) })
                  : t('launch.handoff')}
              </span>
              <ChevronDown size={12} className={`transition-transform text-amber-600 ${showHandoffMenu ? 'rotate-180' : ''}`} />
            </button>
            {showHandoffMenu && (
              <div className="absolute right-0 top-full z-50 mt-1 min-w-40 rounded-xl border border-slate-200 bg-white/95 p-1 shadow-lg backdrop-blur">
                <div className="px-2 py-1 text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
                  {t('launch.handoffTitle')}
                </div>
                {AGENT_ENGINES.filter(e => e.id !== activeTab.engine).map(target => (
                  <button
                    key={target.id}
                    onClick={() => void handleHandoff(target.id)}
                    className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs text-slate-700 transition-colors hover:bg-slate-100"
                  >
                    <span className={`h-2 w-2 rounded-full ${target.dot}`} />
                    <span className="font-medium">{target.nameKey ? t(target.nameKey) : target.name}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {handoffError && (
        <div className="flex items-center justify-between rounded-lg border border-red-200 bg-red-50 p-2 text-xs text-red-700">
          <span>{t('launch.handoffFailed', { error: handoffError })}</span>
          <button onClick={() => setHandoffError(null)} className="p-0.5 text-red-500 hover:text-red-700">
            <X size={12} />
          </button>
        </div>
      )}

      {activeTab && rateLimitTabId === activeTab.id && (
        <SmartHandoffBanner
          activeEngine={activeTab.engine}
          onHandoff={handleHandoff}
          onDismiss={() => setRateLimitTabId(null)}
          loadingEngine={handoffLoading}
        />
      )}

      <div className="min-h-0 flex-1">
        {activeTabId === null && (
          <div className="custom-scrollbar h-full overflow-y-auto pr-1">{launcher}</div>
        )}
        {/* Every terminal stays mounted -- see the `tabs` state comment. */}
        {tabs.map(tab => (
          <div
            key={tab.id}
            className={tab.id === activeTabId ? 'flex h-full min-h-0 flex-col' : 'hidden'}
          >
            <BrowserTerminal
              engine={tab.engine}
              cwd={tab.cwd}
              sessionId={tab.sessionId}
              attachId={tab.attachId}
              onExit={() => {}}
              onTerminalEvent={event => {
                if (event === 'rate_limit') {
                  setRateLimitTabId(tab.id);
                }
              }}
            />
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div className="flex h-full min-h-0 gap-3">
      <TerminalSessionSidebar
        currentWorkspace={effectiveProject}
        activeSessionId={activeTab?.sessionId}
        launcherActive={activeTabId === null}
        onOpenSession={openTab}
        onNewSession={() => setActiveTabId(null)}
      />
      {workspace}
    </div>
  );
}
