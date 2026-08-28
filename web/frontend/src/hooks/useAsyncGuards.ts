import { useCallback, useEffect, useRef } from 'react';

/**
 * Guards for state written by a promise that outlives the render that started
 * it. Both were hand-rolled in six components before this, which is how the
 * `mountedRef` bug below reached five of them at once.
 */

/**
 * Returns a predicate for "this component is still mounted".
 *
 * The ref must be set back to `true` on mount, not just initialised to it:
 * React re-runs effects on the same instance -- StrictMode does it on every
 * mount in development, and a remount does it in production -- and the first
 * cleanup has already set it to `false`. Skipping that line leaves every
 * later response discarded and the page stuck on its skeleton forever.
 */
export function useIsMounted(): () => boolean {
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  return useCallback(() => mounted.current, []);
}

/**
 * Returns a "claim the latest request" function for a stream of overlapping
 * fetches, e.g. one per keystroke of a search box.
 *
 * Call it when a request starts; the token it hands back reports whether that
 * request is still the newest one. Being mounted is not enough here: a slow
 * request for a wide query resolving after a narrow one lands its results on
 * top of what the user is actually looking at.
 *
 *     const claim = useLatestRequest();
 *     const isCurrent = claim();
 *     fetchPage(query).then(page => { if (isCurrent()) setPage(page); });
 */
export function useLatestRequest(): () => () => boolean {
  const latest = useRef(0);
  return useCallback(() => {
    const request = ++latest.current;
    return () => latest.current === request;
  }, []);
}
