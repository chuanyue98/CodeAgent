import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { AlertTriangle } from 'lucide-react';
import { fetchSessionPage, type SessionUsage } from '../api/analytics';
import { fetchPtyStatus } from '../api/pty';
import { useProject } from '../context/ProjectContext';
import { useTerminal } from '../context/TerminalContext';
import { useLanguageCode, useT } from '../i18n/context';
import { relativeTime, workspaceLabel } from '../utils/workspaceFormat';
import SectionLabel from './shared/SectionLabel';
import SessionInspector from './SessionInspector';
import {
  AGENT_ENGINES,
  SHELL_ENGINE,
  findEngine,
  type Engine,
} from './terminalEngines';

const RECENT_LIMIT = 6;

/**
 * The Sessions stage. With a session open it is the terminal plus an
 * inspector; with none it is where you start one.
 *
 * Every open terminal stays mounted in GlobalTerminalDrawer and only the
 * active one is shown: unmounting a tab to switch away would close its socket,
 * and the PTY endpoint spawns a process per connection, so the session would
 * be gone rather than backgrounded. This component only leaves the slot the
 * terminal is placed into.
 */
export default function LaunchPad() {
  const t = useT();
  const language = useLanguageCode();
  const { validProjects, selectedWorkspace } = useProject();
  const { activeTabId, openTab, setTerminalSlot, tabs } = useTerminal();
  const [searchParams] = useSearchParams();

  const [available, setAvailable] = useState<boolean | null>(null);
  const [reason, setReason] = useState<string | null>(null);
  const [recent, setRecent] = useState<SessionUsage[] | null>(null);

  const effectiveProject = (validProjects.some(project => project.path === selectedWorkspace) ? selectedWorkspace : (selectedWorkspace.trim() || validProjects[0]?.path || '')).trim();
  const activeTab = tabs.find(tab => tab.id === activeTabId);

  useEffect(() => {
    fetchPtyStatus()
      .then(res => {
        setAvailable(res.available);
        setReason(res.reason || null);
      })
      .catch(err => {
        setAvailable(false);
        setReason(String(err));
      });
  }, []);

  useEffect(() => {
    if (activeTab) return;
    let cancelled = false;
    fetchSessionPage({ limit: RECENT_LIMIT })
      .then(page => { if (!cancelled) setRecent(page.sessions); })
      .catch(() => { if (!cancelled) setRecent([]); });
    return () => { cancelled = true; };
  }, [activeTab]);

  useEffect(() => {
    const engineParam = searchParams.get('engine');
    const cwdParam = searchParams.get('cwd');
    const sessionParam = searchParams.get('session') || undefined;
    const attachParam = searchParams.get('attach') || undefined;
    if (engineParam && cwdParam && (sessionParam || attachParam)) {
      openTab(engineParam, cwdParam, sessionParam, attachParam);
    }
  }, [searchParams, openTab]);

  if (activeTab) {
    return (
      <div className="flex h-full min-h-0">
        {/* The terminal itself stays mounted in GlobalTerminalDrawer; this
            empty box only tells it where to sit. */}
        <div ref={setTerminalSlot} data-testid="terminal-slot" className="min-w-0 flex-1" />
        <SessionInspector tab={activeTab} />
      </div>
    );
  }

  const blocked = !available || !effectiveProject;

  const engineButton = (engine: Engine) => {
    const name = engine.nameKey ? t(engine.nameKey) : engine.name;
    const description = engine.descriptionKey ? t(engine.descriptionKey) : engine.description;
    return (
      <button
        key={engine.id}
        type="button"
        onClick={() => openTab(engine.id, effectiveProject)}
        disabled={blocked}
        aria-label={`${t('launch.openTerminal')} · ${name}`}
        title={`${t('launch.openTerminal')} · ${name}`}
        className={`glass-card flex w-full items-center gap-3 px-4 py-3 text-left transition-colors ${
          blocked ? 'cursor-not-allowed opacity-50' : 'glass-card-interactive cursor-pointer'
        }`}
      >
        <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${engine.dot}`} />
        <span className="min-w-0 flex-1">
          <span className="block truncate font-semibold">{name}</span>
          <span className="block truncate text-xs text-muted-foreground">{description}</span>
        </span>
      </button>
    );
  };

  return (
    <div className="custom-scrollbar h-full overflow-y-auto">
      <div className="mx-auto flex max-w-3xl flex-col gap-8 px-4 py-8 md:px-8 md:py-12">
        <header className="space-y-2">
          <h1 className="text-2xl font-semibold tracking-tight">{t('launch.newChat')}</h1>
          {/* Which directory a terminal opens in is the one thing to check
              before launching one, and the rail shows only its last segment. */}
          {effectiveProject && (
            <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
              <span>{t('launch.workspaceLabel')}</span>
              <code data-testid="launch-workspace" className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-foreground">
                {effectiveProject}
              </code>
              <span>{t('launch.workspaceChange')}</span>
            </p>
          )}
        </header>

        {available === false && (
          <div role="status" className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <p className="font-semibold">{t('launch.unavailable')}</p>
              <p className="mt-0.5 text-xs">{reason}</p>
            </div>
          </div>
        )}
        {available !== false && !effectiveProject && (
          <p role="status" className="rounded-xl border border-border bg-muted px-4 py-3 text-sm text-muted-foreground">
            {t('launch.pickWorkspace')}
          </p>
        )}

        <section className="space-y-3">
          <SectionLabel as="h2">{t('launch.engines')}</SectionLabel>
          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
            {AGENT_ENGINES.map(engineButton)}
            {engineButton(SHELL_ENGINE)}
          </div>
        </section>

        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <SectionLabel as="h2">{t('launch.recent')}</SectionLabel>
            <Link to="/activity/sessions" className="text-xs font-medium text-primary hover:underline">
              {t('launch.allHistory')}
            </Link>
          </div>
          {recent !== null && recent.length === 0 && (
            <p className="text-sm text-muted-foreground">{t('terminalSidebar.empty')}</p>
          )}
          {recent !== null && recent.length > 0 && (
            <ul className="glass-card divide-y divide-border overflow-hidden">
              {recent.map(session => {
                const engine = findEngine(session.target);
                return (
                  <li key={`${session.target}:${session.sessionId}`}>
                    <button
                      type="button"
                      onClick={() => openTab(session.target, session.projectPath, session.sessionId)}
                      title={session.title || session.sessionId}
                      className="grid w-full grid-cols-[8px_minmax(0,1fr)_auto] items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-muted/60"
                    >
                      <span className={`h-2 w-2 rounded-full ${engine?.dot ?? 'bg-slate-400'}`} />
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-medium">{session.title || t('terminalSidebar.untitled')}</span>
                        <span className="block truncate text-xs text-muted-foreground">
                          {engine?.nameKey ? t(engine.nameKey) : (engine?.name ?? session.target)} · {workspaceLabel(session.projectPath)}
                        </span>
                      </span>
                      <span className="shrink-0 font-mono text-xs text-muted-foreground">
                        {relativeTime(session.lastActivity, language)}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
