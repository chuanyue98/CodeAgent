import { useCallback, useState, useEffect } from 'react';
import { AlertCircle, CheckCircle, AlertTriangle, XCircle, RefreshCw } from 'lucide-react';
import { fetchSystemHealth, type SystemHealth } from '../api/system';
import { useSystemMetrics } from '../context/SystemMetricsContext';
import { useT } from '../i18n/context';

function StatusIcon({ status }: { status: string }) {
  if (status === '[OK]') return <CheckCircle className="w-4 h-4 text-green-600" />;
  if (status === '[!] ') return <AlertTriangle className="w-4 h-4 text-yellow-600" />;
  if (status === '[X] ') return <XCircle className="w-4 h-4 text-red-600" />;
  return <AlertCircle className="w-4 h-4 text-blue-600" />;
}

function MetricBar({ label, value, max, unit, color }: { label: string; value: number; max: number; unit: string; color: string }) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-slate-500">{label}</span>
        <span className="text-slate-700 font-medium">{value}{unit}</span>
      </div>
      <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

export default function SystemPage() {
  const t = useT();
  // Metrics come from the same shared poller SystemPanel (the header
  // popover) reads from, so the two views never show different numbers for
  // the same instant. Health checks are this page's own concern -- they're
  // heavier and only meaningful on-demand, not worth polling continuously.
  const { metrics, error: metricsError, refresh: refreshMetrics } = useSystemMetrics();
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // useCallback because it now closes over `t`: without a stable identity the
  // mount effect below would re-run on every render.
  const load = useCallback(async () => {
    try {
      const h = await fetchSystemHealth();
      setHealth(h);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : t('systemPage.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void load(); }, [load]);

  const handleRefresh = () => {
    void load();
    void refreshMetrics();
  };

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-sm text-slate-400">{t('systemPage.loading')}</div>;
  }
  if (error) {
    return <div className="p-8 text-red-600 text-sm">{error}</div>;
  }

  const uptimeHours = metrics ? Math.floor(metrics.uptimeSeconds / 3600) : 0;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-slate-800">{t('systemPage.health')}</h2>
        <button onClick={handleRefresh} className="flex items-center gap-2 px-3 py-1.5 text-sm border border-slate-200 rounded-xl hover:border-primary/30">
          <RefreshCw className="w-3.5 h-3.5" /> {t('common.refresh')}
        </button>
      </div>

      {/* Metrics */}
      {metricsError && !metrics && (
        <div className="flex items-center gap-2 px-3 py-2 bg-red-50/60 border border-red-100 rounded-lg text-xs text-red-600">
          <AlertCircle className="w-3.5 h-3.5 shrink-0" /> {metricsError}
        </div>
      )}
      {metrics && (
        <div className="glass-card p-5 space-y-4">
          <p className="text-xs text-slate-400 font-medium uppercase tracking-widest">{t('systemPage.metrics')}</p>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricBar label="CPU" value={metrics.cpuPercent} max={100} unit="%" color={metrics.cpuPercent > 80 ? '#ef4444' : '#3b82f6'} />
            <MetricBar label={t('system.memory')} value={metrics.memoryPercent} max={100} unit="%" color={metrics.memoryPercent > 80 ? '#ef4444' : '#10b981'} />
            <MetricBar label={t('system.disk')} value={metrics.diskPercent} max={100} unit="%" color={metrics.diskPercent > 90 ? '#ef4444' : '#f59e0b'} />
            <div className="space-y-1">
              <div className="flex justify-between text-xs">
                <span className="text-slate-500">{t('system.uptime')}</span>
                <span className="text-slate-700 font-medium">{uptimeHours}h</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-slate-500">{t('systemPage.historyFile')}</span>
                <span className="text-slate-700">{metrics.historyFileSizeMb} MB</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-slate-500">{t('systemPage.logFiles')}</span>
                <span className="text-slate-700">{metrics.logFileCount}</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Health checks */}
      {health && health.sections.map((section, i) => (
        <div key={i} className="glass-card p-5">
          <p className="text-xs text-slate-400 font-medium uppercase tracking-widest mb-3">{section.title}</p>
          <div className="space-y-2">
            {section.checks.map((check, j) => (
              <div key={j} className="flex items-start gap-2 text-xs">
                <StatusIcon status={check.status} />
                <div className="flex-1 min-w-0">
                  <span className="text-slate-700">{check.label}</span>
                  {check.detail && <span className="text-slate-400 ml-1">— {check.detail}</span>}
                  {check.fixHint && check.status !== '[OK]' && (
                    <p className="text-slate-400 mt-0.5 ml-6">↳ {check.fixHint}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
      {/* Task run logs live in Automations > Logs, next to the tasks that
          write them -- embedding a second viewer here duplicated that page
          with no system-health purpose of its own. */}
    </div>
  );
}
