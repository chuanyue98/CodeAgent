import { describe, expect, test } from 'vitest';
import {
  activeRangeOf,
  buildRangeEngines,
  buildRangeModels,
  buildSeries,
  computeTotals,
  filterDailyByRange,
} from '../components/analytics/rangeStats';
import type { DailyUsage, ModelStat, SessionUsage } from '../api/analytics';

function day(date: string, overrides: Partial<DailyUsage> = {}): DailyUsage {
  return {
    date,
    target: 'claude',
    inputTokens: 100,
    outputTokens: 50,
    cacheCreationTokens: 10,
    cacheReadTokens: 5,
    cost: 1,
    modelsUsed: ['sonnet'],
    modelBreakdowns: [
      {
        modelName: 'sonnet',
        inputTokens: 100,
        outputTokens: 50,
        cacheCreationTokens: 10,
        cacheReadTokens: 5,
        cost: 1,
      },
    ],
    ...overrides,
  };
}

describe('activeRangeOf', () => {
  test('maps ids to definitions and falls back to 30d', () => {
    expect(activeRangeOf('7d').days).toBe(7);
    expect(activeRangeOf('all').days).toBeNull();
    expect(activeRangeOf('bogus' as never).id).toBe('30d');
  });
});

describe('filterDailyByRange', () => {
  test('keeps only days at or after the window cutoff', () => {
    const today = new Date();
    const iso = (offset: number) =>
      new Date(today.getTime() - offset * 86400000).toISOString().slice(0, 10);
    const daily = [day(iso(0)), day(iso(6)), day(iso(7)), day(iso(30))];
    // localDayOffset(6) with days=7 keeps exactly the last 7 days.
    expect(filterDailyByRange(daily, 7).map(d => d.date)).toEqual([iso(0), iso(6)]);
  });

  test('returns everything for all-time', () => {
    const daily = [day('2024-01-01'), day('2024-05-01')];
    expect(filterDailyByRange(daily, null)).toHaveLength(2);
  });
});

describe('computeTotals', () => {
  test('sums token classes and cost across days', () => {
    const totals = computeTotals([day('2024-01-01'), day('2024-01-02')]);
    expect(totals.inputTokens).toBe(200);
    expect(totals.outputTokens).toBe(100);
    expect(totals.cacheTokens).toBe(30);
    expect(totals.cost).toBe(2);
  });
});

describe('buildRangeEngines', () => {
  test('aggregates daily rows per engine and counts sessions', () => {
    const daily = [
      day('2024-01-01', { target: 'claude', cost: 2 }),
      day('2024-01-01', { target: 'codex', cost: 1, inputTokens: 10 }),
    ];
    const sessions: SessionUsage[] = [
      { sessionId: 'a', target: 'claude' } as SessionUsage,
      { sessionId: 'b', target: 'claude' } as SessionUsage,
    ];
    const engines = buildRangeEngines([], daily, sessions, 7);
    expect(engines.map(e => e.target)).toEqual(['claude', 'codex']);
    const claude = engines[0];
    expect(claude.sessionCount).toBe(2);
    expect(claude.cost).toBe(2);
    expect(claude.models).toEqual(['sonnet']);
  });

  test('passes all-time engine summaries through untouched', () => {
    const engines = [{ target: 'codex', sessionCount: 9 }];
    expect(buildRangeEngines(engines as never, [], [], null)).toBe(engines);
  });
});

describe('buildRangeModels', () => {
  const modelStats: ModelStat[] = [
    {
      model: 'sonnet',
      inputTokens: 1000,
      outputTokens: 1000,
      cacheCreationTokens: 0,
      cacheReadTokens: 0,
      inputCost: 3,
      outputCost: 15,
      cacheWriteCost: 0,
      cacheReadCost: 0,
      cost: 18,
      sessionCount: 1,
      targets: ['claude'],
    },
  ];

  test('all-time maps the API model stats one-to-one', () => {
    const models = buildRangeModels(modelStats, [], null);
    expect(models).toHaveLength(1);
    expect(models[0].inputCost).toBe(3);
    expect(models[0].outputCost).toBe(15);
  });

  test('a narrowed range derives cost categories from all-time rates', () => {
    // sonnet all-time: $3 per 1000 input tokens, $15 per 1000 output tokens.
    const models = buildRangeModels(modelStats, [day('2024-01-01')], 7);
    expect(models).toHaveLength(1);
    const sonnet = models[0];
    expect(sonnet.inputTokens).toBe(100);
    expect(sonnet.inputCost).toBeCloseTo(0.3);
    expect(sonnet.outputCost).toBeCloseTo(0.75);
    expect(sonnet.targets).toEqual(['claude']);
  });
});

describe('buildSeries', () => {
  test('pivots daily rows into per-key cost/tokens columns per engine', () => {
    const daily = [
      day('2024-01-01', { target: 'claude', cost: 1 }),
      day('2024-01-01', { target: 'codex', cost: 2, inputTokens: 0, outputTokens: 10 }),
      day('2024-01-02', { target: 'claude', cost: 4 }),
    ];
    const series = buildSeries('day', [], daily);
    expect(series.engines).toEqual(['claude', 'codex']);
    expect(series.cost).toEqual([
      { _key: '2024-01-01', claude: 1, codex: 2 },
      { _key: '2024-01-02', claude: 4 },
    ]);
    // tokens = input + output per row, accumulated per engine+key.
    expect(series.tokens[0]).toEqual({ _key: '2024-01-01', claude: 150, codex: 10 });
  });

  test('month granularity pivots the monthly rows instead', () => {
    const series = buildSeries(
      'month',
      [{ month: '2024-01', target: 'claude', inputTokens: 1, outputTokens: 1, cost: 5 } as never],
      [day('2024-01-01')],
    );
    expect(series.cost).toEqual([{ _key: '2024-01', claude: 5 }]);
  });
});
