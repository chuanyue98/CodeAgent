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
import { useT } from '../i18n/context';
import useAnalyticsData from './analytics/useAnalyticsData';
import { StatCard } from './analytics/ChartCards';
import { CostTrendCard, TokensTrendCard } from './analytics/ChartCards';
import EnginePanel from './analytics/EnginePanel';
import ModelBreakdown from './analytics/ModelBreakdown';
import DetailTable from './analytics/DetailTable';
import {
  RANGES,
  RANGE_DAYS,
  RANGE_LABEL_KEYS,
  buildRangeEngines,
  buildRangeModels,
  buildSeries,
  computeTotals,
  filterDailyByRange,
  filterSessionsByRange,
  type RangeId,
} from './analytics/rangeStats';
import ToolRanking from './analytics/ToolRanking';

// ── Main component ───────────────────────────────────────────────────────────
const Analytics: React.FC = () => {
  const [range, setRange] = useState<RangeId>('30d');
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const {
    engines, daily, monthly, sessions, modelStats, totalSessions,
    loading, refreshing, error, retry, handleRefresh,
  } = useAnalyticsData();
  const t = useT();

  // Read from two separate maps rather than off one range object — see the
  // note on RANGE_DAYS for why sharing the object costs the page its
  // memoization.
  const rangeDays = RANGE_DAYS[range];

  // Over a long window a per-day series is unreadable, so the all-time view
  // rolls up by month. This is what the old separate Monthly tab was for.
  const granularity: 'day' | 'month' = range === 'all' ? 'month' : 'day';

  const rangeDaily = useMemo(
    () => filterDailyByRange(daily, rangeDays),
    [daily, rangeDays],
  );

  const totals = useMemo(() => computeTotals(rangeDaily), [rangeDaily]);

  const rangeSessions = useMemo(
    () => filterSessionsByRange(sessions, rangeDays),
    [sessions, rangeDays],
  );

  // `summary.session_count` is authoritative but all-time only; a narrowed
  // range has to count the fetched window instead.
  const sessionCount = rangeDays === null ? totalSessions : rangeSessions.length;
  const avgCostPerSession = sessionCount > 0 ? totals.cost / sessionCount : 0;

  const rangeEngines = useMemo(
    () => buildRangeEngines(engines, rangeDaily, rangeSessions, rangeDays),
    [engines, rangeDaily, rangeSessions, rangeDays],
  );

  const rangeModels = useMemo(
    () => buildRangeModels(modelStats, rangeDaily, rangeDays),
    [modelStats, rangeDaily, rangeDays],
  );

  const rangeLabel = t(RANGE_LABEL_KEYS[range]).toLowerCase();

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

      {/* ── Toolbar ───────────────────────────────────────────────────────────
          Pinned: the range buttons govern every panel below them, and this
          page is several screens tall — changing the range meant scrolling
          back up to the only control that could do it. Opaque rather than
          blurred, so a pinned bar does not re-filter the page behind it on
          every scrolled frame. */}
      <div className="animate-fade-rise stagger-1 sticky top-0 z-20 -mx-1 flex flex-wrap items-center justify-between gap-2 bg-background px-1 py-2">
        <div
          className="flex gap-1 bg-slate-100 p-1 rounded-xl"
          role="group"
          aria-label={t('analytics.timeRange')}
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
              {t(r.labelKey)}
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
          {t('common.refresh')}
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
          <p className="text-sm font-semibold text-slate-800">{t('analytics.noUsageTitle')}</p>
          <p className="max-w-md text-xs leading-5 text-slate-500">
            {t('analytics.noUsageBody')}
          </p>
        </div>
      )}

      {/* Distinguishes "you have no usage at all" from "nothing in the last
          7 days", which otherwise render as the same wall of zeros. */}
      {hasUsage && !hasRangeUsage && (
        <div className="glass-card flex flex-col items-center gap-1 px-6 py-8 text-center">
          <p className="text-sm font-semibold text-slate-800">{t('analytics.emptyRangeTitle', { range: rangeLabel })}</p>
          <p className="text-xs text-slate-500">
            {t('analytics.emptyRangeBody')}
          </p>
        </div>
      )}

      {/* ── Stat cards ─────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        <StatCard
          label={t('analytics.totalTokens')}
          value={fmtTokens(totals.inputTokens + totals.outputTokens + totals.cacheTokens)}
          sub={`${fmtTokens(totals.inputTokens)} in / ${fmtTokens(totals.outputTokens)} out`}
          Icon={FileText} iconColor="text-blue-600" iconBg="bg-blue-100" stagger="stagger-2"
        />
        <StatCard
          label={t('analytics.totalCost')} value={fmtCost(totals.cost)}
          sub={t('analytics.perSession', { cost: fmtCost(avgCostPerSession) })}
          Icon={DollarSign} iconColor="text-green-600" iconBg="bg-green-100" stagger="stagger-3"
        />
        <StatCard
          label={t('analytics.cacheTokens')} value={fmtTokens(totals.cacheTokens)}
          sub={rangeEngines.length === 1
            ? t('analytics.engineCountOne', { count: rangeEngines.length })
            : t('analytics.engineCount', { count: rangeEngines.length })}
          Icon={Database} iconColor="text-cyan-600" iconBg="bg-cyan-100" stagger="stagger-4"
        />
        <StatCard
          label={t('analytics.inputCost')}
          value={fmtCost(rangeModels.reduce((s, m) => s + m.inputCost, 0))}
          sub={`${fmtTokens(totals.inputTokens)} Token`}
          Icon={ArrowDownRight} iconColor="text-purple-600" iconBg="bg-purple-100" stagger="stagger-5"
        />
        <StatCard
          label={t('analytics.outputCost')}
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
        totalLabel={rangeDays === null ? t('analytics.total') : t('analytics.lastRange', { range: rangeLabel })}
        recentSessions={recentSessions}
      />

      {/* ── Model breakdown ────────────────────────────────────────────────── */}
      <ModelBreakdown
        rangeModels={rangeModels}
        selectedModel={selectedModel}
        onSelectModel={setSelectedModel}
        totalCost={totals.cost}
      />

      {/* ── Tool usage ─────────────────────────────────────────────────────── */}
      <ToolRanking rangeDays={rangeDays} rangeLabel={rangeLabel} />

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
