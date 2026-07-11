import { useState, useEffect } from 'react';
import { AlertCircle, CheckCircle, AlertTriangle, XCircle, RefreshCw } from 'lucide-react';
import { fetchSystemHealth, fetchSystemMetrics, type SystemHealth, type SystemMetrics } from '../api/system';
import LogViewer from '../components/LogViewer';

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
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      const [h, m] = await Promise.all([fetchSystemHealth(), fetchSystemMetrics()]);
      setHealth(h);
      setMetrics(m);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  };

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void load(); }, []);

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-sm text-slate-400">Loading system info...</div>;
  }
  if (error) {
    return <div className="p-8 text-red-600 text-sm">{error}</div>;
  }

  const uptimeHours = metrics ? Math.floor(metrics.uptime_seconds / 3600) : 0;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-slate-800">System Health</h2>
        <button onClick={load} className="flex items-center gap-2 px-3 py-1.5 text-sm border border-slate-200 rounded-xl hover:border-primary/30">
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </div>

      {/* Metrics */}
      {metrics && (
        <div className="glass-card p-5 space-y-4">
          <p className="text-xs text-slate-400 font-medium uppercase tracking-widest">Metrics</p>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricBar label="CPU" value={metrics.cpu_percent} max={100} unit="%" color={metrics.cpu_percent > 80 ? '#ef4444' : '#3b82f6'} />
            <MetricBar label="Memory" value={metrics.memory_percent} max={100} unit="%" color={metrics.memory_percent > 80 ? '#ef4444' : '#10b981'} />
            <MetricBar label="Disk" value={metrics.disk_percent} max={100} unit="%" color={metrics.disk_percent > 90 ? '#ef4444' : '#f59e0b'} />
            <div className="space-y-1">
              <div className="flex justify-between text-xs">
                <span className="text-slate-500">Uptime</span>
                <span className="text-slate-700 font-medium">{uptimeHours}h</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-slate-500">History file</span>
                <span className="text-slate-700">{metrics.history_file_size_mb} MB</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-slate-500">Log files</span>
                <span className="text-slate-700">{metrics.log_file_count}</span>
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
                  {check.fix_hint && check.status !== '[OK]' && (
                    <p className="text-slate-400 mt-0.5 ml-6">↳ {check.fix_hint}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}

      {/* Log viewer */}
      <LogViewer />
    </div>
  );
}
