import React, { useMemo, useState } from 'react';
import {
  ArrowDownRight,
  ArrowUpRight,
  Database,
  DollarSign,
  FileText,
  RefreshCw,
  TrendingUp,
} from 'lucide-react';
import ErrorState from './shared/ErrorState';
import LoadingState from './shared/LoadingState';
import { fmtCost, fmtTokens } from '../api/analytics';
import useAnalyticsData from './analytics/useAnalyticsData';
import { StatCard } from './analytics/ChartCards';
import { CostTrendCard, TokensTrendCard } from './analytics/ChartCards';
import EnginePanel from './analytics/EnginePanel';
import ModelBreakdown from './analytics/ModelBreakdown';
import DetailTable from './analytics/DetailTable';
import {
  RANGES,
  activeRangeOf,
  buildRangeEngines,
  buildRangeModels,
  buildSeries,
  computeTotals,
  filterDailyByRange,
  filterSessionsByRange,
  type RangeId,
} from './analytics/rangeStats';

// ── Main component ───────────────────────────────────────────────────────────
const Analytics: React.FC = () => {
  const [range, setRange] = useState<RangeId>('30d');
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const {
    engines, daily, monthly, sessions, modelStats, totalSessions,
    loading, refreshing, error, retry, handleRefresh,
  } = useAnalyticsData();

  const activeRange = activeRangeOf(range);
  const rangeLabel = activeRange.label.toLowerCase();

  // Over a long window a per-day series is unreadable, so the all-time view
  // rolls up by month. This is what the old separate Monthly tab was for.
  const granularity: 'day' | 'month' = range === 'all' ? 'month' : 'day';

  const rangeDaily = useMemo(
    () => filterDailyByRange(daily, activeRange.days),
    [daily, activeRange.days],
  );

  const totals = useMemo(() => computeTotals(rangeDaily), [rangeDaily]);

  const rangeSessions = useMemo(
    () => filterSessionsByRange(sessions, activeRange.days),
    [sessions, activeRange.days],
  );

  // `summary.session_count` is authoritative but all-time only; a narrowed
  // range has to count the fetched window instead.
  const sessionCount = activeRange.days === null ? totalSessions : rangeSessions.length;
  const avgCostPerSession = sessionCount > 0 ? totals.cost / sessionCount : 0;

  const rangeEngines = useMemo(
    () => buildRangeEngines(engines, rangeDaily, rangeSessions, activeRange.days),
    [engines, rangeDaily, rangeSessions, activeRange.days],
  );

  const rangeModels = useMemo(
    () => buildRangeModels(modelStats, rangeDaily, activeRange.days),
    [modelStats, rangeDaily, activeRange.days],
  );

  const series = useMemo(
    () => buildSeries(granularity, monthly, rangeDaily),
    [granularity, monthly, rangeDaily],
  );

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
          aria-label="时间范围"
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
          刷新
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
          <p className="text-sm font-semibold text-slate-800">还没有用量记录</p>
          <p className="max-w-md text-xs leading-5 text-slate-500">
            Token 数量和成本估算读取自各引擎 CLI 在本机写入的会话日志。运行一次代理会话或任务，
            然后点击刷新——生成这些数字不会向任何地方发送数据。
          </p>
        </div>
      )}

      {/* Distinguishes "you have no usage at all" from "nothing in the last
          7 days", which otherwise render as the same wall of zeros. */}
      {hasUsage && !hasRangeUsage && (
        <div className="glass-card flex flex-col items-center gap-1 px-6 py-8 text-center">
          <p className="text-sm font-semibold text-slate-800">最近 {rangeLabel}内没有用量</p>
          <p className="text-xs text-slate-500">
            选择更长的时间范围即可查看更早的记录。
          </p>
        </div>
      )}

      {/* ── Stat cards ─────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        <StatCard
          label="总 Token"
          value={fmtTokens(totals.inputTokens + totals.outputTokens + totals.cacheTokens)}
          sub={`${fmtTokens(totals.inputTokens)} in / ${fmtTokens(totals.outputTokens)} out`}
          Icon={FileText} iconColor="text-blue-600" iconBg="bg-blue-100" stagger="stagger-2"
        />
        <StatCard
          label="总成本" value={fmtCost(totals.cost)}
          sub={`每会话 ~${fmtCost(avgCostPerSession)}`}
          Icon={DollarSign} iconColor="text-green-600" iconBg="bg-green-100" stagger="stagger-3"
        />
        <StatCard
          label="缓存 Token" value={fmtTokens(totals.cacheTokens)}
          sub={`${rangeEngines.length} 个引擎`}
          Icon={Database} iconColor="text-cyan-600" iconBg="bg-cyan-100" stagger="stagger-4"
        />
        <StatCard
          label="输入成本"
          value={fmtCost(rangeModels.reduce((s, m) => s + m.inputCost, 0))}
          sub={`${fmtTokens(totals.inputTokens)} Token`}
          Icon={ArrowDownRight} iconColor="text-purple-600" iconBg="bg-purple-100" stagger="stagger-5"
        />
        <StatCard
          label="输出成本"
          value={fmtCost(rangeModels.reduce((s, m) => s + m.outputCost, 0))}
          sub={`${fmtTokens(totals.outputTokens)} Token`}
          Icon={ArrowUpRight} iconColor="text-orange-600" iconBg="bg-orange-100" stagger="stagger-6"
        />
      </div>

      {/* ── Usage over time ────────────────────────────────────────────────── */}
      <CostTrendCard series={series} granularity={granularity} rangeLabel={rangeLabel} />
      <TokensTrendCard series={series} granularity={granularity} rangeLabel={rangeLabel} />

      {/* ── Engines + distribution ─────────────────────────────────────────── */}
      <EnginePanel
        rangeEngines={rangeEngines}
        pieData={pieData}
        sessionCount={sessionCount}
        avgCostPerSession={avgCostPerSession}
        totalLabel={activeRange.days === null ? '总计' : `最近 ${rangeLabel}`}
        recentSessions={recentSessions}
      />

      {/* ── Model breakdown ────────────────────────────────────────────────── */}
      <ModelBreakdown
        rangeModels={rangeModels}
        selectedModel={selectedModel}
        onSelectModel={setSelectedModel}
        totalCost={totals.cost}
      />

      {/* ── Detail table ───────────────────────────────────────────────────── */}
      <DetailTable
        granularity={granularity}
        monthly={monthly}
        rangeDaily={rangeDaily}
        rangeLabel={rangeLabel}
        hasRows={series.cost.length > 0}
      />
    </div>
  );
};

export default Analytics;
