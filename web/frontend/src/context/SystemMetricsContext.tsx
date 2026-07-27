import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { fetchSystemMetrics, type SystemMetrics } from '../api/system';
import usePolling from '../hooks/usePolling';

const POLL_INTERVAL_MS = 5000;

interface SystemMetricsContextValue {
  metrics: SystemMetrics | undefined;
  error: string | null;
  refresh: () => Promise<void>;
}

const SystemMetricsContext = createContext<SystemMetricsContextValue | null>(null);

/**
 * Single shared subscription to /api/system/metrics. SystemPanel (the
 * always-visible header popover) and SystemPage used to each poll this
 * endpoint independently, on different schedules -- which meant the two
 * views could show different numbers for the same instant, and the
 * metrics endpoint got hit twice as often as it needed to be. Both now
 * read from this one poller instead.
 */
export function SystemMetricsProvider({ children }: { children: ReactNode }) {
  const [metrics, setMetrics] = useState<SystemMetrics>();
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await fetchSystemMetrics();
      setMetrics(next);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load metrics');
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
  }, [refresh]);

  usePolling(refresh, POLL_INTERVAL_MS, true, { immediate: false });

  return (
    <SystemMetricsContext.Provider value={{ metrics, error, refresh }}>
      {children}
    </SystemMetricsContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useSystemMetrics(): SystemMetricsContextValue {
  const ctx = useContext(SystemMetricsContext);
  if (!ctx) {
    throw new Error('useSystemMetrics must be used within a SystemMetricsProvider');
  }
  return ctx;
}
