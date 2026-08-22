import { useCallback, useEffect, useRef, useState } from 'react';
import {
  type DailyUsage,
  type EngineSummary,
  type ModelStat,
  type MonthlyUsage,
  type SessionUsage,
  fetchDaily,
  fetchEngines,
  fetchModels,
  fetchMonthly,
  fetchSessions,
  fetchSummary,
  refreshAnalytics,
} from '../../api/analytics';

export interface AnalyticsData {
  engines: EngineSummary[];
  daily: DailyUsage[];
  monthly: MonthlyUsage[];
  sessions: SessionUsage[];
  modelStats: ModelStat[];
  totalSessions: number;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  retry: () => void;
  handleRefresh: () => Promise<void>;
}

/**
 * Loads the six analytics endpoints the dashboard derives everything from.
 * Split out of the page component so the derivations and rendering below
 * read as pure transforms of this data.
 */
export default function useAnalyticsData(): AnalyticsData {
  const [engines, setEngines] = useState<EngineSummary[]>([]);
  const [daily, setDaily] = useState<DailyUsage[]>([]);
  const [monthly, setMonthly] = useState<MonthlyUsage[]>([]);
  const [sessions, setSessions] = useState<SessionUsage[]>([]);
  const [modelStats, setModelStats] = useState<ModelStat[]>([]);
  const [totalSessions, setTotalSessions] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Guards setState calls in the async fetch below from firing after the
  // component has unmounted (e.g. a fast page switch while the request is
  // still in flight).
  const mountedRef = useRef(true);
  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const loadAll = useCallback(async () => {
    try {
      const [summary, eng, day, mon, sess, mods] = await Promise.all([
        fetchSummary(), fetchEngines(), fetchDaily(), fetchMonthly(), fetchSessions(500), fetchModels(),
      ]);
      if (!mountedRef.current) return;
      setEngines(eng); setDaily(day); setMonthly(mon); setSessions(sess); setModelStats(mods);
      setTotalSessions(summary.session_count);
      setError(null);
    } catch (e) {
      if (!mountedRef.current) return;
      setError(e instanceof Error ? e.message : 'Failed to load analytics');
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void loadAll(); }, [loadAll]);

  const retry = useCallback(() => {
    setError(null);
    setLoading(true);
    void loadAll();
  }, [loadAll]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try { await refreshAnalytics(); await loadAll(); } catch { /* ignore */ }
    finally { setRefreshing(false); }
  }, [loadAll]);

  return {
    engines, daily, monthly, sessions, modelStats, totalSessions,
    loading, refreshing, error, retry, handleRefresh,
  };
}
