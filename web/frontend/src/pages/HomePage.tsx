import { useEffect, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { Link, useNavigate } from 'react-router';
import { fetchDaily, fetchSessions, fmtTokens, type SessionUsage } from '../api/analytics';
import { fetchSchedules, type Schedule } from '../api/schedules';
import { AGENT_ENGINES, findEngine } from '../components/terminalEngines';
import SectionLabel from '../components/shared/SectionLabel';
import { useProject } from '../context/ProjectContext';
import { useTerminal } from '../context/TerminalContext';
import { useLanguageCode, useT } from '../i18n/context';
import request from '../utils/request';
import { buildResumeLink } from '../utils/sessionLink';
import { formatRelativeCountdown, relativeTime, workspaceLabel } from '../utils/workspaceFormat';
import type { RunStatus } from '../components/TaskDashboard/types';

/** Overview shows only enough of a run to identify it; Automations shows the rest. */
type RunningTask = Pick<RunStatus, 'taskId' | 'engine' | 'status'>;

const RECENT_SESSIONS_LIMIT = 6;
const UPCOMING_LIMIT = 3;

function engineName(id: string, t: ReturnType<typeof useT>): string {
  const engine = findEngine(id);
  if (!engine) return id;
  return engine.nameKey ? t(engine.nameKey) : engine.name ?? id;
}

/**
 * The page you land on: what is open and running, what needs you, what fires
 * next, and where you left off. Everything here is read from data the gateway
 * already has; there is nothing to configure.
 */
export default function HomePage() {
  const t = useT();
  const lang = useLanguageCode();
  const navigate = useNavigate();
  const { validProjects, selectedWorkspace } = useProject();
  const { tabs, openTab, setActiveTabId, rateLimitedTabIds } = useTerminal();
  const recent = useRecentSessions(RECENT_SESSIONS_LIMIT);
  const usage = useUsage();
  const runs = useRunningTasks();
  const schedules = useSchedules();

  const workspace = (validProjects.some(p => p.path === selectedWorkspace)
    ? selectedWorkspace
    : (selectedWorkspace.trim() || validProjects[0]?.path || '')).trim();

  const startSession = (engine: string) => {
    openTab(engine, workspace);
    navigate('/agent/terminal');
  };
  const openTabPage = (id: string) => {
    setActiveTabId(id);
    navigate('/agent/terminal');
  };

  const upcoming = (schedules ?? [])
    .filter(s => s.enabled && typeof s.nextRunAt === 'number' && s.nextRunAt > 0)
    .sort((a, b) => (a.nextRunAt ?? 0) - (b.nextRunAt ?? 0))
    .slice(0, UPCOMING_LIMIT);
  const failedSchedules = (schedules ?? []).filter(s => s.enabled && s.lastRunStatus === 'failed');
  const limitedTabs = tabs.filter(tab => rateLimitedTabIds.has(tab.id));
  const hasAttention = limitedTabs.length > 0 || failedSchedules.length > 0;
  const inProgressCount = tabs.length + (runs?.length ?? 0);

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-8 px-4 py-8 md:px-8 md:py-12">
      <header className="space-y-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t('home.greeting')}</h1>
          {workspace && (
            <p className="mt-1 font-mono text-sm text-muted-foreground" title={workspace}>{workspaceLabel(workspace)}</p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label={t('home.startIn')}>
          <span className="mr-1 text-sm text-muted-foreground">{t('home.startIn')}</span>
          {AGENT_ENGINES.map(engine => (
            <button
              key={engine.id}
              type="button"
              disabled={!workspace}
              onClick={() => startSession(engine.id)}
              className="inline-flex items-center gap-2 rounded-full border border-border px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
            >
              <span className={`h-2 w-2 rounded-full ${engine.dot}`} />
              {engine.nameKey ? t(engine.nameKey) : engine.name}
            </button>
          ))}
        </div>
      </header>

      {hasAttention && (
        <section aria-label="attention" className="space-y-2">
          {limitedTabs.map(tab => (
            <div key={tab.id} className="flex items-center gap-3 rounded-xl border border-warn/40 bg-warn/10 px-4 py-3 text-sm">
              <AlertTriangle size={17} className="shrink-0 text-warn" />
              <span className="min-w-0 flex-1">
                {t('home.attentionRateLimited', { engine: engineName(tab.engine, t), workspace: workspaceLabel(tab.cwd) })}
              </span>
              <button type="button" onClick={() => openTabPage(tab.id)} className="shrink-0 rounded-lg border border-border bg-card px-3 py-1 font-medium hover:bg-muted">
                {t('home.attentionOpen')}
              </button>
            </div>
          ))}
          {failedSchedules.map(schedule => (
            <div key={schedule.id} className="flex items-center gap-3 rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm">
              <AlertTriangle size={17} className="shrink-0 text-destructive" />
              <span className="min-w-0 flex-1">{t('home.attentionFailed', { name: schedule.taskName })}</span>
              <Link to="/automations/schedules" className="shrink-0 rounded-lg border border-border bg-card px-3 py-1 font-medium hover:bg-muted">
                {t('home.attentionOpen')}
              </Link>
            </div>
          ))}
        </section>
      )}

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <section className="space-y-3">
          <SectionLabel as="h2">
            {t('home.inProgress')} <span className="ml-1 font-mono normal-case tracking-normal">{inProgressCount}</span>
          </SectionLabel>
          {inProgressCount === 0 ? (
            <p className="text-sm text-muted-foreground">{t('home.inProgressEmpty')}</p>
          ) : (
            <ul className="glass-card divide-y divide-border overflow-hidden">
              {tabs.map(tab => {
                const engine = findEngine(tab.engine);
                const limited = rateLimitedTabIds.has(tab.id);
                return (
                  <li key={tab.id}>
                    <button
                      type="button"
                      onClick={() => openTabPage(tab.id)}
                      className="grid w-full grid-cols-[8px_minmax(0,1fr)_auto] items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/60"
                    >
                      <span className={`h-2 w-2 rounded-full ${limited ? 'bg-warn' : (engine?.dot ?? 'bg-slate-400')}`} />
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-medium">{engineName(tab.engine, t)}</span>
                        <span className="block truncate font-mono text-xs text-muted-foreground">{workspaceLabel(tab.cwd)}</span>
                      </span>
                    </button>
                  </li>
                );
              })}
              {(runs ?? []).map(run => (
                <li key={run.taskId}>
                  <Link
                    to="/automations/tasks"
                    className="grid grid-cols-[8px_minmax(0,1fr)_auto] items-center gap-3 px-4 py-3 transition-colors hover:bg-muted/60"
                  >
                    <span className={`h-2 w-2 animate-pulse-soft rounded-full ${findEngine(run.engine)?.dot ?? 'bg-primary'}`} />
                    <span className="min-w-0 truncate font-mono text-sm">{run.taskId}</span>
                    <span className="text-xs text-muted-foreground">{engineName(run.engine, t)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <SectionLabel as="h2">{t('home.upNext')}</SectionLabel>
            <Link to="/automations/schedules" className="text-xs font-medium text-primary hover:underline">{t('home.allAutomations')}</Link>
          </div>
          {schedules !== null && upcoming.length === 0 && (
            <p className="text-sm text-muted-foreground">{t('home.noUpcomingSchedule')}</p>
          )}
          {upcoming.length > 0 && (
            <ul className="glass-card divide-y divide-border overflow-hidden">
              {upcoming.map(schedule => (
                <li key={schedule.id} className="flex items-center gap-3 px-4 py-3">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{schedule.taskName}</span>
                    <span className="block text-xs text-muted-foreground">{engineName(schedule.engine, t)}</span>
                  </span>
                  <span className="shrink-0 rounded-full bg-muted px-2.5 py-0.5 font-mono text-xs text-muted-foreground">
                    {formatRelativeCountdown(schedule.nextRunAt ?? 0, lang)}
                  </span>
                </li>
              ))}
            </ul>
          )}

          <dl className="grid grid-cols-3 gap-px overflow-hidden rounded-xl border border-border bg-border">
            {[
              [t('home.statToday'), usage ? fmtTokens(usage.today) : '—'],
              [t('home.statWeek'), usage ? fmtTokens(usage.week) : '—'],
              [t('home.statRunning'), runs ? String(runs.length) : '—'],
            ].map(([label, value]) => (
              <div key={label} className="bg-card px-4 py-3">
                <dt className="truncate text-xs text-muted-foreground">{label}</dt>
                <dd className="mt-0.5 font-mono text-xl font-medium tracking-tight">{value}</dd>
              </div>
            ))}
          </dl>
        </section>
      </div>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <SectionLabel as="h2">{t('home.continueTitle')}</SectionLabel>
          <Link to="/activity/sessions" className="text-xs font-medium text-primary hover:underline">{t('home.allSessions')}</Link>
        </div>
        {recent === null && <p className="text-sm text-muted-foreground">{t('home.loadingSessions')}</p>}
        {recent !== null && recent.length === 0 && <p className="text-sm text-muted-foreground">{t('home.noSessions')}</p>}
        {recent !== null && recent.length > 0 && (
          <ul className="glass-card divide-y divide-border overflow-hidden">
            {recent.map(session => {
              const engine = findEngine(session.target);
              return (
                <li key={`${session.target}:${session.sessionId}`}>
                  <Link
                    to={buildResumeLink(session.target, session.sessionId, session.projectPath || '')}
                    className="grid grid-cols-[8px_minmax(0,1fr)_auto] items-center gap-3 px-4 py-3 transition-colors hover:bg-muted/60"
                  >
                    <span className={`h-2 w-2 rounded-full ${engine?.dot ?? 'bg-slate-400'}`} />
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium">
                        {session.title?.trim() || workspaceLabel(session.projectPath || '') || t('home.unknownWorkspace')}
                      </span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {engineName(session.target, t)} · {workspaceLabel(session.projectPath || '') || t('home.unknownWorkspace')}
                      </span>
                    </span>
                    <span className="shrink-0 font-mono text-xs text-muted-foreground">
                      {fmtTokens(session.inputTokens + session.outputTokens)} · {relativeTime(session.lastActivity, lang)}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}

const dayKey = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

/** Tokens spent today and over the last seven days, summed across engines. */
function useUsage(): { today: number; week: number } | null {
  const [usage, setUsage] = useState<{ today: number; week: number } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchDaily()
      .then(daily => {
        if (cancelled) return;
        const byDay = new Map<string, number>();
        for (const row of daily) {
          byDay.set(row.date, (byDay.get(row.date) ?? 0) + row.inputTokens + row.outputTokens);
        }
        const now = new Date();
        let week = 0;
        for (let i = 0; i < 7; i += 1) {
          const day = new Date(now);
          day.setDate(day.getDate() - i);
          week += byDay.get(dayKey(day)) ?? 0;
        }
        setUsage({ today: byDay.get(dayKey(now)) ?? 0, week });
      })
      .catch(() => { if (!cancelled) setUsage({ today: 0, week: 0 }); });
    return () => { cancelled = true; };
  }, []);

  return usage;
}

function useRecentSessions(limit: number): SessionUsage[] | null {
  const [sessions, setSessions] = useState<SessionUsage[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchSessions(limit)
      .then(list => { if (!cancelled) setSessions(list); })
      .catch(() => { if (!cancelled) setSessions([]); });
    return () => { cancelled = true; };
  }, [limit]);

  return sessions;
}

/** Only the running rows matter here: everything else is noise. */
function useRunningTasks(): RunningTask[] | null {
  const [runs, setRuns] = useState<RunningTask[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    request<RunningTask[]>('/api/tasks/runs')
      .then(list => {
        if (!cancelled) setRuns(Array.isArray(list) ? list.filter(run => run.status === 'running') : []);
      })
      .catch(() => { if (!cancelled) setRuns([]); });
    return () => { cancelled = true; };
  }, []);

  return runs;
}

function useSchedules(): Schedule[] | null {
  const [schedules, setSchedules] = useState<Schedule[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchSchedules()
      .then(list => { if (!cancelled) setSchedules(Array.isArray(list) ? list : []); })
      .catch(() => { if (!cancelled) setSchedules([]); });
    return () => { cancelled = true; };
  }, []);

  return schedules;
}
