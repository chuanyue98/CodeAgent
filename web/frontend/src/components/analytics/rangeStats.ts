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

/**
 * Input + output tokens: the work a model did. Cache reads run to billions on
 * long sessions, so rankings and shares that counted them would bury it.
 */
export function ioTokens(usage: { inputTokens: number; outputTokens: number }): number {
  return usage.inputTokens + usage.outputTokens;
}

/** Per-model totals for the selected range, rebuilt from daily breakdowns. */
export interface RangeModelStat {
  model: string;
  targets: string[];
  inputTokens: number;
  outputTokens: number;
  cacheCreationTokens: number;
  cacheReadTokens: number;
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
  cacheCreationTokens: number;
  cacheReadTokens: number;
}

export interface TimeSeries {
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
  let inputTokens = 0, outputTokens = 0, cacheCreationTokens = 0, cacheReadTokens = 0;
  for (const d of rangeDaily) {
    inputTokens += d.inputTokens;
    outputTokens += d.outputTokens;
    cacheCreationTokens += d.cacheCreationTokens;
    cacheReadTokens += d.cacheReadTokens;
  }
  return { inputTokens, outputTokens, cacheCreationTokens, cacheReadTokens };
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
      sessionCount: 0, models: [],
    };
    current.inputTokens += d.inputTokens;
    current.outputTokens += d.outputTokens;
    current.cacheCreationTokens += d.cacheCreationTokens;
    current.cacheReadTokens += d.cacheReadTokens;
    current.models = [...new Set([...current.models, ...d.modelsUsed])];
    byTarget.set(d.target, current);
  }
  for (const session of rangeSessions) {
    const entry = byTarget.get(session.target);
    if (entry) entry.sessionCount += 1;
  }
  return [...byTarget.values()].sort((a, b) => ioTokens(b) - ioTokens(a));
}

/** Per-model totals for the range, summed from the daily breakdowns. */
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
    }));
  }

  const byModel = new Map<string, RangeModelStat>();
  for (const d of rangeDaily) {
    for (const bd of d.modelBreakdowns ?? []) {
      const current = byModel.get(bd.modelName) ?? {
        model: bd.modelName, targets: [],
        inputTokens: 0, outputTokens: 0, cacheCreationTokens: 0, cacheReadTokens: 0,
      };
      current.inputTokens += bd.inputTokens;
      current.outputTokens += bd.outputTokens;
      current.cacheCreationTokens += bd.cacheCreationTokens;
      current.cacheReadTokens += bd.cacheReadTokens;
      if (!current.targets.includes(d.target)) current.targets.push(d.target);
      byModel.set(bd.modelName, current);
    }
  }

  return [...byModel.values()].sort((a, b) => ioTokens(b) - ioTokens(a));
}

/** Day rows in a narrow range, month rows for all time. */
export function buildSeries(
  granularity: 'day' | 'month',
  monthly: MonthlyUsage[],
  rangeDaily: DailyUsage[],
  days: number | null,
): TimeSeries {
  const rows = granularity === 'month'
    ? monthly.map(m => ({ key: m.month, target: m.target, tokens: ioTokens(m) }))
    : rangeDaily.map(d => ({ key: d.date, target: d.target, tokens: ioTokens(d) }));

  const tokens: Record<string, ChartRow> = {};
  for (const row of rows) {
    tokens[row.key] ??= { _key: row.key };
    tokens[row.key][row.target] = Number(tokens[row.key][row.target] ?? 0) + row.tokens;
  }
  const engines = [...new Set(rows.map(r => r.target))];

  // A day nobody worked has no row at all, and a day only one engine worked
  // leaves the others undefined -- both of which recharts draws as a break in
  // the line. "No work" and "no data" then look identical, and the gaps make
  // the surrounding points read as one continuous run. Fill the calendar and
  // every engine on it, so a quiet day is plotted as the zero it was.
  if (granularity === 'day' && days !== null) {
    for (const key of calendarKeys(days)) {
      tokens[key] ??= { _key: key };
    }
  }
  for (const row of Object.values(tokens)) {
    for (const engine of engines) row[engine] ??= 0;
  }

  return {
    tokens: Object.values(tokens).sort((a, b) => a._key.localeCompare(b._key)),
    engines,
  };
}

/** Every `YYYY-MM-DD` in the trailing `days`-day window, oldest first. */
function calendarKeys(days: number): string[] {
  return Array.from({ length: days }, (_, i) => localDayOffset(days - 1 - i));
}
