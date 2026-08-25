import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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

let toolRequests: string[] = [];

const TOOL_USAGE = {
  tools: [
    { name: 'Bash', count: 80, byEngine: { claude: 50, codex: 30 } },
    { name: 'Read', count: 32, byEngine: { claude: 32 } },
  ],
  totalCalls: 112,
  sessions: 9,
  engines: { claude: 82, codex: 30 },
};

beforeEach(() => {
  toolRequests = [];
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
    if (url.includes('/api/analytics/sessions'))
      return jsonResponse({ sessions: [], nextCursor: null, total: 0 });
    if (url.includes('/api/analytics/models')) return jsonResponse(MODELS);
    if (url.includes('/api/analytics/tools')) {
      toolRequests.push(url);
      return jsonResponse(TOOL_USAGE);
    }
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
    await screen.findByText('Total Cost');

    expect(screen.getByText('Model Breakdown')).toBeVisible();
    expect(screen.getByText(/Cost by engine/)).toBeVisible();
    expect(screen.getByText(/Tokens by engine/)).toBeVisible();

    // The old Overview/Daily/Monthly/Sessions sub-tabs are gone.
    for (const gone of ['Overview', 'Daily', 'Monthly']) {
      expect(screen.queryByRole('button', { name: gone })).not.toBeInTheDocument();
    }
  });

  test('offers the four time ranges', async () => {
    renderAnalytics();
    await screen.findByText('Total Cost');

    const group = screen.getByRole('group', { name: 'Time range' });
    for (const label of ['7 days', '30 days', '90 days', 'All time']) {
      expect(within(group).getByRole('button', { name: label })).toBeVisible();
    }
  });
});

describe('Analytics time range scoping', () => {
  test('defaults to 30 days and counts only rows inside it', async () => {
    renderAnalytics();
    await screen.findByText('Total Cost');

    // Only the 2-days-ago row ($10) is inside 30 days; the 45-day-old $100 is not.
    expect(within(statCard('Total Cost')).getByText('$10.00')).toBeVisible();
  });

  test('widening the range pulls in older rows', async () => {
    renderAnalytics();
    await screen.findByText('Total Cost');

    pickRange('90 days');
    expect(within(statCard('Total Cost')).getByText('$110.00')).toBeVisible();

    pickRange('7 days');
    expect(within(statCard('Total Cost')).getByText('$10.00')).toBeVisible();
  });

  test('scopes the engine card to the range, not all-time', async () => {
    renderAnalytics();
    await screen.findByText('Total Cost');

    // The all-time engine summary says $110; the 30-day view must not.
    // "Est. Cost" is unique to the engine card (unlike the engine name, which
    // also appears in the pie legend).
    const engineCard = screen.getByText('Est. Cost').closest('div.glass-card') as HTMLElement;
    expect(within(engineCard).getByText('$10.00')).toBeVisible();
    expect(within(engineCard).queryByText('$110.00')).not.toBeInTheDocument();
  });

  test('scopes the model breakdown and derives its cost split', async () => {
    renderAnalytics();
    await screen.findByText('Model Breakdown');

    fireEvent.click(screen.getByRole('button', { name: /claude-opus/ }));

    const panel = screen.getByText('Token Breakdown').closest('div') as HTMLElement;
    // Half the all-time tokens sit in range, so half the all-time input cost
    // ($44 over 2000 tokens → $22 over the 1000 in range).
    expect(within(panel).getByText('$22.00')).toBeVisible();
    expect(within(panel).getByText('$33.00')).toBeVisible();
  });

  test('says so when the range is empty rather than showing bare zeros', async () => {
    renderAnalytics();
    await screen.findByText('Total Cost');

    pickRange('7 days');
    expect(screen.queryByText(/No usage in the last/)).not.toBeInTheDocument();
  });
});

describe('Analytics empty range', () => {
  test('distinguishes an empty range from no usage at all', async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/analytics/summary')) return jsonResponse({ session_count: 1 });
      if (url.includes('/api/analytics/engines')) return jsonResponse([]);
      if (url.includes('/api/analytics/daily')) return jsonResponse([daily(dayAgo(120), 'claude', 5)]);
      if (url.includes('/api/analytics/monthly')) return jsonResponse([]);
      if (url.includes('/api/analytics/sessions'))
      return jsonResponse({ sessions: [], nextCursor: null, total: 0 });
      if (url.includes('/api/analytics/models')) return jsonResponse([]);
      if (url.includes('/api/analytics/tools')) {
        toolRequests.push(url);
        return jsonResponse(TOOL_USAGE);
      }
      return Promise.reject(new Error(`Unhandled fetch to ${url}`));
    }) as unknown as typeof fetch;

    renderAnalytics();

    expect(await screen.findByText(/No usage in the last 30 days/)).toBeVisible();
    expect(screen.queryByText('No usage recorded yet')).not.toBeInTheDocument();
  });
});

describe('Analytics tool ranking', () => {
  test('ranks tools and shows the per-engine split', async () => {
    renderAnalytics();

    expect(await screen.findByText('Tool usage')).toBeVisible();
    expect(await screen.findByText('Bash')).toBeVisible();
    expect(screen.getByText('Read')).toBeVisible();

    // The cross-engine split is the reason this exists: a single vendor CLI
    // can only ever report its own column.
    expect(screen.getByText(/Claude 50/)).toBeVisible();
    expect(screen.getByText(/Codex 30/)).toBeVisible();
  });

  test('re-counts when the range changes', async () => {
    renderAnalytics();
    await screen.findByText('Bash');

    expect(toolRequests.some(url => url.includes('days=30'))).toBe(true);

    fireEvent.click(screen.getByRole('button', { name: '7 days' }));

    await waitFor(() => {
      expect(toolRequests.some(url => url.includes('days=7'))).toBe(true);
    });
  });
});
