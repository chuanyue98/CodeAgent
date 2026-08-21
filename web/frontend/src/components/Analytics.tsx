import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { TooltipPayloadEntry } from 'recharts';
import { Link } from 'react-router';
import {
  ArrowDownRight,
  ArrowUpRight,
  ArrowUpRight as LinkArrow,
  Clock,
  Database,
  DollarSign,
  FileText,
  RefreshCw,
  Terminal,
  TrendingUp,
} from 'lucide-react';
import { format } from 'date-fns';
import ErrorState from './shared/ErrorState';
import LoadingState from './shared/LoadingState';
import { localDayOffset } from '../utils/dateRange';
import {
  type DailyUsage,
  type EngineSummary,
  type ModelStat,
  type MonthlyUsage,
  type SessionUsage,
  fetchDaily,
  fetchEngines,
  fetchModels,
  fetchMonthly,
  fetchSessions,
  fetchSummary,
  fmtCost,
  fmtTokens,
  refreshAnalytics,
} from '../api/analytics';

// ── Engine palette ───────────────────────────────────────────────────────────
const ENGINE_COLORS: Record<string, string> = {
  claude: '#f97316',
  gemini: '#3b82f6',
  codex: '#10b981',
  opencode: '#8b5cf6',
};
const ENGINE_BADGE: Record<string, string> = {
  claude: 'bg-orange-100 text-orange-700',
  gemini: 'bg-blue-100 text-blue-700',
  codex: 'bg-emerald-100 text-emerald-700',
  opencode: 'bg-violet-100 text-violet-700',
};
function ec(t: string) { return ENGINE_COLORS[t] ?? '#94a3b8'; }
function eb(t: string) { return ENGINE_BADGE[t] ?? 'bg-slate-100 text-slate-600'; }

// A row in the time-series recharts dataset: one string category key (`_key`,
// used as the axis `dataKey`) plus one numeric total per engine, added
// dynamically as engines are discovered. The engine index signature is widened
// to `number | string` only so the literal `_key` property is legal on the
// same type; every access on a dynamic key is numeric by construction.
type ChartRow = { _key: string; [engine: string]: number | string };

// ── Range ────────────────────────────────────────────────────────────────────
// The page used to have no time filter at all: charts covered all history and
// the detail table was hardcoded to "last 30 days" regardless. One range now
// scopes the whole page, so every number on screen means the same window.
type RangeId = '7d' | '30d' | '90d' | 'all';
const RANGES: { id: RangeId; label: string; days: number | null }[] = [
  { id: '7d', label: '7 days', days: 7 },
  { id: '30d', label: '30 days', days: 30 },
  { id: '90d', label: '90 days', days: 90 },
  { id: 'all', label: 'All time', days: null },
];

// ── Tiny helpers ─────────────────────────────────────────────────────────────
function formatDate(s: string) {
  try { return format(new Date(s), 'MMM dd'); } catch { return s.slice(5); }
}
function formatMonth(s: string) {
  try { return format(new Date(`${s}-01`), 'MMM yyyy'); } catch { return s; }
}
function timeAgo(iso: string) {
  if (!iso) return '—';
  const ms = Date.now() - new Date(iso).getTime();
  const days = Math.floor(ms / 86400000);
  if (days === 0) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 30) return `${days}d ago`;
  return iso.slice(0, 10);
}

/** Per-model totals for the selected range, rebuilt from daily breakdowns. */
interface RangeModelStat {
  model: string;
  targets: string[];
  inputTokens: number;
  outputTokens: number;
  cacheCreationTokens: number;
  cacheReadTokens: number;
  cost: number;
  inputCost: number;
  outputCost: number;
  cacheWriteCost: number;
  cacheReadCost: number;
}

// ── Stat card ────────────────────────────────────────────────────────────────
function StatCard({
  label, value, sub, Icon, iconColor, iconBg, stagger = 'stagger-1',
}: {
  label: string; value: string; sub?: string;
  Icon: React.ElementType; iconColor: string; iconBg: string;
  stagger?: string;
}) {
  return (
    <div className={`animate-fade-rise ${stagger} glass-card group p-4 transition-all duration-300 hover:-translate-y-0.5 hover:shadow-[0_24px_36px_-16px_rgba(15,23,42,0.12)]`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 space-y-0.5">
          <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-widest truncate">{label}</p>
          <p className="text-xl font-bold text-slate-800 truncate">{value}</p>
          {sub && <p className="text-[10px] text-slate-500 truncate">{sub}</p>}
        </div>
        <div className={`p-2 rounded-lg shrink-0 ${iconBg} transition-transform duration-300 group-hover:scale-110`}>
          <Icon className={`w-4 h-4 ${iconColor}`} />
        </div>
      </div>
    </div>
  );
}

// ── Custom tooltip ────────────────────────────────────────────────────────────
// `TooltipPayloadEntry` is recharts' own entry shape (all fields optional / a
// union `ValueType = number | string | ReadonlyArray<number | string>`), so we
// normalize the bits we actually render instead of trusting them blindly.
function ChartTooltip({ active, payload, label, isCost }: {
  active?: boolean; payload?: ReadonlyArray<TooltipPayloadEntry>;
  label?: string; isCost?: boolean;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 shadow-lg text-xs">
      <p className="font-semibold mb-1.5 text-slate-700">{label}</p>
      {payload.map((entry, i) => {
        const color = entry.color ?? '#94a3b8';
        const value = typeof entry.value === 'number' ? entry.value : Number(entry.value ?? 0);
        return (
          <p key={i} className="flex gap-2 items-center" style={{ color }}>
            <span className="w-2 h-2 rounded-full shrink-0" style={{ background: color }} />
            <span className="text-slate-600">{String(entry.name ?? '')}:</span>
            <span className="font-semibold">
              {isCost ? fmtCost(value) : fmtTokens(value)}
            </span>
          </p>
        );
      })}
    </div>
  );
}

function SectionTitle({ children, action }: { children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-2">
      <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-widest">{children}</p>
      {action}
    </div>
  );
}

// ── Main component ───────────────────────────────────────────────────────────
const Analytics: React.FC = () => {
  const [range, setRange] = useState<RangeId>('30d');
  const [engines, setEngines] = useState<EngineSummary[]>([]);
  const [daily, setDaily] = useState<DailyUsage[]>([]);
  const [monthly, setMonthly] = useState<MonthlyUsage[]>([]);
  const [sessions, setSessions] = useState<SessionUsage[]>([]);
  const [modelStats, setModelStats] = useState<ModelStat[]>([]);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [totalSessions, setTotalSessions] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Guards setState calls in the async fetch below from firing after the
  // component has unmounted (e.g. a fast page switch while the request is
  // still in flight).
  const mountedRef = useRef(true);
  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const loadAll = useCallback(async () => {
    try {
      const [summary, eng, day, mon, sess, mods] = await Promise.all([
        fetchSummary(), fetchEngines(), fetchDaily(), fetchMonthly(), fetchSessions(500), fetchModels(),
      ]);
      if (!mountedRef.current) return;
      setEngines(eng); setDaily(day); setMonthly(mon); setSessions(sess); setModelStats(mods);
      setTotalSessions(summary.session_count);
      setError(null);
    } catch (e) {
      if (!mountedRef.current) return;
      setError(e instanceof Error ? e.message : 'Failed to load analytics');
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void loadAll(); }, [loadAll]);

  const retry = useCallback(() => {
    setError(null);
    setLoading(true);
    void loadAll();
  }, [loadAll]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try { await refreshAnalytics(); await loadAll(); } catch { /* ignore */ }
    finally { setRefreshing(false); }
  };

  const activeRange = RANGES.find(r => r.id === range) ?? RANGES[1];
  const rangeLabel = activeRange.label.toLowerCase();

  // Over a long window a per-day series is unreadable, so the all-time view
  // rolls up by month. This is what the old separate Monthly tab was for.
  const granularity: 'day' | 'month' = range === 'all' ? 'month' : 'day';

  const rangeDaily = useMemo(() => {
    if (activeRange.days === null) return daily;
    const cutoff = localDayOffset(activeRange.days - 1);
    return daily.filter(d => d.date >= cutoff);
  }, [daily, activeRange.days]);

  // Every headline number derives from the same filtered set, so the range
  // control can't leave a stat card describing a different window than the
  // chart beside it.
  const totals = useMemo(() => {
    let inputTokens = 0, outputTokens = 0, cacheTokens = 0, cost = 0;
    for (const d of rangeDaily) {
      inputTokens += d.inputTokens;
      outputTokens += d.outputTokens;
      cacheTokens += d.cacheCreationTokens + d.cacheReadTokens;
      cost += d.cost;
    }
    return { inputTokens, outputTokens, cacheTokens, cost };
  }, [rangeDaily]);

  const rangeSessions = useMemo(() => {
    if (activeRange.days === null) return sessions;
    const cutoff = localDayOffset(activeRange.days - 1);
    return sessions.filter(s => (s.lastActivity || '').slice(0, 10) >= cutoff);
  }, [sessions, activeRange.days]);

  // `summary.session_count` is authoritative but all-time only; a narrowed
  // range has to count the fetched window instead.
  const sessionCount = activeRange.days === null ? totalSessions : rangeSessions.length;
  const avgCostPerSession = sessionCount > 0 ? totals.cost / sessionCount : 0;

  /** Per-engine totals for the range, rebuilt from daily rows. */
  const rangeEngines = useMemo(() => {
    if (activeRange.days === null) return engines;
    const byTarget = new Map<string, EngineSummary>();
    for (const d of rangeDaily) {
      const current = byTarget.get(d.target) ?? {
        target: d.target,
        inputTokens: 0, outputTokens: 0, cacheCreationTokens: 0, cacheReadTokens: 0,
        cost: 0, sessionCount: 0, models: [],
      };
      current.inputTokens += d.inputTokens;
      current.outputTokens += d.outputTokens;
      current.cacheCreationTokens += d.cacheCreationTokens;
      current.cacheReadTokens += d.cacheReadTokens;
      current.cost += d.cost;
      current.models = [...new Set([...current.models, ...d.modelsUsed])];
      byTarget.set(d.target, current);
    }
    for (const session of rangeSessions) {
      const entry = byTarget.get(session.target);
      if (entry) entry.sessionCount += 1;
    }
    return [...byTarget.values()].sort((a, b) => b.cost - a.cost);
  }, [engines, rangeDaily, rangeSessions, activeRange.days]);

  /**
   * Per-model totals for the range. Token counts come straight from the daily
   * breakdowns; the four cost categories aren't carried there, so they're
   * derived from each model's all-time cost-per-token, which is constant for
   * a given model and already the assumption behind the all-time figures.
   */
  const rangeModels = useMemo<RangeModelStat[]>(() => {
    if (activeRange.days === null) {
      return modelStats.map(m => ({
        model: m.model,
        targets: m.targets,
        inputTokens: m.inputTokens,
        outputTokens: m.outputTokens,
        cacheCreationTokens: m.cacheCreationTokens,
        cacheReadTokens: m.cacheReadTokens,
        cost: m.cost,
        inputCost: m.inputCost,
        outputCost: m.outputCost,
        cacheWriteCost: m.cacheWriteCost,
        cacheReadCost: m.cacheReadCost,
      }));
    }

    const rateOf = (model: string) => {
      const all = modelStats.find(m => m.model === model);
      const per = (cost: number, tokens: number) => (tokens > 0 ? cost / tokens : 0);
      return {
        input: per(all?.inputCost ?? 0, all?.inputTokens ?? 0),
        output: per(all?.outputCost ?? 0, all?.outputTokens ?? 0),
        cacheWrite: per(all?.cacheWriteCost ?? 0, all?.cacheCreationTokens ?? 0),
        cacheRead: per(all?.cacheReadCost ?? 0, all?.cacheReadTokens ?? 0),
      };
    };

    const byModel = new Map<string, RangeModelStat>();
    for (const d of rangeDaily) {
      for (const bd of d.modelBreakdowns ?? []) {
        const current = byModel.get(bd.modelName) ?? {
          model: bd.modelName, targets: [],
          inputTokens: 0, outputTokens: 0, cacheCreationTokens: 0, cacheReadTokens: 0,
          cost: 0, inputCost: 0, outputCost: 0, cacheWriteCost: 0, cacheReadCost: 0,
        };
        current.inputTokens += bd.inputTokens;
        current.outputTokens += bd.outputTokens;
        current.cacheCreationTokens += bd.cacheCreationTokens;
        current.cacheReadTokens += bd.cacheReadTokens;
        current.cost += bd.cost;
        if (!current.targets.includes(d.target)) current.targets.push(d.target);
        byModel.set(bd.modelName, current);
      }
    }

    return [...byModel.values()]
      .map(m => {
        const rate = rateOf(m.model);
        return {
          ...m,
          inputCost: m.inputTokens * rate.input,
          outputCost: m.outputTokens * rate.output,
          cacheWriteCost: m.cacheCreationTokens * rate.cacheWrite,
          cacheReadCost: m.cacheReadTokens * rate.cacheRead,
        };
      })
      .sort((a, b) => b.cost - a.cost);
  }, [modelStats, rangeDaily, activeRange.days]);

  const activeModel = rangeModels.find(m => m.model === selectedModel) ?? null;

  // ── Time series (day rows in a narrow range, month rows for all time) ────
  const series = useMemo(() => {
    const rows = granularity === 'month'
      ? monthly.map(m => ({
          key: m.month, target: m.target, cost: m.cost,
          tokens: m.inputTokens + m.outputTokens,
        }))
      : rangeDaily.map(d => ({
          key: d.date, target: d.target, cost: d.cost,
          tokens: d.inputTokens + d.outputTokens,
        }));

    const cost: Record<string, ChartRow> = {};
    const tokens: Record<string, ChartRow> = {};
    for (const row of rows) {
      cost[row.key] ??= { _key: row.key };
      tokens[row.key] ??= { _key: row.key };
      cost[row.key][row.target] = Number(cost[row.key][row.target] ?? 0) + row.cost;
      tokens[row.key][row.target] = Number(tokens[row.key][row.target] ?? 0) + row.tokens;
    }
    const byKey = (a: ChartRow, b: ChartRow) => a._key.localeCompare(b._key);
    return {
      cost: Object.values(cost).sort(byKey),
      tokens: Object.values(tokens).sort(byKey),
      engines: [...new Set(rows.map(r => r.target))],
    };
  }, [granularity, monthly, rangeDaily]);

  const formatAxis = granularity === 'month' ? formatMonth : formatDate;

  const pieData = useMemo(
    () => rangeEngines.filter(e => e.cost > 0).map(e => ({ name: e.target, value: e.cost })),
    [rangeEngines],
  );

  const recentSessions = useMemo(() => rangeSessions.slice(0, 5), [rangeSessions]);

  const hasUsage = totalSessions > 0 || daily.length > 0;
  const hasRangeUsage = rangeDaily.length > 0;

  if (loading) {
    return <LoadingState />;
  }

  if (error) {
    return <ErrorState message={error} onRetry={retry} />;
  }

  return (
    <div className="flex flex-col gap-5 pb-6">

      {/* ── Toolbar ────────────────────────────────────────────────────────── */}
      <div className="animate-fade-rise stagger-1 flex flex-wrap items-center justify-between gap-2">
        <div
          className="flex gap-1 bg-slate-100 p-1 rounded-xl"
          role="group"
          aria-label="Time range"
        >
          {RANGES.map(r => (
            <button
              key={r.id}
              onClick={() => setRange(r.id)}
              aria-pressed={range === r.id}
              className={`px-4 py-1.5 text-sm font-semibold rounded-lg transition-all ${
                range === r.id
                  ? 'bg-white text-primary shadow-sm'
                  : 'text-slate-600 hover:text-slate-800'
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
        <button
          onClick={() => void handleRefresh()}
          disabled={refreshing}
          className="flex items-center gap-2 px-3 py-1.5 text-sm font-semibold text-slate-600
            hover:text-primary bg-white rounded-xl border border-slate-200
            hover:border-primary/30 transition-all disabled:opacity-50"
        >
          <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Zeros across five stat cards and a blank half-page read as "broken",
          not "nothing recorded yet". Say which it is, and where the data
          comes from, before showing the empty numbers. */}
      {!hasUsage && (
        <div className="glass-card flex flex-col items-center gap-2 px-6 py-10 text-center">
          <div className="rounded-2xl bg-primary/10 p-3 text-primary">
            <TrendingUp className="h-6 w-6" />
          </div>
          <p className="text-sm font-semibold text-slate-800">No usage recorded yet</p>
          <p className="max-w-md text-xs leading-5 text-slate-500">
            Token counts and cost estimates are read from the session logs each provider CLI
            writes on this machine. Run an agent session or a task, then press Refresh — nothing
            is sent anywhere to produce these numbers.
          </p>
        </div>
      )}

      {/* Distinguishes "you have no usage at all" from "nothing in the last
          7 days", which otherwise render as the same wall of zeros. */}
      {hasUsage && !hasRangeUsage && (
        <div className="glass-card flex flex-col items-center gap-1 px-6 py-8 text-center">
          <p className="text-sm font-semibold text-slate-800">No usage in the last {rangeLabel}</p>
          <p className="text-xs text-slate-500">
            Pick a wider range to see earlier activity.
          </p>
        </div>
      )}

      {/* ── Stat cards ─────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        <StatCard
          label="Total Tokens"
          value={fmtTokens(totals.inputTokens + totals.outputTokens + totals.cacheTokens)}
          sub={`${fmtTokens(totals.inputTokens)} in / ${fmtTokens(totals.outputTokens)} out`}
          Icon={FileText} iconColor="text-blue-600" iconBg="bg-blue-100" stagger="stagger-2"
        />
        <StatCard
          label="Total Cost" value={fmtCost(totals.cost)}
          sub={`~${fmtCost(avgCostPerSession)} / session`}
          Icon={DollarSign} iconColor="text-green-600" iconBg="bg-green-100" stagger="stagger-3"
        />
        <StatCard
          label="Cache Tokens" value={fmtTokens(totals.cacheTokens)}
          sub={`${rangeEngines.length} engine${rangeEngines.length === 1 ? '' : 's'}`}
          Icon={Database} iconColor="text-cyan-600" iconBg="bg-cyan-100" stagger="stagger-4"
        />
        <StatCard
          label="Input Cost"
          value={fmtCost(rangeModels.reduce((s, m) => s + m.inputCost, 0))}
          sub={`${fmtTokens(totals.inputTokens)} tokens`}
          Icon={ArrowDownRight} iconColor="text-purple-600" iconBg="bg-purple-100" stagger="stagger-5"
        />
        <StatCard
          label="Output Cost"
          value={fmtCost(rangeModels.reduce((s, m) => s + m.outputCost, 0))}
          sub={`${fmtTokens(totals.outputTokens)} tokens`}
          Icon={ArrowUpRight} iconColor="text-orange-600" iconBg="bg-orange-100" stagger="stagger-6"
        />
      </div>

      {/* ── Usage over time ────────────────────────────────────────────────── */}
      <div className="animate-fade-rise stagger-2 glass-card p-5">
        <SectionTitle>
          Cost by engine — {granularity === 'month' ? 'per month' : `last ${rangeLabel}`}
        </SectionTitle>
        <ResponsiveContainer width="100%" height={240}>
          <AreaChart data={series.cost} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <defs>
              {series.engines.map(eng => (
                <linearGradient key={eng} id={`grad-${eng}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={ec(eng)} stopOpacity={0.5} />
                  <stop offset="95%" stopColor={ec(eng)} stopOpacity={0.05} />
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis
              dataKey="_key" tick={{ fontSize: 11 }} tickLine={false}
              tickFormatter={v => formatAxis(String(v))}
            />
            <YAxis
              tick={{ fontSize: 11 }} tickLine={false}
              tickFormatter={v => `$${(v as number).toFixed(0)}`}
              width={45}
            />
            <Tooltip
              content={props => (
                <ChartTooltip
                  active={props.active}
                  payload={props.payload}
                  label={props.label != null ? formatAxis(String(props.label)) : undefined}
                  isCost
                />
              )}
            />
            {series.engines.map(eng => (
              <Area
                key={eng} type="monotone" dataKey={eng} name={eng}
                stroke={ec(eng)} strokeWidth={2} fill={`url(#grad-${eng})`}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="animate-fade-rise stagger-3 glass-card p-5">
        <SectionTitle>
          Tokens by engine — {granularity === 'month' ? 'per month' : `last ${rangeLabel}`}
        </SectionTitle>
        <ResponsiveContainer width="100%" height={200}>
          {granularity === 'month' ? (
            <BarChart data={series.tokens} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="_key" tick={{ fontSize: 11 }} tickLine={false}
                tickFormatter={v => formatMonth(String(v))} />
              <YAxis tick={{ fontSize: 11 }} tickLine={false}
                tickFormatter={v => fmtTokens(v as number)} width={45} />
              <Tooltip
                content={props => (
                  <ChartTooltip
                    active={props.active}
                    payload={props.payload}
                    label={props.label != null ? formatMonth(String(props.label)) : undefined}
                  />
                )}
              />
              {series.engines.map((eng, i) => (
                <Bar key={eng} dataKey={eng} name={eng} stackId="a" fill={ec(eng)}
                  radius={i === series.engines.length - 1 ? [3, 3, 0, 0] : [0, 0, 0, 0]} />
              ))}
            </BarChart>
          ) : (
            <AreaChart data={series.tokens} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
              <defs>
                {series.engines.map(eng => (
                  <linearGradient key={eng} id={`tgrad-${eng}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={ec(eng)} stopOpacity={0.4} />
                    <stop offset="95%" stopColor={ec(eng)} stopOpacity={0.02} />
                  </linearGradient>
                ))}
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="_key" tick={{ fontSize: 11 }} tickLine={false}
                tickFormatter={v => formatDate(String(v))} />
              <YAxis tick={{ fontSize: 11 }} tickLine={false}
                tickFormatter={v => fmtTokens(v as number)} width={45} />
              <Tooltip
                content={props => (
                  <ChartTooltip
                    active={props.active}
                    payload={props.payload}
                    label={props.label != null ? formatDate(String(props.label)) : undefined}
                  />
                )}
              />
              {series.engines.map(eng => (
                <Area key={eng} type="monotone" dataKey={eng} name={eng}
                  stroke={ec(eng)} strokeWidth={2} fill={`url(#tgrad-${eng})`} />
              ))}
            </AreaChart>
          )}
        </ResponsiveContainer>
      </div>

      {/* ── Engines + distribution ─────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 grid grid-cols-1 sm:grid-cols-2 gap-3">
          {rangeEngines.map((eng, i) => (
            <div
              key={eng.target}
              className={`animate-fade-rise stagger-${Math.min(i + 2, 7)} glass-card group p-4 transition-all duration-300 hover:-translate-y-0.5 hover:shadow-[0_24px_36px_-16px_rgba(15,23,42,0.12)]`}
            >
              <div className="flex items-center justify-between mb-3">
                <span className={`text-[11px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full ${eb(eng.target)}`}>
                  {eng.target}
                </span>
                <span className="text-xs text-slate-400">{eng.sessionCount} sessions</span>
              </div>
              <div className="space-y-1.5 text-xs">
                {[
                  { label: 'Input', value: fmtTokens(eng.inputTokens) },
                  { label: 'Output', value: fmtTokens(eng.outputTokens) },
                  { label: 'Cache', value: fmtTokens(eng.cacheCreationTokens + eng.cacheReadTokens) },
                ].map(({ label, value }) => (
                  <div key={label} className="flex justify-between">
                    <span className="text-slate-400">{label}</span>
                    <span className="font-semibold text-slate-700">{value}</span>
                  </div>
                ))}
                <div className="flex justify-between pt-1.5 border-t border-slate-100">
                  <span className="text-slate-500 font-medium">Est. Cost</span>
                  <span className="font-bold" style={{ color: ec(eng.target) }}>
                    {fmtCost(eng.cost)}
                  </span>
                </div>
              </div>
              <div className="mt-2 text-[10px] text-slate-300 truncate">
                {eng.models.slice(0, 2).join(', ')}{eng.models.length > 2 && ` +${eng.models.length - 2} more`}
              </div>
            </div>
          ))}
          {rangeEngines.length === 0 && (
            <p className="text-xs text-slate-400">No engine usage in this range.</p>
          )}
        </div>

        <div className="animate-fade-rise stagger-5 flex flex-col gap-3">
          {pieData.length > 0 && (
            <div className="glass-card p-4">
              <SectionTitle>Cost Distribution</SectionTitle>
              <ResponsiveContainer width="100%" height={180}>
                <PieChart>
                  <Pie
                    data={pieData} dataKey="value" nameKey="name"
                    cx="50%" cy="45%" innerRadius={42} outerRadius={64}
                    paddingAngle={2}
                    label={({ percent }: { percent?: number }) =>
                      (percent ?? 0) > 0.05 ? `${((percent ?? 0) * 100).toFixed(0)}%` : ''
                    }
                    labelLine={false}
                  >
                    {pieData.map(entry => (
                      <Cell key={entry.name} fill={ec(entry.name)} strokeWidth={1} />
                    ))}
                  </Pie>
                  <Tooltip
                    content={({ active, payload }) => {
                      if (!active || !payload?.length) return null;
                      const p = payload[0].payload as { name: string; value: number };
                      return (
                        <div className="rounded-lg border border-slate-200 bg-white p-2 shadow-lg text-xs">
                          <p className="font-semibold" style={{ color: ec(p.name) }}>{p.name}</p>
                          <p className="text-slate-600">{fmtCost(p.value)}</p>
                        </div>
                      );
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="flex flex-wrap gap-x-3 gap-y-1 justify-center mt-1">
                {pieData.map(e => (
                  <span key={e.name} className="flex items-center gap-1 text-[10px] text-slate-500">
                    <span className="w-2 h-2 rounded-full" style={{ background: ec(e.name) }} />
                    {e.name}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="glass-card p-4 flex-1">
            <SectionTitle
              action={
                <Link
                  to="/activity/sessions"
                  className="flex items-center gap-1 text-[10px] font-semibold text-primary hover:underline"
                >
                  All sessions <LinkArrow className="h-3 w-3" />
                </Link>
              }
            >
              <span className="flex items-center gap-1.5"><Terminal className="w-3 h-3" /> Sessions</span>
            </SectionTitle>
            <div className="grid grid-cols-2 gap-2 mb-3">
              <div className="p-2 rounded-lg bg-slate-50 border border-slate-100 text-center">
                <p className="text-lg font-bold text-blue-600">{sessionCount}</p>
                <p className="text-[9px] text-slate-600 uppercase tracking-wide">
                  {activeRange.days === null ? 'Total' : `Last ${rangeLabel}`}
                </p>
              </div>
              <div className="p-2 rounded-lg bg-slate-50 border border-slate-100 text-center">
                <p className="text-lg font-bold text-green-700">{fmtCost(avgCostPerSession)}</p>
                <p className="text-[9px] text-slate-600 uppercase tracking-wide">Avg / session</p>
              </div>
            </div>
            <div className="space-y-1.5">
              <div className="flex items-center gap-1 text-[10px] text-slate-400 font-medium mb-1">
                <Clock className="w-3 h-3" /> Recent activity
              </div>
              {recentSessions.map(s => (
                <div
                  key={`${s.target}::${s.sessionId}`}
                  className="flex items-center justify-between text-xs p-1.5 rounded-md bg-slate-50/80 hover:bg-slate-100/70 transition-colors border border-slate-100"
                >
                  <div className="flex flex-col min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="font-medium truncate text-slate-700" title={s.projectPath}>
                        {s.projectPath.split(/[\\/]/).pop() || s.projectPath || '—'}
                      </span>
                      <span className={`shrink-0 px-1 py-0 text-[9px] font-bold rounded uppercase ${eb(s.target)}`}>
                        {s.target}
                      </span>
                    </div>
                    <span className="text-[10px] text-slate-400">{timeAgo(s.lastActivity)}</span>
                  </div>
                  <div className="text-right shrink-0 ml-2">
                    <div className="font-mono text-[11px] font-semibold text-slate-700">
                      {fmtCost(s.cost)}
                    </div>
                    <div className="text-[9px] text-slate-400">
                      {fmtTokens(s.inputTokens + s.outputTokens)}
                    </div>
                  </div>
                </div>
              ))}
              {recentSessions.length === 0 && (
                <p className="text-[11px] text-slate-400">No sessions in this range.</p>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── Model breakdown ────────────────────────────────────────────────── */}
      {rangeModels.length > 0 && (
        <div className="animate-fade-rise stagger-6 glass-card p-5">
          <SectionTitle>Model Breakdown</SectionTitle>
          <div className="flex flex-col lg:flex-row gap-4">
            <div className="flex-1 space-y-1.5 min-w-0">
              {rangeModels.map(m => {
                const pct = totals.cost > 0 ? (m.cost / totals.cost) * 100 : 0;
                const isSelected = selectedModel === m.model;
                return (
                  <button
                    key={m.model}
                    aria-pressed={isSelected}
                    onClick={() => setSelectedModel(isSelected ? null : m.model)}
                    className={`w-full text-left rounded-xl px-3 py-2.5 transition-all border ${
                      isSelected
                        ? 'bg-slate-100 border-slate-300'
                        : 'bg-slate-50/60 border-transparent hover:bg-slate-100/70 hover:border-slate-200'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <span className="text-xs font-semibold text-slate-700 truncate">{m.model}</span>
                      <div className="flex items-center gap-2 shrink-0">
                        {m.targets.map(t => (
                          <span key={t} className={`text-[9px] font-black uppercase px-1.5 py-0.5 rounded-full ${eb(t)}`}>{t}</span>
                        ))}
                        <span className="text-xs font-bold text-slate-600">{fmtCost(m.cost)}</span>
                        <span className="text-[10px] text-slate-400">{pct.toFixed(1)}%</span>
                      </div>
                    </div>
                    <div className="w-full h-1 bg-slate-200 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${Math.min(pct, 100)}%`,
                          background: m.targets[0] ? ec(m.targets[0]) : '#94a3b8',
                        }}
                      />
                    </div>
                  </button>
                );
              })}
            </div>

            {activeModel && (() => {
              const m = activeModel;
              const pct = totals.cost > 0 ? (m.cost / totals.cost) * 100 : 0;
              const totalTok = m.inputTokens + m.outputTokens + m.cacheCreationTokens + m.cacheReadTokens;
              const ioRatio = m.outputTokens > 0 ? m.inputTokens / m.outputTokens : 0;
              const ioLabel = ioRatio < 0.1 ? '0:1' : ioRatio > 10 ? '1:0' : `${ioRatio.toFixed(1)}:1`;
              const ioText = ioRatio < 0.3
                ? 'More output than input. Generation-heavy workload.'
                : ioRatio > 3
                ? 'More input than output. Context-heavy workload.'
                : 'Balanced input/output ratio.';
              const rows = [
                { label: 'Input',       cost: m.inputCost,      tokens: m.inputTokens },
                { label: 'Output',      cost: m.outputCost,     tokens: m.outputTokens },
                { label: 'Cache Write', cost: m.cacheWriteCost, tokens: m.cacheCreationTokens },
                { label: 'Cache Read',  cost: m.cacheReadCost,  tokens: m.cacheReadTokens },
              ];
              return (
                <div className="w-full lg:w-72 shrink-0 rounded-xl border border-slate-200 bg-slate-50/80 p-4 space-y-4">
                  <div>
                    <p className="text-sm font-bold text-slate-800 truncate">{m.model}</p>
                    <div className="flex items-center gap-2 mt-1 text-xs text-slate-500">
                      <span className="font-semibold text-slate-700">{pct.toFixed(1)}%</span>
                      <span>usage</span>
                      <span className="text-slate-300">•</span>
                      <span className="font-semibold text-slate-700">{ioLabel}</span>
                      <span>I/O</span>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div className="rounded-lg bg-white border border-slate-200 p-2.5">
                      <p className="text-base font-bold text-slate-800">{fmtCost(m.cost)}</p>
                      <p className="text-[10px] text-slate-400 mt-0.5">Total Cost</p>
                    </div>
                    <div className="rounded-lg bg-white border border-slate-200 p-2.5">
                      <p className="text-base font-bold text-slate-800">{fmtTokens(totalTok)}</p>
                      <p className="text-[10px] text-slate-400 mt-0.5">All Tokens</p>
                    </div>
                  </div>

                  <div>
                    <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest mb-1.5">
                      Token Breakdown
                    </p>
                    <div className="space-y-1">
                      {rows.map(({ label, cost, tokens }) => (
                        <div key={label} className="flex items-center justify-between text-xs">
                          <span className="text-slate-500 w-20">{label}</span>
                          <span className="font-semibold text-slate-700 w-16 text-right">{fmtCost(cost)}</span>
                          <span className="text-slate-400 text-right">{fmtTokens(tokens)}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="rounded-lg bg-white border border-slate-200 p-2.5">
                    <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest mb-1">
                      Input/Output Ratio
                    </p>
                    <p className="text-xs text-slate-600">{ioText}</p>
                  </div>
                </div>
              );
            })()}
          </div>
        </div>
      )}

      {/* ── Detail table ───────────────────────────────────────────────────── */}
      {series.cost.length > 0 && (
        <div className="animate-fade-rise stagger-6 glass-card p-5">
          <SectionTitle>
            {granularity === 'month' ? 'Detail by month' : `Detail — last ${rangeLabel}`}
          </SectionTitle>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-100 text-slate-400">
                  <th className="text-left py-2 pr-4 font-medium">
                    {granularity === 'month' ? 'Month' : 'Date'}
                  </th>
                  <th className="text-left py-2 pr-4 font-medium">Engine</th>
                  <th className="text-right py-2 pr-4 font-medium">Input</th>
                  <th className="text-right py-2 pr-4 font-medium">Output</th>
                  <th className="text-right py-2 font-medium">Cost</th>
                </tr>
              </thead>
              <tbody>
                {(granularity === 'month'
                  ? [...monthly].reverse().map(m => ({
                      key: `${m.month}-${m.target}`, label: m.month, target: m.target,
                      inputTokens: m.inputTokens, outputTokens: m.outputTokens, cost: m.cost,
                    }))
                  : [...rangeDaily].reverse().map(d => ({
                      key: `${d.date}-${d.target}`, label: d.date, target: d.target,
                      inputTokens: d.inputTokens, outputTokens: d.outputTokens, cost: d.cost,
                    }))
                ).map(row => (
                  <tr key={row.key} className="border-b border-slate-50 hover:bg-slate-50/60 transition-colors">
                    <td className="py-1.5 pr-4 font-mono text-slate-500">{row.label}</td>
                    <td className="py-1.5 pr-4">
                      <span className={`px-1.5 py-0.5 text-[10px] font-bold rounded-full uppercase ${eb(row.target)}`}>
                        {row.target}
                      </span>
                    </td>
                    <td className="py-1.5 pr-4 text-right text-slate-600">{fmtTokens(row.inputTokens)}</td>
                    <td className="py-1.5 pr-4 text-right text-slate-600">{fmtTokens(row.outputTokens)}</td>
                    <td className="py-1.5 text-right font-semibold text-slate-700">{fmtCost(row.cost)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default Analytics;
