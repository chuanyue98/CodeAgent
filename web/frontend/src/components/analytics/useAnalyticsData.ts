import { useCallback, useEffect, useState } from 'react';
import { useIsMounted } from '../../hooks/useAsyncGuards';
import { useT } from '../../i18n/context';
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
  const t = useT();
  const [engines, setEngines] = useState<EngineSummary[]>([]);
  const [daily, setDaily] = useState<DailyUsage[]>([]);
  const [monthly, setMonthly] = useState<MonthlyUsage[]>([]);
  const [sessions, setSessions] = useState<SessionUsage[]>([]);
  const [modelStats, setModelStats] = useState<ModelStat[]>([]);
  const [totalSessions, setTotalSessions] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isMounted = useIsMounted();

  const loadAll = useCallback(async () => {
    try {
      const [summary, eng, day, mon, sess, mods] = await Promise.all([
        fetchSummary(), fetchEngines(), fetchDaily(), fetchMonthly(), fetchSessions(500), fetchModels(),
      ]);
      if (!isMounted()) return;
      setEngines(eng); setDaily(day); setMonthly(mon); setSessions(sess); setModelStats(mods);
      setTotalSessions(summary.session_count);
      setError(null);
    } catch (e) {
      if (!isMounted()) return;
      setError(e instanceof Error ? e.message : t('analytics.loadFailed'));
    } finally {
      if (isMounted()) setLoading(false);
    }
  }, [isMounted, t]);

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
