import { useSyncExternalStore } from 'react';

/**
 * Whether a media query currently matches. `fallback` is what a browser
 * without matchMedia (and the first server-less render) reports.
 */
export function useMediaQuery(query: string, fallback = true): boolean {
  return useSyncExternalStore(
    notify => {
      const list = window.matchMedia?.(query);
      list?.addEventListener('change', notify);
      return () => list?.removeEventListener('change', notify);
    },
    () => window.matchMedia?.(query).matches ?? fallback,
    () => fallback,
  );
}
