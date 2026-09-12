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
import { localDayOffset } from '../utils/dateRange';

function day(date: string, overrides: Partial<DailyUsage> = {}): DailyUsage {
  return {
    date,
    target: 'claude',
    inputTokens: 100,
    outputTokens: 50,
    cacheCreationTokens: 10,
    cacheReadTokens: 5,
    modelsUsed: ['sonnet'],
    modelBreakdowns: [
      {
        modelName: 'sonnet',
        inputTokens: 100,
        outputTokens: 50,
        cacheCreationTokens: 10,
        cacheReadTokens: 5,
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
    const iso = (offset: number) => localDayOffset(offset);
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
  test('sums each token class across days', () => {
    expect(computeTotals([day('2024-01-01'), day('2024-01-02')])).toEqual({
      inputTokens: 200,
      outputTokens: 100,
      cacheCreationTokens: 20,
      cacheReadTokens: 10,
    });
  });
});

describe('buildRangeEngines', () => {
  test('aggregates daily rows per engine, busiest first, and counts sessions', () => {
    const daily = [
      day('2024-01-01', { target: 'codex', inputTokens: 10 }),
      day('2024-01-01', { target: 'claude', inputTokens: 500 }),
    ];
    const sessions: SessionUsage[] = [
      { sessionId: 'a', target: 'claude' } as SessionUsage,
      { sessionId: 'b', target: 'claude' } as SessionUsage,
    ];
    const engines = buildRangeEngines([], daily, sessions, 7);
    expect(engines.map(e => e.target)).toEqual(['claude', 'codex']);
    const claude = engines[0];
    expect(claude.sessionCount).toBe(2);
    expect(claude.inputTokens).toBe(500);
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
      sessionCount: 1,
      targets: ['claude'],
    },
  ];

  test('all-time maps the API model stats one-to-one', () => {
    expect(buildRangeModels(modelStats, [], null)).toEqual([
      {
        model: 'sonnet',
        targets: ['claude'],
        inputTokens: 1000,
        outputTokens: 1000,
        cacheCreationTokens: 0,
        cacheReadTokens: 0,
      },
    ]);
  });

  test('a narrowed range sums the daily breakdowns, ranked by input + output', () => {
    // haiku's cache reads dwarf sonnet's whole day, but it did far less work.
    const haiku = {
      modelName: 'haiku', inputTokens: 1, outputTokens: 1,
      cacheCreationTokens: 0, cacheReadTokens: 900,
    };
    const models = buildRangeModels(
      modelStats,
      [day('2024-01-01'), day('2024-01-02', { modelBreakdowns: [haiku] })],
      7,
    );
    expect(models.map(m => m.model)).toEqual(['sonnet', 'haiku']);
    expect(models[0].inputTokens).toBe(100);
    expect(models[0].targets).toEqual(['claude']);
  });
});

describe('buildSeries', () => {
  test('pivots daily rows into per-key token columns per engine', () => {
    const daily = [
      day('2024-01-01', { target: 'claude' }),
      day('2024-01-01', { target: 'codex', inputTokens: 0, outputTokens: 10 }),
      day('2024-01-02', { target: 'claude', inputTokens: 400 }),
    ];
    const series = buildSeries('day', [], daily, null);
    expect(series.engines).toEqual(['claude', 'codex']);
    // codex is 0 on Jan 2, not absent: recharts draws an absent key as a break
    // in the line, which reads as missing data rather than as a quiet day.
    // tokens = input + output per row, accumulated per engine+key.
    expect(series.tokens).toEqual([
      { _key: '2024-01-01', claude: 150, codex: 10 },
      { _key: '2024-01-02', claude: 450, codex: 0 },
    ]);
  });

  test('a day with no work at all still gets a row', () => {
    const twoDaysAgo = localDayOffset(2);

    const series = buildSeries('day', [], [day(twoDaysAgo)], 3);

    // Three days requested, three plotted -- the two idle ones as zeroes.
    expect(series.tokens.map(r => r._key)).toEqual([
      twoDaysAgo,
      localDayOffset(1),
      localDayOffset(0),
    ]);
    expect(series.tokens.map(r => r.claude)).toEqual([150, 0, 0]);
  });

  test('month granularity pivots the monthly rows instead', () => {
    const series = buildSeries(
      'month',
      [{ month: '2024-01', target: 'claude', inputTokens: 1, outputTokens: 1 } as never],
      [day('2024-01-01')],
      null,
    );
    expect(series.tokens).toEqual([{ _key: '2024-01', claude: 2 }]);
  });
});
