import React, { useCallback, useEffect, useMemo, useState } from 'react';
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
import {
  AlertCircle,
  ArrowDownRight,
  ArrowUpRight,
  Clock,
  Database,
  DollarSign,
  FileText,
  RefreshCw,
  Terminal,
  TrendingUp,
} from 'lucide-react';
import { format } from 'date-fns';
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

// ── Stat card ────────────────────────────────────────────────────────────────
function StatCard({
  label, value, sub, Icon, iconColor, iconBg,
}: {
  label: string; value: string; sub?: string;
  Icon: React.ElementType; iconColor: string; iconBg: string;
}) {
  return (
    <div className="glass-card p-4 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 space-y-0.5">
          <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-widest truncate">{label}</p>
          <p className="text-xl font-bold text-slate-800 truncate">{value}</p>
          {sub && <p className="text-[10px] text-slate-500 truncate">{sub}</p>}
        </div>
        <div className={`p-2 rounded-lg shrink-0 ${iconBg}`}>
          <Icon className={`w-4 h-4 ${iconColor}`} />
        </div>
      </div>
    </div>
  );
}

// ── Custom tooltip ────────────────────────────────────────────────────────────
function ChartTooltip({ active, payload, label, isCost }: {
  active?: boolean; payload?: Array<{ name: string; value: number; color: string }>;
  label?: string; isCost?: boolean;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 shadow-lg text-xs">
      <p className="font-semibold mb-1.5 text-slate-700">{label}</p>
      {payload.map((entry, i) => (
        <p key={i} className="flex gap-2 items-center" style={{ color: entry.color }}>
          <span className="w-2 h-2 rounded-full shrink-0" style={{ background: entry.color }} />
          <span className="text-slate-600">{entry.name}:</span>
          <span className="font-semibold">
            {isCost ? fmtCost(entry.value) : fmtTokens(entry.value)}
          </span>
        </p>
      ))}
    </div>
  );
}

// ── Tab bar ──────────────────────────────────────────────────────────────────
type Tab = 'overview' | 'daily' | 'monthly' | 'sessions';
const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'daily', label: 'Daily' },
  { id: 'monthly', label: 'Monthly' },
  { id: 'sessions', label: 'Sessions' },
];

// ── Main component ───────────────────────────────────────────────────────────
const Analytics: React.FC = () => {
  const [tab, setTab] = useState<Tab>('overview');
  const [engines, setEngines] = useState<EngineSummary[]>([]);
  const [daily, setDaily] = useState<DailyUsage[]>([]);
  const [monthly, setMonthly] = useState<MonthlyUsage[]>([]);
  const [sessions, setSessions] = useState<SessionUsage[]>([]);
  const [modelStats, setModelStats] = useState<ModelStat[]>([]);
  const [selectedModel, setSelectedModel] = useState<ModelStat | null>(null);
  const [totalSessions, setTotalSessions] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    try {
      const [summary, eng, day, mon, sess, mods] = await Promise.all([
        fetchSummary(), fetchEngines(), fetchDaily(), fetchMonthly(), fetchSessions(200), fetchModels(),
      ]);
      setEngines(eng); setDaily(day); setMonthly(mon); setSessions(sess); setModelStats(mods);
      setTotalSessions(summary.session_count);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load analytics');
    } finally { setLoading(false); }
  }, []);

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void loadAll(); }, [loadAll]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try { await refreshAnalytics(); await loadAll(); } catch { /* ignore */ }
    finally { setRefreshing(false); }
  };

  const totalCost = useMemo(() => engines.reduce((s, e) => s + e.cost, 0), [engines]);
  const totalInput = useMemo(() => engines.reduce((s, e) => s + e.inputTokens, 0), [engines]);
  const totalOutput = useMemo(() => engines.reduce((s, e) => s + e.outputTokens, 0), [engines]);
  const totalCache = useMemo(
    () => engines.reduce((s, e) => s + e.cacheCreationTokens + e.cacheReadTokens, 0), [engines]
  );

  // ── Daily chart: one series per engine, cost ─────────────────────────────
  const dailyChartData = useMemo(() => {
    const byDate: Record<string, Record<string, number>> = {};
    for (const d of daily) {
      if (!byDate[d.date]) byDate[d.date] = { _date: d.date as unknown as number };
      byDate[d.date][d.target] = (byDate[d.date][d.target] ?? 0) + d.cost;
    }
    return Object.values(byDate).sort((a, b) =>
      String(a._date).localeCompare(String(b._date))
    );
  }, [daily]);

  // ── Daily token chart ────────────────────────────────────────────────────
  const dailyTokenData = useMemo(() => {
    const byDate: Record<string, Record<string, number>> = {};
    for (const d of daily) {
      if (!byDate[d.date]) byDate[d.date] = { _date: d.date as unknown as number };
      byDate[d.date][d.target] =
        (byDate[d.date][d.target] ?? 0) + d.inputTokens + d.outputTokens;
    }
    return Object.values(byDate).sort((a, b) =>
      String(a._date).localeCompare(String(b._date))
    );
  }, [daily]);

  const enginesInDaily = useMemo(() => [...new Set(daily.map((d) => d.target))], [daily]);
  const enginesInMonthly = useMemo(() => [...new Set(monthly.map((m) => m.target))], [monthly]);

  const monthlyChartData = useMemo(() => {
    const byMonth: Record<string, Record<string, number>> = {};
    for (const m of monthly) {
      if (!byMonth[m.month]) byMonth[m.month] = { _month: m.month as unknown as number };
      byMonth[m.month][m.target] = (byMonth[m.month][m.target] ?? 0) + m.cost;
    }
    return Object.values(byMonth).sort((a, b) =>
      String(a._month).localeCompare(String(b._month))
    );
  }, [monthly]);

  const pieData = useMemo(
    () => engines.filter((e) => e.cost > 0).map((e) => ({ name: e.target, value: e.cost })),
    [engines]
  );

  const recentSessions = useMemo(() => sessions.slice(0, 5), [sessions]);
  const avgCostPerSession = totalSessions > 0 ? totalCost / totalSessions : 0;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex flex-col items-center gap-3 text-slate-400 animate-pulse">
          <TrendingUp className="w-7 h-7" />
          <span className="text-sm font-medium">Loading analytics…</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8 flex items-center justify-center">
        <div className="glass-card p-5 flex items-center gap-3 bg-red-50/60 border-red-100">
          <AlertCircle className="w-5 h-5 text-red-500 shrink-0" />
          <span className="font-medium text-red-600 text-sm">{error}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5 pb-6">

      {/* ── Toolbar ────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div className="flex gap-1 bg-slate-100 p-1 rounded-xl">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-4 py-1.5 text-sm font-semibold rounded-lg transition-all ${
                tab === t.id
                  ? 'bg-white text-primary shadow-sm'
                  : 'text-slate-600 hover:text-slate-800'
              }`}
            >
              {t.label}
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

      {/* ── Overview ─────────────────────────────────────────────────────── */}
      {tab === 'overview' && (
        <>
          {/* Stat cards — 5 columns mirroring CCS */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
            <StatCard
              label="Total Tokens" value={fmtTokens(totalInput + totalOutput + totalCache)}
              sub={`${fmtTokens(totalInput)} in / ${fmtTokens(totalOutput)} out`}
              Icon={FileText} iconColor="text-blue-600" iconBg="bg-blue-100"
            />
            <StatCard
              label="Total Cost" value={fmtCost(totalCost)}
              sub={`~${fmtCost(avgCostPerSession)} / session`}
              Icon={DollarSign} iconColor="text-green-600" iconBg="bg-green-100"
            />
            <StatCard
              label="Cache Tokens" value={fmtTokens(totalCache)}
              sub={`${engines.length} engines`}
              Icon={Database} iconColor="text-cyan-600" iconBg="bg-cyan-100"
            />
            <StatCard
              label="Input Cost"
              value={fmtCost(modelStats.reduce((s, m) => s + m.inputCost, 0))}
              sub={fmtTokens(totalInput) + ' tokens'}
              Icon={ArrowDownRight} iconColor="text-purple-600" iconBg="bg-purple-100"
            />
            <StatCard
              label="Output Cost"
              value={fmtCost(modelStats.reduce((s, m) => s + m.outputCost, 0))}
              sub={fmtTokens(totalOutput) + ' tokens'}
              Icon={ArrowUpRight} iconColor="text-orange-600" iconBg="bg-orange-100"
            />
          </div>

          {/* Engine cards + pie */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Engine breakdown cards */}
            <div className="lg:col-span-2 grid grid-cols-2 gap-3">
              {engines.map((eng) => (
                <div key={eng.target} className="glass-card p-4 hover:shadow-md transition-shadow">
                  <div className="flex items-center justify-between mb-3">
                    <span
                      className={`text-[11px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full ${eb(eng.target)}`}
                    >
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
            </div>

            {/* Right column: pie + session stats */}
            <div className="flex flex-col gap-3">
              {/* Donut pie */}
              {pieData.length > 0 && (
                <div className="glass-card p-4">
                  <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-widest mb-2">
                    Cost Distribution
                  </p>
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
                        {pieData.map((entry) => (
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
                    {pieData.map((e) => (
                      <span key={e.name} className="flex items-center gap-1 text-[10px] text-slate-500">
                        <span className="w-2 h-2 rounded-full" style={{ background: ec(e.name) }} />
                        {e.name}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Session mini-stats */}
              <div className="glass-card p-4 flex-1">
                <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-widest mb-3 flex items-center gap-1.5">
                  <Terminal className="w-3 h-3" /> Recent Sessions
                </p>
                <div className="grid grid-cols-2 gap-2 mb-3">
                  <div className="p-2 rounded-lg bg-slate-50 border border-slate-100 text-center">
                    <p className="text-lg font-bold text-blue-600">{totalSessions}</p>
                    <p className="text-[9px] text-slate-600 uppercase tracking-wide">Total</p>
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
                  {recentSessions.map((s) => (
                    <div
                      key={s.sessionId}
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
                </div>
              </div>
            </div>
          </div>

          {/* ── Model Breakdown ─────────────────────────────────────────── */}
          {modelStats.length > 0 && (
            <div className="glass-card p-5">
              <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-widest mb-4">
                Model Breakdown
              </p>
              <div className="flex gap-4">
                {/* Model list */}
                <div className="flex-1 space-y-1.5 min-w-0">
                  {modelStats.map((m) => {
                    const pct = totalCost > 0 ? (m.cost / totalCost) * 100 : 0;
                    const isSelected = selectedModel?.model === m.model;
                    return (
                      <button
                        key={m.model}
                        onClick={() => setSelectedModel(isSelected ? null : m)}
                        className={`w-full text-left rounded-xl px-3 py-2.5 transition-all border ${
                          isSelected
                            ? 'bg-slate-100 border-slate-300'
                            : 'bg-slate-50/60 border-transparent hover:bg-slate-100/70 hover:border-slate-200'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2 mb-1.5">
                          <span className="text-xs font-semibold text-slate-700 truncate">{m.model}</span>
                          <div className="flex items-center gap-2 shrink-0">
                            {m.targets.map((t) => (
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
                              width: `${pct}%`,
                              background: m.targets[0] ? ec(m.targets[0]) : '#94a3b8',
                            }}
                          />
                        </div>
                      </button>
                    );
                  })}
                </div>

                {/* Detail panel */}
                {selectedModel && (() => {
                  const m = selectedModel;
                  const pct = totalCost > 0 ? (m.cost / totalCost) * 100 : 0;
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
                    <div className="w-72 shrink-0 rounded-xl border border-slate-200 bg-slate-50/80 p-4 space-y-4">
                      {/* Header */}
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

                      {/* Cost + Tokens */}
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

                      {/* Token breakdown */}
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

                      {/* I/O analysis */}
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
        </>
      )}

      {/* ── Daily ────────────────────────────────────────────────────────── */}
      {tab === 'daily' && (
        <div className="flex flex-col gap-4">
          {/* Cost chart with gradient fills */}
          <div className="glass-card p-5">
            <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-widest mb-4">
              Daily Cost by Engine
            </p>
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={dailyChartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                <defs>
                  {enginesInDaily.map((eng) => (
                    <linearGradient key={eng} id={`grad-${eng}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={ec(eng)} stopOpacity={0.5} />
                      <stop offset="95%" stopColor={ec(eng)} stopOpacity={0.05} />
                    </linearGradient>
                  ))}
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis
                  dataKey="_date" tick={{ fontSize: 11 }} tickLine={false}
                  tickFormatter={(v) => formatDate(String(v))}
                />
                <YAxis
                  tick={{ fontSize: 11 }} tickLine={false}
                  tickFormatter={(v) => `$${(v as number).toFixed(0)}`}
                  width={45}
                />
                <Tooltip
                  content={(props) => (
                    <ChartTooltip
                      active={props.active}
                      payload={props.payload as unknown as Array<{ name: string; value: number; color: string }>}
                      label={props.label != null ? formatDate(String(props.label)) : undefined}
                      isCost
                    />
                  )}
                />
                {enginesInDaily.map((eng) => (
                  <Area
                    key={eng} type="monotone" dataKey={eng} name={eng}
                    stroke={ec(eng)} strokeWidth={2}
                    fill={`url(#grad-${eng})`}
                  />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Token chart */}
          <div className="glass-card p-5">
            <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-widest mb-4">
              Daily Tokens by Engine
            </p>
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={dailyTokenData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                <defs>
                  {enginesInDaily.map((eng) => (
                    <linearGradient key={eng} id={`tgrad-${eng}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={ec(eng)} stopOpacity={0.4} />
                      <stop offset="95%" stopColor={ec(eng)} stopOpacity={0.02} />
                    </linearGradient>
                  ))}
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="_date" tick={{ fontSize: 11 }} tickLine={false}
                  tickFormatter={(v) => formatDate(String(v))} />
                <YAxis tick={{ fontSize: 11 }} tickLine={false}
                  tickFormatter={(v) => fmtTokens(v as number)} width={45} />
                <Tooltip
                  content={(props) => (
                    <ChartTooltip
                      active={props.active}
                      payload={props.payload as unknown as Array<{ name: string; value: number; color: string }>}
                      label={props.label != null ? formatDate(String(props.label)) : undefined}
                    />
                  )}
                />
                {enginesInDaily.map((eng) => (
                  <Area key={eng} type="monotone" dataKey={eng} name={eng}
                    stroke={ec(eng)} strokeWidth={2} fill={`url(#tgrad-${eng})`} />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Detail table */}
          <div className="glass-card p-5">
            <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-widest mb-3">
              Detail (last 30 days)
            </p>
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-100 text-slate-400">
                  <th className="text-left py-2 pr-4 font-medium">Date</th>
                  <th className="text-left py-2 pr-4 font-medium">Engine</th>
                  <th className="text-right py-2 pr-4 font-medium">Input</th>
                  <th className="text-right py-2 pr-4 font-medium">Output</th>
                  <th className="text-right py-2 font-medium">Cost</th>
                </tr>
              </thead>
              <tbody>
                {[...daily].reverse().slice(0, 30).map((d, i) => (
                  <tr key={i} className="border-b border-slate-50 hover:bg-slate-50/60 transition-colors">
                    <td className="py-1.5 pr-4 font-mono text-slate-500">{d.date}</td>
                    <td className="py-1.5 pr-4">
                      <span className={`px-1.5 py-0.5 text-[10px] font-bold rounded-full uppercase ${eb(d.target)}`}>
                        {d.target}
                      </span>
                    </td>
                    <td className="py-1.5 pr-4 text-right text-slate-600">{fmtTokens(d.inputTokens)}</td>
                    <td className="py-1.5 pr-4 text-right text-slate-600">{fmtTokens(d.outputTokens)}</td>
                    <td className="py-1.5 text-right font-semibold text-slate-700">{fmtCost(d.cost)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Monthly ──────────────────────────────────────────────────────── */}
      {tab === 'monthly' && (
        <div className="flex flex-col gap-4">
          <div className="glass-card p-5">
            <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-widest mb-4">
              Monthly Cost by Engine
            </p>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={monthlyChartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="_month" tick={{ fontSize: 11 }} tickLine={false}
                  tickFormatter={(v) => formatMonth(String(v))} />
                <YAxis tick={{ fontSize: 11 }} tickLine={false}
                  tickFormatter={(v) => `$${(v as number).toFixed(0)}`} width={45} />
                <Tooltip
                  content={(props) => (
                    <ChartTooltip
                      active={props.active}
                      payload={props.payload as unknown as Array<{ name: string; value: number; color: string }>}
                      label={props.label != null ? formatMonth(String(props.label)) : undefined}
                      isCost
                    />
                  )}
                />
                {enginesInMonthly.map((eng) => (
                  <Bar key={eng} dataKey={eng} name={eng} stackId="a"
                    fill={ec(eng)} radius={eng === enginesInMonthly.at(-1) ? [3, 3, 0, 0] : [0, 0, 0, 0]} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="glass-card p-5">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-100 text-slate-400">
                  <th className="text-left py-2 pr-4 font-medium">Month</th>
                  <th className="text-left py-2 pr-4 font-medium">Engine</th>
                  <th className="text-right py-2 pr-4 font-medium">Input</th>
                  <th className="text-right py-2 pr-4 font-medium">Output</th>
                  <th className="text-right py-2 font-medium">Cost</th>
                </tr>
              </thead>
              <tbody>
                {[...monthly].reverse().map((m, i) => (
                  <tr key={i} className="border-b border-slate-50 hover:bg-slate-50/60 transition-colors">
                    <td className="py-1.5 pr-4 font-mono text-slate-500">{m.month}</td>
                    <td className="py-1.5 pr-4">
                      <span className={`px-1.5 py-0.5 text-[10px] font-bold rounded-full uppercase ${eb(m.target)}`}>
                        {m.target}
                      </span>
                    </td>
                    <td className="py-1.5 pr-4 text-right text-slate-600">{fmtTokens(m.inputTokens)}</td>
                    <td className="py-1.5 pr-4 text-right text-slate-600">{fmtTokens(m.outputTokens)}</td>
                    <td className="py-1.5 text-right font-semibold text-slate-700">{fmtCost(m.cost)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Sessions ─────────────────────────────────────────────────────── */}
      {tab === 'sessions' && (
        <div className="glass-card p-5">
          <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-widest mb-4">
            Sessions ({sessions.length} shown)
          </p>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-100 text-slate-400">
                <th className="text-left py-2 pr-3 font-medium">Engine</th>
                <th className="text-left py-2 pr-3 font-medium">Project</th>
                <th className="text-left py-2 pr-3 font-medium">Model</th>
                <th className="text-right py-2 pr-3 font-medium">Tokens</th>
                <th className="text-right py-2 pr-3 font-medium">Cost</th>
                <th className="text-right py-2 font-medium">Last Active</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s, i) => (
                <tr key={i} className="border-b border-slate-50 hover:bg-slate-50/60 transition-colors">
                  <td className="py-1.5 pr-3">
                    <span className={`px-1.5 py-0.5 text-[10px] font-bold rounded-full uppercase ${eb(s.target)}`}>
                      {s.target}
                    </span>
                  </td>
                  <td className="py-1.5 pr-3 max-w-[140px]">
                    <span className="truncate block text-slate-600 font-medium" title={s.projectPath}>
                      {s.projectPath.split(/[\\/]/).pop() || s.projectPath || '—'}
                    </span>
                  </td>
                  <td className="py-1.5 pr-3 max-w-[120px]">
                    <span className="truncate block text-slate-400" title={s.modelsUsed[0]}>
                      {s.modelsUsed[0] ?? '—'}
                    </span>
                  </td>
                  <td className="py-1.5 pr-3 text-right text-slate-600 font-mono">
                    {fmtTokens(s.inputTokens + s.outputTokens)}
                  </td>
                  <td className="py-1.5 pr-3 text-right font-semibold text-slate-700">
                    {fmtCost(s.cost)}
                  </td>
                  <td className="py-1.5 text-right text-slate-400">{timeAgo(s.lastActivity)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default Analytics;
