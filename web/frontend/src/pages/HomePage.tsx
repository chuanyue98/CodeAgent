import { useEffect, useState } from 'react';
import { ArrowRight, ArrowUpRight, Bot, Clock, History, Settings, Terminal } from 'lucide-react';
import { Link } from 'react-router';
import { fetchAuditEvents, type AuditEvent } from '../api/audit';

const QUICK_ACTIONS = [
  {
    to: '/agent/web',
    title: 'Web Agent',
    description: 'Start or continue a structured provider conversation.',
    icon: Bot,
  },
  {
    to: '/agent/terminal',
    title: 'Local Terminal',
    description: 'Open a provider CLI in an in-browser terminal, running on this machine.',
    icon: Terminal,
  },
  {
    to: '/automations/tasks',
    title: 'Automations',
    description: 'Run tasks and manage schedules from one workspace.',
    icon: Clock,
  },
  {
    to: '/activity/history',
    title: 'Activity',
    description: 'Review conversations, events, logs, and usage.',
    icon: History,
  },
  {
    to: '/settings/capabilities/skills',
    title: 'Capabilities',
    description: 'Configure skills, prompts, hooks, plugins, and MCP.',
    icon: Settings,
  },
] as const;

const EQ_BARS = [0.4, 0.7, 1, 0.55, 0.85, 0.35, 0.65, 0.5, 0.9, 0.3, 0.75, 0.45];

const RECENT_ACTIVITY_LIMIT = 6;

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

export default function HomePage() {
  // The first two actions get the wide/tall bento slots; the rest fill in.
  const [webAgent, localTerminal, automations, activity, capabilities] = QUICK_ACTIONS;
  const recentEvents = useRecentActivity(RECENT_ACTIVITY_LIMIT);

  return (
    <div className="mx-auto w-full max-w-7xl space-y-3 p-2 sm:space-y-4 sm:p-4 lg:p-6">
      {/* Bento grid: asymmetric — hero spans 2x2, web-agent spans 2-wide,
          terminal is tall, capabilities is a full-width closing strip. */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4 lg:gap-4">

        {/* ===== HERO ===== */}
        <section
          className="animate-fade-rise stagger-1 glass-card-feature group relative flex min-h-[20rem] flex-col justify-between overflow-hidden p-6 sm:p-8 lg:col-span-2 lg:row-span-2 lg:min-h-[26rem]"
          aria-labelledby="hero-heading"
        >
          {/* Decorative orbit halo behind the copy */}
          <div aria-hidden className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 opacity-60">
            <div className="animate-orbit absolute inset-0 rounded-full border border-primary/20" />
            <div className="animate-orbit absolute inset-6 rounded-full border border-primary/10" style={{ animationDuration: '32s' }} />
            <div className="animate-orbit absolute inset-12 rounded-full border border-primary/5" style={{ animationDuration: '40s' }} />
            <div className="absolute left-1/2 top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/40 blur-[1px]" />
          </div>

          {/* Spotlight gradient that follows the card surface */}
          <div aria-hidden className="pointer-events-none absolute inset-0 bg-gradient-to-br from-primary/[0.06] via-transparent to-transparent" />

          <div className="relative">
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/[0.06] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-primary">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-pulse-ring absolute inline-flex h-full w-full rounded-full bg-primary" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-primary" />
              </span>
              CodeAgent Workspace
            </div>
            <h2 id="hero-heading" className="max-w-xl text-3xl font-bold leading-[1.05] text-slate-900 sm:text-4xl lg:text-5xl">
              Start with the <span className="font-display italic text-primary">work</span> you want to do.
            </h2>
            <p className="mt-4 max-w-md text-sm leading-6 text-slate-500">
              Agent conversations, terminal sessions, automations, activity, and configuration — grouped by workflow instead of scattered as separate top-level tools.
            </p>
          </div>

          {/* Live activity strip — gives the hero information density. */}
          <div className="relative mt-8 space-y-3">
            {/* Equalizer decoration */}
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
                  to="/activity/history"
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

        {/* ===== WEB AGENT (wide) ===== */}
        <TileLink action={webAgent} className="animate-fade-rise stagger-2 lg:col-span-2" featured />

        {/* ===== LOCAL TERMINAL (tall) ===== */}
        <TileLink action={localTerminal} className="animate-fade-rise stagger-3 lg:row-span-2" mono />

        {/* ===== AUTOMATIONS (tall — matches Local Terminal's row-span so
            row 3's last column doesn't sit empty) ===== */}
        <TileLink action={automations} className="animate-fade-rise stagger-4 lg:row-span-2" />

        {/* ===== ACTIVITY (wide) ===== */}
        <TileLink action={activity} className="animate-fade-rise stagger-5 lg:col-span-2" chart />

        {/* ===== CAPABILITIES (full-width strip) ===== */}
        <TileLink action={capabilities} className="animate-fade-rise stagger-6 lg:col-span-4" strip />
      </div>
    </div>
  );
}

/* ---------- Tile sub-component ---------- */

interface TileLinkProps {
  action: typeof QUICK_ACTIONS[number];
  className?: string;
  featured?: boolean;
  mono?: boolean;
  chart?: boolean;
  strip?: boolean;
}

function TileLink({ action, className = '', featured, mono, chart, strip }: TileLinkProps) {
  const { to, title, description, icon: Icon } = action;

  return (
    <Link
      to={to}
      aria-label={title}
      className={`glass-card group relative flex min-h-36 flex-col justify-between overflow-hidden p-5 transition-all duration-300 hover:-translate-y-0.5 hover:border-primary/30 hover:bg-white hover:shadow-[0_28px_40px_-16px_rgba(15,23,42,0.12)] ${className}`}
    >
      {/* Hover spotlight sweep */}
      <span
        aria-hidden
        className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-primary/[0.04] to-transparent transition-transform duration-700 group-hover:translate-x-full"
      />

      <div className="relative flex items-start justify-between gap-3">
        <div className={`inline-flex rounded-xl p-2.5 text-primary transition-colors ${
          featured ? 'bg-primary/15' : 'bg-primary/10 group-hover:bg-primary/15'
        }`}>
          <Icon className="h-5 w-5" />
        </div>
        <ArrowRight className="h-4 w-4 text-slate-300 transition-all duration-300 group-hover:translate-x-0.5 group-hover:text-primary" />
      </div>

      <div className="relative mt-4">
        <h3 className={`text-base font-semibold text-slate-800 ${mono ? 'font-mono' : ''}`}>
          {title}
        </h3>
        <p className="mt-1.5 text-xs leading-5 text-slate-500">{description}</p>
      </div>

      {/* Per-tile flourish — gives each card a distinct silhouette. */}
      {chart && (
        <div aria-hidden className="relative mt-4 flex h-8 items-end gap-1">
          {[0.35, 0.55, 0.4, 0.75, 0.5, 0.9, 0.6, 0.45, 0.7].map((h, i) => (
            <span
              key={i}
              className="flex-1 rounded-sm bg-gradient-to-t from-primary/20 to-primary/60 opacity-70 transition-opacity group-hover:opacity-100"
              style={{ height: `${h * 100}%` }}
            />
          ))}
        </div>
      )}

      {strip && (
        <div aria-hidden className="relative mt-4 flex flex-wrap gap-1.5">
          {['Skills', 'Prompts', 'Hooks', 'Plugins', 'MCP'].map(tag => (
            <span key={tag} className="rounded-full border border-slate-200 bg-white/60 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
              {tag}
            </span>
          ))}
        </div>
      )}

      {mono && (
        <div aria-hidden className="relative mt-4 font-mono text-[11px] leading-relaxed text-slate-400">
          <div><span className="text-emerald-500">$</span> ca --provider claude</div>
          <div className="text-slate-400">▍ ready</div>
        </div>
      )}
    </Link>
  );
}
