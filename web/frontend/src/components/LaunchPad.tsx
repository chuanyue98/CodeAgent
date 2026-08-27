import { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router';
import { AlertTriangle, Plus, TerminalSquare, X } from 'lucide-react';
import { fetchPtyStatus } from '../api/pty';
import { useProject } from '../context/ProjectContext';
import { useT } from '../i18n/context';
import type { TranslationKey } from '../i18n/locales/en';
import BrowserTerminal from './BrowserTerminal';
import TerminalSessionSidebar from './TerminalSessionSidebar';

interface Engine {
  id: string;
  name?: string;
  /** 非品牌名称（如纯终端）走 i18n。 */
  nameKey?: TranslationKey;
  /** Brand blurb that stays as-is (product names), or a key when it is prose. */
  description?: string;
  descriptionKey?: TranslationKey;
  color: string;
}

// Engine names and their vendor blurbs are brands, so they are not translated;
// only OpenCode's descriptive line is prose, and it carries a key instead.
const ENGINES: Engine[] = [
  { id: 'claude',    name: 'Claude',    description: 'Anthropic · Claude Code CLI',      color: 'bg-orange-50 border-orange-200 text-orange-700' },
  { id: 'opencode',  name: 'OpenCode',  descriptionKey: 'launch.opencodeDescription', color: 'bg-violet-50 border-violet-200 text-violet-700' },
  { id: 'codex',     name: 'Codex',     description: 'OpenAI · Codex CLI',               color: 'bg-emerald-50 border-emerald-200 text-emerald-700' },
  { id: 'codebuddy', name: 'CodeBuddy', description: 'Tencent · CodeBuddy Code CLI',     color: 'bg-sky-50 border-sky-200 text-sky-700' },
  { id: 'shell',     nameKey: 'launch.shellName', descriptionKey: 'launch.shellDescription', color: 'bg-slate-50 border-slate-200 text-slate-700' },
];

interface TerminalTab {
  /** Stable across re-renders so React keeps the same xterm instance mounted. */
  id: string;
  engine: string;
  cwd: string;
  sessionId?: string;
}

let nextTabId = 0;

export default function LaunchPad() {
  const t = useT();
  const {
    validProjects,
    selectedWorkspace,
    setSelectedWorkspace,
  } = useProject();

  const [available, setAvailable] = useState<boolean | null>(null);
  const [reason, setReason] = useState<string | null>(null);
  // Every open terminal stays mounted; only the active one is displayed.
  // Unmounting a tab to switch away would close its socket, and the PTY
  // endpoint spawns a process per connection -- the session would be gone,
  // not backgrounded.
  const [tabs, setTabs] = useState<TerminalTab[]>([]);
  // null means the launcher is showing while the open terminals sit hidden.
  const [activeTabId, setActiveTabId] = useState<string | null>(null);
  const [searchParams] = useSearchParams();

  const tabsRef = useRef<TerminalTab[]>([]);
  useEffect(() => {
    tabsRef.current = tabs;
  }, [tabs]);

  const openTab = useCallback((engine: string, cwd: string, sessionId?: string) => {
    // Resuming a session that already has a tab focuses it. Opening a second
    // PTY on one conversation gives two terminals writing the same history.
    if (sessionId) {
      const existing = tabsRef.current.find(
        tab => tab.sessionId === sessionId && tab.engine === engine,
      );
      if (existing) {
        setActiveTabId(existing.id);
        return;
      }
    }
    const id = `tab-${nextTabId++}`;
    setTabs(previous => [...previous, { id, engine, cwd, sessionId }]);
    setActiveTabId(id);
  }, []);

  const closeTab = useCallback((id: string) => {
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
  const openedDeepLinkRef = useRef<string | null>(null);
  useEffect(() => {
    const engine = searchParams.get('engine');
    const cwd = searchParams.get('cwd');
    if (!engine || !cwd) return;
    const sessionId = searchParams.get('session') ?? undefined;
    const key = `${engine}|${cwd}|${sessionId ?? ''}`;
    if (openedDeepLinkRef.current === key) return;
    openedDeepLinkRef.current = key;
    openTab(engine, cwd, sessionId);
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

  const effectiveProject = validProjects.some(project => project.path === selectedWorkspace)
    ? selectedWorkspace
    : (selectedWorkspace.trim() || validProjects[0]?.path || '');

  // An override rather than a mirror: until something is typed the field just
  // shows the shared selection, so there is no state to keep in sync (and no
  // effect writing state during render, which cascades).
  const [typedWorkspace, setTypedWorkspace] = useState<string | null>(null);
  const workspaceInput = typedWorkspace ?? effectiveProject;

  const engineLabel = (id: string) => {
    const engine = ENGINES.find(item => item.id === id);
    if (!engine) return id;
    return engine.nameKey ? t(engine.nameKey) : engine.name;
  };

  const launcher = (
    <div className="space-y-6">
      <div className="space-y-2">
        <p className="text-sm text-slate-600">
          {t('launch.intro')}
        </p>
        <p className="text-xs text-slate-400">
          {t('launch.introDetail')}
        </p>
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

      {/* A combobox, not a select: any existing directory works now (see
          core.services.workspace_service), so the registered ones are
          suggestions rather than the whole world. As a select this page was a
          dead end on a fresh install -- nothing registered meant no options,
          which meant every launch button stayed disabled. */}
      <div className="max-w-xl space-y-1">
        <label htmlFor="launchpad-project" className="text-xs font-medium text-slate-500">
          {t('filters.workspace')}
        </label>
        <input
          id="launchpad-project"
          list="launchpad-known-workspaces"
          value={workspaceInput}
          onChange={event => setTypedWorkspace(event.target.value)}
          onBlur={() => setSelectedWorkspace(workspaceInput.trim())}
          placeholder={t('launch.workspacePlaceholder')}
          spellCheck={false}
          className="w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-sm"
        />
        <datalist id="launchpad-known-workspaces">
          {validProjects.map(project => (
            <option key={project.path} value={project.path} />
          ))}
        </datalist>
        <p className="text-[11px] text-slate-400">{t('launch.workspaceHint')}</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {ENGINES.map((engine) => (
          <div
            key={engine.id}
            className="glass-card p-6 flex items-center justify-between gap-4"
          >
            <div className="space-y-1">
              <div className="font-semibold text-slate-800">{engine.nameKey ? t(engine.nameKey) : engine.name}</div>
              <div className="text-xs text-slate-500">{engine.descriptionKey ? t(engine.descriptionKey) : engine.description}</div>
            </div>

            <button
              onClick={() => openTab(engine.id, workspaceInput.trim())}
              disabled={!available || !workspaceInput.trim()}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium border transition-all
                ${!available || !workspaceInput.trim()
                  ? 'opacity-50 cursor-not-allowed'
                  : 'hover:scale-105 active:scale-95 cursor-pointer'}
                ${engine.color}`}
            >
              <TerminalSquare size={15} />
              {t('launch.openTerminal')}
            </button>
          </div>
        ))}
      </div>
    </div>
  );

  const activeTab = tabs.find(tab => tab.id === activeTabId);

  const workspace = (
    <div className="flex min-w-0 flex-1 flex-col gap-2">
      <div
        role="tablist"
        aria-label={t('launch.openTerminals')}
        className={`shrink-0 items-center gap-1 overflow-x-auto ${tabs.length === 0 ? 'hidden' : 'flex'}`}
      >
        {tabs.map(tab => {
          const active = tab.id === activeTabId;
          return (
            <div
              key={tab.id}
              className={`group flex shrink-0 items-center gap-2 rounded-t-lg border-b-2 px-3 py-1.5 text-xs transition-colors ${
                active
                  ? 'border-primary bg-primary/5 font-semibold text-primary'
                  : 'border-transparent text-slate-500 hover:bg-slate-50'
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
                {tab.sessionId && (
                  <span className="rounded-full bg-primary/10 px-1.5 text-[9px] font-semibold text-primary">
                    {t('launch.resumed')}
                  </span>
                )}
              </button>
              <button
                onClick={() => closeTab(tab.id)}
                aria-label={t('launch.closeTerminal')}
                title={t('launch.closeTerminal')}
                className="rounded p-0.5 text-slate-400 opacity-0 transition-opacity hover:bg-slate-200 hover:text-slate-700 focus:opacity-100 group-hover:opacity-100"
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
              onExit={() => {}}
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
        onOpenSession={openTab}
        onNewSession={() => setActiveTabId(null)}
      />
      {workspace}
    </div>
  );
}
