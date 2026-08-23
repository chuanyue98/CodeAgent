import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import Analytics from '../components/Analytics';
import { toLocalDayString } from '../utils/dateRange';

function jsonResponse(data: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    text: async () => JSON.stringify(data),
    json: async () => data,
  });
}

function dayAgo(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return toLocalDayString(date);
}

function daily(date: string, target: string, cost: number, model = 'claude-opus') {
  return {
    date,
    target,
    inputTokens: 1000,
    outputTokens: 500,
    cacheCreationTokens: 0,
    cacheReadTokens: 0,
    cost,
    modelsUsed: [model],
    modelBreakdowns: [
      {
        modelName: model,
        inputTokens: 1000,
        outputTokens: 500,
        cacheCreationTokens: 0,
        cacheReadTokens: 0,
        cost,
      },
    ],
  };
}

// 2 days ago is inside every range; 45 days ago is inside 90d/all only.
const DAILY = [
  daily(dayAgo(2), 'claude', 10),
  daily(dayAgo(45), 'claude', 100),
];

const MODELS = [
  {
    model: 'claude-opus',
    inputTokens: 2000,
    outputTokens: 1000,
    cacheCreationTokens: 0,
    cacheReadTokens: 0,
    inputCost: 44,
    outputCost: 66,
    cacheWriteCost: 0,
    cacheReadCost: 0,
    cost: 110,
    sessionCount: 2,
    targets: ['claude'],
  },
];

beforeEach(() => {
  globalThis.fetch = vi.fn().mockImplementation((url: string) => {
    if (url.includes('/api/analytics/summary')) return jsonResponse({ session_count: 2 });
    if (url.includes('/api/analytics/engines')) {
      return jsonResponse([
        {
          target: 'claude',
          inputTokens: 2000, outputTokens: 1000,
          cacheCreationTokens: 0, cacheReadTokens: 0,
          cost: 110, sessionCount: 2, models: ['claude-opus'],
        },
      ]);
    }
    if (url.includes('/api/analytics/daily')) return jsonResponse(DAILY);
    if (url.includes('/api/analytics/monthly')) return jsonResponse([]);
    if (url.includes('/api/analytics/sessions')) return jsonResponse([]);
    if (url.includes('/api/analytics/models')) return jsonResponse(MODELS);
    return Promise.reject(new Error(`Unhandled fetch to ${url}`));
  }) as unknown as typeof fetch;
});

afterEach(() => {
  vi.restoreAllMocks();
});

function renderAnalytics() {
  return render(
    <MemoryRouter>
      <Analytics />
    </MemoryRouter>,
  );
}

function statCard(label: string): HTMLElement {
  return screen.getByText(label).closest('div.glass-card') as HTMLElement;
}

function pickRange(label: string) {
  fireEvent.click(screen.getByRole('button', { name: label }));
}

describe('Analytics is one page, not four tabs', () => {
  test('shows every section at once instead of a tab bar', async () => {
    renderAnalytics();
    await screen.findByText('总成本');

    expect(screen.getByText('模型明细')).toBeVisible();
    expect(screen.getByText(/按引擎成本/)).toBeVisible();
    expect(screen.getByText(/按引擎 Token/)).toBeVisible();

    // The old Overview/Daily/Monthly sub-tabs are gone.
    for (const gone of ['Overview', 'Daily', 'Monthly']) {
      expect(screen.queryByRole('button', { name: gone })).not.toBeInTheDocument();
    }
  });

  test('offers the four time ranges', async () => {
    renderAnalytics();
    await screen.findByText('总成本');

    const group = screen.getByRole('group', { name: '时间范围' });
    for (const label of ['7 天', '30 天', '90 天', '全部']) {
      expect(within(group).getByRole('button', { name: label })).toBeVisible();
    }
  });
});

describe('Analytics time range scoping', () => {
  test('defaults to 30 days and counts only rows inside it', async () => {
    renderAnalytics();
    await screen.findByText('总成本');

    // Only the 2-days-ago row ($10) is inside 30 days; the 45-day-old $100 is not.
    expect(within(statCard('总成本')).getByText('$10.00')).toBeVisible();
  });

  test('widening the range pulls in older rows', async () => {
    renderAnalytics();
    await screen.findByText('总成本');

    pickRange('90 天');
    expect(within(statCard('总成本')).getByText('$110.00')).toBeVisible();

    pickRange('7 天');
    expect(within(statCard('总成本')).getByText('$10.00')).toBeVisible();
  });

  test('scopes the engine card to the range, not all-time', async () => {
    renderAnalytics();
    await screen.findByText('总成本');

    // The all-time engine summary says $110; the 30-day view must not.
    // "预估成本" is unique to the engine card (unlike the engine name, which
    // also appears in the pie legend).
    const engineCard = screen.getByText('预估成本').closest('div.glass-card') as HTMLElement;
    expect(within(engineCard).getByText('$10.00')).toBeVisible();
    expect(within(engineCard).queryByText('$110.00')).not.toBeInTheDocument();
  });

  test('scopes the model breakdown and derives its cost split', async () => {
    renderAnalytics();
    await screen.findByText('模型明细');

    fireEvent.click(screen.getByRole('button', { name: /claude-opus/ }));

    const panel = screen.getByText('Token 明细').closest('div') as HTMLElement;
    // Half the all-time tokens sit in range, so half the all-time input cost
    // ($44 over 2000 tokens → $22 over the 1000 in range).
    expect(within(panel).getByText('$22.00')).toBeVisible();
    expect(within(panel).getByText('$33.00')).toBeVisible();
  });

  test('says so when the range is empty rather than showing bare zeros', async () => {
    renderAnalytics();
    await screen.findByText('总成本');

    pickRange('7 天');
    expect(screen.queryByText(/最近 7 天内没有用量/)).not.toBeInTheDocument();
  });
});

describe('Analytics empty range', () => {
  test('distinguishes an empty range from no usage at all', async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/analytics/summary')) return jsonResponse({ session_count: 1 });
      if (url.includes('/api/analytics/engines')) return jsonResponse([]);
      if (url.includes('/api/analytics/daily')) return jsonResponse([daily(dayAgo(120), 'claude', 5)]);
      if (url.includes('/api/analytics/monthly')) return jsonResponse([]);
      if (url.includes('/api/analytics/sessions')) return jsonResponse([]);
      if (url.includes('/api/analytics/models')) return jsonResponse([]);
      return Promise.reject(new Error(`Unhandled fetch to ${url}`));
    }) as unknown as typeof fetch;

    renderAnalytics();

    expect(await screen.findByText(/最近 30 天内没有用量/)).toBeVisible();
    expect(screen.queryByText('还没有用量记录')).not.toBeInTheDocument();
  });
});
