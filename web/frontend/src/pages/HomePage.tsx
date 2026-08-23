import { useEffect, useState } from 'react';
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  Bot,
  Clock3,
  Cpu,
  HardDrive,
  MemoryStick,
  Terminal,
} from 'lucide-react';
import { Link } from 'react-router';
import { fetchAuditEvents, type AuditEvent } from '../api/audit';
import { fetchSessions, type SessionUsage } from '../api/analytics';
import request from '../utils/request';
import { useSystemMetrics } from '../context/SystemMetricsContext';

const EQ_BARS = [0.4, 0.7, 1, 0.55, 0.85, 0.35, 0.65, 0.5, 0.9, 0.3, 0.75, 0.45];

const RECENT_ACTIVITY_LIMIT = 6;
const RECENT_SESSIONS_LIMIT = 5;

/** Compact "2s"/"14m"/"3h"/"2d" — matches the hero's tight, terminal-ish style. */
function formatCompactAgo(timestamp: string): string {
  const then = new Date(timestamp).getTime();
  if (Number.isNaN(then)) return '';
  const diffSec = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (diffSec < 60) return `${diffSec}s`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h`;
  return `${Math.floor(diffHr / 24)}d`;
}

function describeAuditEvent(event: AuditEvent): string {
  if (event.event_type === 'tool_call') {
    return event.tool_name ? `${event.engine}.tool.${event.tool_name}` : `${event.engine}.tool_call`;
  }
  return event.role === 'user' ? `${event.engine}.message.user` : `${event.engine}.message.assistant`;
}

function toneForEvent(event: AuditEvent): 'live' | 'ok' | 'idle' {
  if (event.event_type === 'tool_call') return 'ok';
  return event.role === 'user' ? 'live' : 'idle';
}

/** Last path segment — the label form every other page uses for a workspace. */
function workspaceLabel(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).pop() || path;
}

interface RunStatus {
  task_id: string;
  engine: string;
  status: string;
}

/**
 * Home used to be five entry cards repeating the five primary-nav items one
 * to one. It is now a dashboard of live data — recent sessions, what is
 * running, system health — so the page answers "what's going on / what was I
 * doing" instead of "where is the nav" (the sidebar already answers that).
 */
export default function HomePage() {
  const recentEvents = useRecentActivity(RECENT_ACTIVITY_LIMIT);
  const recentSessions = useRecentSessions(RECENT_SESSIONS_LIMIT);
  const runs = useRunningTasks();
  const { metrics } = useSystemMetrics();

  return (
    <div className="mx-auto w-full max-w-7xl space-y-3 p-2 sm:space-y-4 sm:p-4 lg:p-6">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 lg:gap-4">

        {/* ===== HERO + live activity ===== */}
        <section
          className="animate-fade-rise stagger-1 glass-card-feature group relative flex min-h-[18rem] flex-col justify-between overflow-hidden p-6 sm:p-8 lg:col-span-2"
          aria-labelledby="hero-heading"
        >
          <div aria-hidden className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 opacity-60">
            <div className="animate-orbit absolute inset-0 rounded-full border border-primary/20" />
            <div className="animate-orbit absolute inset-6 rounded-full border border-primary/10" style={{ animationDuration: '32s' }} />
            <div className="animate-orbit absolute inset-12 rounded-full border border-primary/5" style={{ animationDuration: '40s' }} />
            <div className="absolute left-1/2 top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/40 blur-[1px]" />
          </div>
          <div aria-hidden className="pointer-events-none absolute inset-0 bg-gradient-to-br from-primary/[0.06] via-transparent to-transparent" />

          <div className="relative">
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/[0.06] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-primary">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-pulse-ring absolute inline-flex h-full w-full rounded-full bg-primary" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-primary" />
              </span>
              CodeAgent Workspace
            </div>
            <h2 id="hero-heading" className="max-w-xl text-3xl font-bold leading-[1.05] text-slate-900 sm:text-4xl">
              Start with the <span className="font-display italic text-primary">work</span> you want to do.
            </h2>
            {/* Quick actions stay one compact row — the sidebar owns
                navigation; these are just the two most common starts. */}
            <div className="mt-4 flex flex-wrap gap-2">
              <Link
                to="/agent/web"
                className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-xs font-semibold text-white transition-all hover:opacity-90"
              >
                <Bot className="h-3.5 w-3.5" /> New conversation
              </Link>
              <Link
                to="/agent/terminal"
                className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white/70 px-4 py-2 text-xs font-semibold text-slate-600 transition-colors hover:border-primary/30 hover:text-primary"
              >
                <Terminal className="h-3.5 w-3.5" /> Open terminal
              </Link>
            </div>
          </div>

          <div className="relative mt-8 space-y-3">
            <div aria-hidden className="flex h-10 items-end gap-[3px]">
              {EQ_BARS.map((h, i) => (
                <span
                  key={i}
                  className="eq-bar w-1.5 rounded-full bg-gradient-to-t from-primary/30 to-primary"
                  style={{ height: `${h * 100}%`, animationDelay: `${i * 70}ms` }}
                />
              ))}
            </div>

            <div className="rounded-2xl border border-slate-200/70 bg-white/60 p-3 backdrop-blur-sm">
              <div className="mb-2 flex items-center justify-between">
                <span className="font-mono text-[10px] font-semibold uppercase tracking-widest text-slate-400">recent activity</span>
                <Link
                  to="/activity/timeline"
                  className="inline-flex items-center gap-1 text-[11px] font-semibold text-primary transition-colors hover:text-primary/80"
                >
                  View all <ArrowUpRight className="h-3 w-3" />
                </Link>
              </div>
              <ul className="space-y-1.5">
                {recentEvents === null ? (
                  <li className="font-mono text-xs text-slate-400">Loading…</li>
                ) : recentEvents.length === 0 ? (
                  <li className="font-mono text-xs text-slate-400">No activity yet — start a session to see it here.</li>
                ) : (
                  recentEvents.map(event => {
                    const tone = toneForEvent(event);
                    return (
                      <li key={event.event_id} className="flex items-center justify-between gap-2 font-mono text-xs">
                        <span className="flex min-w-0 items-center gap-2 text-slate-600">
                          <span
                            className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                              tone === 'live' ? 'animate-pulse-soft bg-emerald-500'
                              : tone === 'ok'   ? 'bg-primary'
                              : 'bg-slate-300'
                            }`}
                          />
                          <span className="truncate">{describeAuditEvent(event)}</span>
                        </span>
                        <span className="shrink-0 text-slate-400">{formatCompactAgo(event.timestamp)}</span>
                      </li>
                    );
                  })
                )}
              </ul>
            </div>
          </div>
        </section>

        {/* ===== SYSTEM ===== */}
        <section className="animate-fade-rise stagger-2 glass-card flex flex-col p-5">
          <div className="flex items-center justify-between">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-700">
              <Cpu className="h-4 w-4 text-primary" /> System
            </h3>
            <Link to="/settings/system" className="text-[11px] font-semibold text-primary hover:underline">
              Details
            </Link>
          </div>
          <div className="mt-4 flex-1 space-y-3">
            {metrics ? (
              <>
                <MetricRow icon={<Cpu className="h-3.5 w-3.5" />} label="CPU" value={metrics.cpu_percent} />
                <MetricRow icon={<MemoryStick className="h-3.5 w-3.5" />} label="Memory" value={metrics.memory_percent} extra={`${metrics.memory_used_gb.toFixed(1)} / ${metrics.memory_total_gb.toFixed(1)} GB`} />
                <MetricRow icon={<HardDrive className="h-3.5 w-3.5" />} label="Disk" value={metrics.disk_percent} extra={`${metrics.disk_used_gb.toFixed(0)} / ${metrics.disk_total_gb.toFixed(0)} GB`} />
              </>
            ) : (
              <p className="text-xs text-slate-400">Loading metrics…</p>
            )}
          </div>
        </section>

        {/* ===== RECENT SESSIONS ===== */}
        <section className="animate-fade-rise stagger-3 glass-card flex flex-col p-5 sm:col-span-2">
          <div className="flex items-center justify-between">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-700">
              <Activity className="h-4 w-4 text-primary" /> Continue where you left off
            </h3>
            <Link to="/activity/sessions" className="text-[11px] font-semibold text-primary hover:underline">
              All sessions
            </Link>
          </div>
          <ul className="mt-3 flex-1 divide-y divide-slate-100">
            {recentSessions === null ? (
              <li className="py-6 text-center text-xs text-slate-400">Loading sessions…</li>
            ) : recentSessions.length === 0 ? (
              <li className="py-6 text-center text-xs text-slate-400">
                No sessions yet — start a conversation or run a task.
              </li>
            ) : (
              recentSessions.map(session => (
                <li key={session.sessionId}>
                  <Link
                    to={`/activity/sessions?session=${encodeURIComponent(session.sessionId)}`}
                    className="group flex items-center justify-between gap-3 py-2.5"
                  >
                    <span className="flex min-w-0 items-center gap-3">
                      <span className="shrink-0 rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase text-slate-500">
                        {session.target}
                      </span>
                      <span className="min-w-0 truncate text-xs font-medium text-slate-700 group-hover:text-primary">
                        {workspaceLabel(session.projectPath || '') || 'Unknown workspace'}
                      </span>
                    </span>
                    <span className="flex shrink-0 items-center gap-2 text-[10px] text-slate-400">
                      <span>{formatCompactAgo(session.lastActivity)}</span>
                      <ArrowRight className="h-3 w-3 opacity-0 transition-opacity group-hover:opacity-100" />
                    </span>
                  </Link>
                </li>
              ))
            )}
          </ul>
        </section>

        {/* ===== AUTOMATIONS ===== */}
        <section className="animate-fade-rise stagger-4 glass-card flex flex-col p-5">
          <div className="flex items-center justify-between">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-700">
              <Clock3 className="h-4 w-4 text-primary" /> Automations
            </h3>
            <Link to="/automations/tasks" className="text-[11px] font-semibold text-primary hover:underline">
              Open
            </Link>
          </div>
          <div className="mt-4 flex-1">
            {runs === null ? (
              <p className="text-xs text-slate-400">Checking runs…</p>
            ) : runs.length === 0 ? (
              <div className="space-y-2">
                <p className="text-xs text-slate-500">Nothing running right now.</p>
                <Link
                  to="/automations/tasks"
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary hover:underline"
                >
                  Run a task <ArrowRight className="h-3 w-3" />
                </Link>
              </div>
            ) : (
              <ul className="space-y-2">
                {runs.map(run => (
                  <li
                    key={run.task_id}
                    className="flex items-center gap-2 rounded-lg border border-emerald-100 bg-emerald-50/60 px-3 py-2 text-xs"
                  >
                    <span className="relative flex h-2 w-2">
                      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                      <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
                    </span>
                    <span className="min-w-0 flex-1 truncate font-mono font-semibold text-emerald-800">
                      {run.task_id}
                    </span>
                    <span className="shrink-0 text-[10px] font-semibold uppercase text-emerald-600">
                      {run.engine}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

function MetricRow({ icon, label, value, extra }: {
  icon: React.ReactNode;
  label: string;
  value: number;
  extra?: string;
}) {
  const pct = Math.min(Math.round(value), 100);
  const tone = value > 85 ? 'bg-red-500' : value > 65 ? 'bg-amber-400' : 'bg-primary';
  return (
    <div>
      <div className="flex items-center justify-between text-xs">
        <span className="flex items-center gap-1.5 text-slate-500">
          {icon} {label}
        </span>
        <span className="font-medium text-slate-700">
          {pct}%{extra ? <span className="ml-1 font-normal text-slate-400">{extra}</span> : null}
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
        <div className={`h-full rounded-full transition-all ${tone}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function useRecentActivity(limit: number): AuditEvent[] | null {
  const [events, setEvents] = useState<AuditEvent[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchAuditEvents({ limit })
      .then(res => { if (!cancelled) setEvents(res.events); })
      .catch(() => { if (!cancelled) setEvents([]); });
    return () => { cancelled = true; };
  }, [limit]);

  return events;
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

/** Only the running rows matter on a dashboard — everything else is noise. */
function useRunningTasks(): RunStatus[] | null {
  const [runs, setRuns] = useState<RunStatus[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    request<RunStatus[]>('/api/tasks/runs')
      .then(list => { if (!cancelled) setRuns((list || []).filter(run => run.status === 'running')); })
      .catch(() => { if (!cancelled) setRuns([]); });
    return () => { cancelled = true; };
  }, []);

  return runs;
}
