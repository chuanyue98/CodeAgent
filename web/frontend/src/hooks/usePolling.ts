import { useEffect, useRef } from 'react';

interface UsePollingOptions {
  /**
   * Call `fn` once immediately whenever polling (re)starts (i.e. on mount,
   * or when `enabled` flips from false to true), in addition to on the
   * recurring interval. Defaults to true, matching the "fetch on mount,
   * then refresh on a timer" pattern used across the app.
   */
  immediate?: boolean;
  /**
   * Upper bound for the failure backoff. A failing endpoint doubles its
   * delay per consecutive failure up to this cap instead of hammering a
   * struggling server at full cadence. Defaults to 30s.
   */
  maxBackoffMs?: number;
  /**
   * Keep polling while the tab is hidden (defaults to false). Background
   * tabs are paused and fire one catch-up call when they become visible
   * again; enable for data that must stay current even unseen.
   */
  pollWhenHidden?: boolean;
}

/**
 * Shared polling hook: calls `fn` on a recurring `intervalMs` timer while
 * `enabled` is true, and cleans up automatically on unmount, when `enabled`
 * flips to false, or when `intervalMs` changes.
 *
 * `fn` is read through a ref, so callers don't need to memoize it (or
 * list unrelated state in its dependency array) just to avoid the timer
 * being torn down and recreated on every unrelated render.
 *
 * When `fn` returns a promise, the next tick is scheduled only after it
 * settles (no request stacking on slow endpoints), consecutive failures
 * back off exponentially up to `maxBackoffMs`, and the loop pauses while
 * the tab is hidden unless `pollWhenHidden` is set — a catch-up call fires
 * as soon as the tab is visible again.
 */
function usePolling(
  fn: () => void | Promise<unknown>,
  intervalMs: number,
  enabled = true,
  options: UsePollingOptions = {},
): void {
  const { immediate = true, maxBackoffMs = 30_000, pollWhenHidden = false } = options;
  const fnRef = useRef(fn);
  useEffect(() => {
    fnRef.current = fn;
  }, [fn]);

  useEffect(() => {
    if (!enabled) return;
    let disposed = false;
    let failures = 0;
    let timer: number | undefined;

    const schedule = () => {
      const delay =
        failures === 0
          ? intervalMs
          : Math.min(intervalMs * 2 ** failures, maxBackoffMs);
      timer = window.setTimeout(tick, delay);
    };

    const tick = () => {
      timer = undefined;
      if (disposed) return;
      if (!pollWhenHidden && document.visibilityState !== 'visible') {
        // Paused: visibilitychange resumes the loop with a catch-up call.
        return;
      }
      let settled = false;
      const finish = (failed: boolean) => {
        if (disposed || settled) return;
        settled = true;
        failures = failed ? failures + 1 : 0;
        schedule();
      };
      try {
        const result = fnRef.current() as unknown;
        if (result instanceof Promise) {
          result.then(
            () => finish(false),
            () => finish(true),
          );
        } else {
          finish(false);
        }
      } catch {
        finish(true);
      }
    };

    const onVisibilityChange = () => {
      if (disposed || pollWhenHidden) return;
      if (document.visibilityState !== 'visible') return;
      // Restart the cadence instead of waiting out a timer that was
      // scheduled for a moment the tab was still hidden.
      if (timer !== undefined) {
        clearTimeout(timer);
        timer = undefined;
      }
      tick();
    };

    if (immediate) tick();
    else schedule();
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      disposed = true;
      if (timer !== undefined) clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [intervalMs, enabled, immediate, maxBackoffMs, pollWhenHidden]);
}

export default usePolling;
