import { useEffect, useState } from 'react';
import { useTerminal } from '../context/TerminalContext';
import { useSearchParams } from 'react-router';
import { AlertTriangle, ChevronDown, Loader2, Plus, Terminal, TerminalSquare, X, Zap } from 'lucide-react';
import { fetchPtyStatus } from '../api/pty';
import { useProject } from '../context/ProjectContext';
import { useT } from '../i18n/context';
import RecentSessions from './RecentSessions';
import SectionLabel from './shared/SectionLabel';
import TerminalSessionSidebar from './TerminalSessionSidebar';
import {
  AGENT_ENGINES,
  findEngine,
  SHELL_ENGINE,
  SHELL_ENGINE_ID,
  type Engine,
} from './terminalEngines';


export default function LaunchPad() {
  const t = useT();
  const { validProjects, selectedWorkspace } = useProject();

  const [available, setAvailable] = useState<boolean | null>(null);
  const [reason, setReason] = useState<string | null>(null);
  // Every open terminal stays mounted; only the active one is displayed.
  // Unmounting a tab to switch away would close its socket, and the PTY
  // endpoint spawns a process per connection -- the session would be gone,
  // not backgrounded.
  const { tabs, activeTabId, openTab, setActiveTabId } = useTerminal();
  const [searchParams] = useSearchParams();
  const effectiveProject = (validProjects.some(project => project.path === selectedWorkspace) ? selectedWorkspace : (selectedWorkspace.trim() || validProjects[0]?.path || "")).trim();
  const activeTab = tabs.find(tab => tab.id === activeTabId);



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
      <div className="min-h-0 flex-1">
        <div className="custom-scrollbar h-full overflow-y-auto pr-1">{launcher}</div>
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
