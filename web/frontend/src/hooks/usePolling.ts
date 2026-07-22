import { useEffect, useRef } from 'react';

interface UsePollingOptions {
  /**
   * Call `fn` once immediately whenever polling (re)starts (i.e. on mount,
   * or when `enabled` flips from false to true), in addition to on the
   * recurring interval. Defaults to true, matching the "fetch on mount,
   * then refresh on a timer" pattern used across the app.
   */
  immediate?: boolean;
}

/**
 * Shared polling hook: calls `fn` on a recurring `intervalMs` timer while
 * `enabled` is true, and cleans up the interval automatically on unmount,
 * when `enabled` flips to false, or when `intervalMs` changes.
 *
 * `fn` is read through a ref, so callers don't need to memoize it (or
 * list unrelated state in its dependency array) just to avoid the
 * interval being torn down and recreated on every unrelated render.
 */
function usePolling(fn: () => void, intervalMs: number, enabled = true, options: UsePollingOptions = {}): void {
  const { immediate = true } = options;
  const fnRef = useRef(fn);
  useEffect(() => {
    fnRef.current = fn;
  }, [fn]);

  useEffect(() => {
    if (!enabled) return;
    if (immediate) fnRef.current();
    const id = setInterval(() => fnRef.current(), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs, enabled, immediate]);
}

export default usePolling;
