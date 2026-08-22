import { renderHook } from '@testing-library/react';
import { afterEach, describe, expect, test, vi } from 'vitest';
import usePolling from '../hooks/usePolling';

function setVisibility(value: DocumentVisibilityState) {
  Object.defineProperty(document, 'visibilityState', {
    value,
    configurable: true,
  });
  document.dispatchEvent(new Event('visibilitychange'));
}

afterEach(() => {
  vi.useRealTimers();
  setVisibility('visible');
});

describe('usePolling', () => {
  test('chains async ticks instead of stacking intervals', async () => {
    vi.useFakeTimers();
    let inFlight = 0;
    let maxInFlight = 0;
    const fn = vi.fn(async () => {
      inFlight += 1;
      maxInFlight = Math.max(maxInFlight, inFlight);
      await new Promise(resolve => setTimeout(resolve, 50));
      inFlight -= 1;
    });
    renderHook(() => usePolling(fn, 100, true, { immediate: false }));
    await vi.advanceTimersByTimeAsync(600);
    // With the old setInterval, several intervals would have fired while
    // each 50ms call was still running. Chained, a call every 100ms after a
    // 50ms handler lands at t=100/250/400/550.
    expect(maxInFlight).toBe(1);
    expect(fn).toHaveBeenCalledTimes(4);
  });

  test('doubles the delay after consecutive failures', async () => {
    vi.useFakeTimers();
    const fn = vi.fn(() => Promise.reject(new Error('down')));
    renderHook(() => usePolling(fn, 1000, true, { immediate: false }));
    await vi.advanceTimersByTimeAsync(1000);
    expect(fn).toHaveBeenCalledTimes(1);
    // First failure backs off to 2x the interval.
    await vi.advanceTimersByTimeAsync(1999);
    expect(fn).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(fn).toHaveBeenCalledTimes(2);
  });

  test('stops ticking while hidden and catches up when visible again', () => {
    vi.useFakeTimers();
    const fn = vi.fn();
    renderHook(() => usePolling(fn, 1000, true, { immediate: false }));
    vi.advanceTimersByTime(1000);
    expect(fn).toHaveBeenCalledTimes(1);

    setVisibility('hidden');
    vi.advanceTimersByTime(5000);
    // A timer scheduled before the tab hid may fire, but must be a no-op and
    // must not schedule another one while still hidden.
    const callsWhileHidden = fn.mock.calls.length;
    expect(callsWhileHidden).toBeLessThanOrEqual(2);

    setVisibility('visible');
    const after = fn.mock.calls.length;
    vi.advanceTimersByTime(5000);
    expect(fn.mock.calls.length).toBeGreaterThan(after);
  });

  test('pollWhenHidden keeps the cadence in the background', () => {
    vi.useFakeTimers();
    const fn = vi.fn();
    renderHook(() => usePolling(fn, 1000, true, { immediate: false, pollWhenHidden: true }));
    setVisibility('hidden');
    vi.advanceTimersByTime(3000);
    expect(fn.mock.calls.length).toBe(3);
  });
});
