import { localDayOffset } from '../../utils/dateRange';
import type { TranslationKey } from '../../i18n/locales/en';
import type {
  DailyUsage,
  EngineSummary,
  ModelStat,
  MonthlyUsage,
  SessionUsage,
} from '../../api/analytics';

// ── Range ────────────────────────────────────────────────────────────────────
// The page used to have no time filter at all: charts covered all history and
// the detail table was hardcoded to "last 30 days" regardless. One range now
// scopes the whole page, so every number on screen means the same window.
export type RangeId = '7d' | '30d' | '90d' | 'all';

export interface RangeDefinition {
  readonly id: RangeId;
  readonly labelKey: TranslationKey;
  readonly days: number | null;
}

// Readonly all the way down: the range objects are constants, and the React
// Compiler otherwise has to assume any function they are passed to could
// mutate them, which makes it give up on memoizing the whole Usage page.
export const RANGES: readonly RangeDefinition[] = [
  { id: '7d', labelKey: 'range.7d', days: 7 },
  { id: '30d', labelKey: 'range.30d', days: 30 },
  { id: '90d', labelKey: 'range.90d', days: 90 },
  { id: 'all', labelKey: 'range.all', days: null },
];

export function activeRangeOf(id: RangeId): RangeDefinition {
  return RANGES.find(r => r.id === id) ?? RANGES[1];
}

// Split into two flat lookups on purpose. Reading `days` and `labelKey` off
// the *same* object means the React Compiler has to assume the `t()` call the
// label is passed to could also mutate `days`, so it stops memoizing the Usage
// page. Independent maps keep the two values unaliased.
export const RANGE_DAYS: Record<RangeId, number | null> = Object.fromEntries(
  RANGES.map(r => [r.id, r.days]),
) as Record<RangeId, number | null>;

export const RANGE_LABEL_KEYS: Record<RangeId, TranslationKey> = Object.fromEntries(
  RANGES.map(r => [r.id, r.labelKey]),
) as Record<RangeId, TranslationKey>;

/** Per-model totals for the selected range, rebuilt from daily breakdowns. */
export interface RangeModelStat {
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

// A row in the time-series recharts dataset: one string category key (`_key`,
// used as the axis `dataKey`) plus one numeric total per engine, added
// dynamically as engines are discovered. The engine index signature is widened
// to `number | string` only so the literal `_key` property is legal on the
// same type; every access on a dynamic key is numeric by construction.
export type ChartRow = { _key: string; [engine: string]: number | string };

export interface RangeTotals {
  inputTokens: number;
  outputTokens: number;
  cacheTokens: number;
  cost: number;
}

export interface TimeSeries {
  cost: ChartRow[];
  tokens: ChartRow[];
  engines: string[];
}

export function filterDailyByRange(daily: DailyUsage[], days: number | null): DailyUsage[] {
  if (days === null) return daily;
  const cutoff = localDayOffset(days - 1);
  return daily.filter(d => d.date >= cutoff);
}

export function filterSessionsByRange(
  sessions: SessionUsage[],
  days: number | null,
): SessionUsage[] {
  if (days === null) return sessions;
  const cutoff = localDayOffset(days - 1);
  return sessions.filter(s => (s.lastActivity || '').slice(0, 10) >= cutoff);
}

// Every headline number derives from the same filtered set, so the range
// control can't leave a stat card describing a different window than the
// chart beside it.
export function computeTotals(rangeDaily: DailyUsage[]): RangeTotals {
  let inputTokens = 0, outputTokens = 0, cacheTokens = 0, cost = 0;
  for (const d of rangeDaily) {
    inputTokens += d.inputTokens;
    outputTokens += d.outputTokens;
    cacheTokens += d.cacheCreationTokens + d.cacheReadTokens;
    cost += d.cost;
  }
  return { inputTokens, outputTokens, cacheTokens, cost };
}

/** Per-engine totals for the range, rebuilt from daily rows. */
export function buildRangeEngines(
  engines: EngineSummary[],
  rangeDaily: DailyUsage[],
  rangeSessions: SessionUsage[],
  days: number | null,
): EngineSummary[] {
  if (days === null) return engines;
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
}

/**
 * Per-model totals for the range. Token counts come straight from the daily
 * breakdowns; the four cost categories aren't carried there, so they're
 * derived from each model's all-time cost-per-token, which is constant for
 * a given model and already the assumption behind the all-time figures.
 */
export function buildRangeModels(
  modelStats: ModelStat[],
  rangeDaily: DailyUsage[],
  days: number | null,
): RangeModelStat[] {
  if (days === null) {
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
}

/** Day rows in a narrow range, month rows for all time. */
export function buildSeries(
  granularity: 'day' | 'month',
  monthly: MonthlyUsage[],
  rangeDaily: DailyUsage[],
): TimeSeries {
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
}
