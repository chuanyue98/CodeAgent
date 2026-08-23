import { useEffect, useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import ErrorBoundary from '../components/shared/ErrorBoundary';

let fetchAttempts = 0;

/**
 * Models a component whose *data* is flaky rather than its render logic:
 * the first "fetch" (an effect, not the initial render) resolves to bad
 * data and throws on the render it triggers; any later mount's fetch
 * succeeds. `fetchAttempts` lives outside React so it only advances when
 * the component is actually remounted (a fresh effect run) -- not on
 * React's own internal render retries.
 */
function Flaky() {
  const [data, setData] = useState<{ ok: boolean } | null>(null);

  useEffect(() => {
    fetchAttempts += 1;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setData({ ok: fetchAttempts > 1 });
  }, []);

  if (data && !data.ok) {
    throw new Error('bad data from a stale/failed fetch');
  }
  if (!data) return <div>Loading…</div>;
  return <div>Recovered after {fetchAttempts} attempt(s)</div>;
}

beforeEach(() => {
  fetchAttempts = 0;
  // React logs the caught error to console.error; keep test output clean.
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('ErrorBoundary retry', () => {
  test('"重试" remounts children so a transient failure gets a genuine second attempt', async () => {
    render(
      <ErrorBoundary>
        <Flaky />
      </ErrorBoundary>,
    );

    await screen.findByText('出错了');
    expect(fetchAttempts).toBe(1);

    fireEvent.click(screen.getByRole('button', { name: '重试' }));

    await screen.findByText('Recovered after 2 attempt(s)');
    expect(fetchAttempts).toBe(2);
  });

  test('a component that fails deterministically still re-renders on retry (not stuck on stale content)', () => {
    function AlwaysThrows(): never {
      throw new Error('always broken');
    }

    render(
      <ErrorBoundary>
        <AlwaysThrows />
      </ErrorBoundary>,
    );
    expect(screen.getByText('出错了')).toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: '重试' }));

    // Still broken (this component can never succeed) -- but it must show
    // the error UI again, not a blank screen or stale content.
    expect(screen.getByText('出错了')).toBeVisible();
  });
});
