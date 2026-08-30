import { createContext, useCallback, useContext, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchSystemMetrics, type SystemMetrics } from '../api/system';

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
  const queryClient = useQueryClient();
  const { data, error } = useQuery({
    queryKey: ['system', 'metrics'],
    queryFn: fetchSystemMetrics,
    refetchInterval: POLL_INTERVAL_MS,
  });

  const refresh = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ['system', 'metrics'] });
  }, [queryClient]);

  return (
    <SystemMetricsContext.Provider
      value={{
        metrics: data,
        error: error ? (error instanceof Error ? error.message : 'Failed to load metrics') : null,
        refresh,
      }}
    >
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
