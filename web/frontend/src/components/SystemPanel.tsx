import { useCallback, useState, useEffect } from 'react';
import { Cpu, HardDrive, Clock, FileText } from 'lucide-react';
import { fetchSystemMetrics, type SystemMetrics } from '../api/system';

function colorFor(value: number, thresholds: [number, number]): string {
  if (value > thresholds[1]) return 'text-red-600 bg-red-50';
  if (value > thresholds[0]) return 'text-yellow-600 bg-yellow-50';
  return 'text-green-600 bg-green-50';
}

export default function SystemPanel() {
  const [metrics, setMetrics] = useState<SystemMetrics>();
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  const loadMetrics = useCallback(async () => {
    try {
      const nextMetrics = await fetchSystemMetrics();
      setMetrics(nextMetrics);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load metrics');
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadMetrics();
    const interval = setInterval(() => { void loadMetrics(); }, 5000);
    return () => clearInterval(interval);
  }, [loadMetrics]);

  const handleRetry = () => {
    void loadMetrics();
  };

  if (error) return (
    <div role="alert" className="shrink-0 border-t border-red-100 bg-red-50/90 px-4 py-2 flex items-center justify-between">
        <span className="text-xs text-red-600">{error}</span>
        <button onClick={handleRetry} className="text-xs text-red-600 hover:underline">Retry</button>
    </div>
  );

  if (!metrics) return null;

  return (
    <footer data-testid="system-metrics" aria-label="System metrics" className="shrink-0 border-t border-slate-200 bg-white/95 px-3 md:px-4 py-1.5 shadow-[0_-4px_12px_rgba(15,23,42,0.04)]">
        <div className="flex items-center justify-between">
          <div className="flex min-w-0 items-center gap-1.5 sm:gap-4 text-xs">
            <span className={`flex items-center gap-1 px-1.5 py-0.5 rounded ${colorFor(metrics.cpu_percent, [70, 90])}`}>
              <Cpu className="w-3 h-3" />{metrics.cpu_percent.toFixed(0)}%
            </span>
            <span className={`flex items-center gap-1 px-1.5 py-0.5 rounded ${colorFor(metrics.memory_percent, [70, 90])}`}>
              <Clock className="w-3 h-3" />{metrics.memory_percent.toFixed(0)}%
            </span>
            <span className={`flex items-center gap-1 px-1.5 py-0.5 rounded ${colorFor(metrics.disk_percent, [70, 90])}`}>
              <HardDrive className="w-3 h-3" />{metrics.disk_percent.toFixed(0)}%
            </span>
            <span className="text-slate-400 flex items-center gap-1">
              <FileText className="w-3 h-3" />{metrics.log_file_count} logs
            </span>
          </div>
          <button
            onClick={() => setExpanded(!expanded)}
            aria-expanded={expanded}
            className="shrink-0 text-xs text-slate-500 hover:text-slate-800 flex items-center gap-1"
          >
            {expanded ? 'Hide' : 'Details'}
          </button>
        </div>

        {expanded && (
          <div className="mt-2 pt-2 border-t border-slate-100 grid grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
            <div>
              <span className="text-slate-400">Memory</span>
              <p className="text-slate-700 font-medium">{metrics.memory_used_gb} / {metrics.memory_total_gb} GB</p>
            </div>
            <div>
              <span className="text-slate-400">Disk</span>
              <p className="text-slate-700 font-medium">{metrics.disk_used_gb} / {metrics.disk_total_gb} GB</p>
            </div>
            <div>
              <span className="text-slate-400">Uptime</span>
              <p className="text-slate-700 font-medium">{Math.floor(metrics.uptime_seconds / 3600)}h</p>
            </div>
            <div>
              <span className="text-slate-400">History DB</span>
              <p className="text-slate-700 font-medium">{metrics.history_file_size_mb} MB</p>
            </div>
          </div>
        )}
    </footer>
  );
}
