import { useCallback, useEffect, useRef, useState } from 'react';
import { Activity, Cpu, HardDrive, Clock, FileText } from 'lucide-react';
import { fetchSystemMetrics, type SystemMetrics } from '../api/system';

function colorFor(value: number, thresholds: [number, number]): string {
  if (value > thresholds[1]) return 'text-red-600 bg-red-50';
  if (value > thresholds[0]) return 'text-yellow-600 bg-yellow-50';
  return 'text-green-600 bg-green-50';
}

function statusDotFor(metrics: SystemMetrics | undefined, error: string | null): string {
  if (error) return 'bg-red-500';
  if (!metrics) return 'bg-slate-300';
  const worst = Math.max(metrics.cpu_percent, metrics.memory_percent, metrics.disk_percent);
  if (worst > 90) return 'bg-red-500';
  if (worst > 70) return 'bg-yellow-500';
  return 'bg-emerald-500';
}

export default function SystemPanel() {
  const [metrics, setMetrics] = useState<SystemMetrics>();
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

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

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleRetry = () => {
    void loadMetrics();
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        data-testid="system-status-button"
        onClick={() => setOpen(!open)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label="System status"
        title="System status"
        className="relative flex items-center gap-1.5 rounded-xl border border-slate-100 bg-white/50 px-3 py-2 text-slate-500 shadow-sm backdrop-blur-md transition-colors hover:bg-white hover:text-slate-800"
      >
        <Activity size={16} />
        <span
          data-testid="system-status-dot"
          className={`absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full ring-2 ring-white ${statusDotFor(metrics, error)}`}
        />
      </button>

      {open && (
        <div
          data-testid="system-metrics"
          role="dialog"
          aria-label="System metrics"
          className="glass-card absolute right-0 z-50 mt-2 w-72 max-w-[calc(100vw-1rem)] overflow-hidden p-3"
        >
          {error ? (
            <div role="alert" className="flex items-center justify-between gap-2 text-xs text-red-600">
              <span>{error}</span>
              <button onClick={handleRetry} className="shrink-0 hover:underline">Retry</button>
            </div>
          ) : !metrics ? (
            <p className="text-xs text-slate-400">Loading metrics…</p>
          ) : (
            <>
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 flex-wrap items-center gap-1.5 text-xs">
                  <span className={`flex items-center gap-1 rounded px-1.5 py-0.5 ${colorFor(metrics.cpu_percent, [70, 90])}`}>
                    <Cpu className="h-3 w-3" />{metrics.cpu_percent.toFixed(0)}%
                  </span>
                  <span className={`flex items-center gap-1 rounded px-1.5 py-0.5 ${colorFor(metrics.memory_percent, [70, 90])}`}>
                    <Clock className="h-3 w-3" />{metrics.memory_percent.toFixed(0)}%
                  </span>
                  <span className={`flex items-center gap-1 rounded px-1.5 py-0.5 ${colorFor(metrics.disk_percent, [70, 90])}`}>
                    <HardDrive className="h-3 w-3" />{metrics.disk_percent.toFixed(0)}%
                  </span>
                  <span className="flex items-center gap-1 text-slate-400">
                    <FileText className="h-3 w-3" />{metrics.log_file_count} logs
                  </span>
                </div>
                <button
                  onClick={() => setExpanded(!expanded)}
                  aria-expanded={expanded}
                  className="shrink-0 text-xs text-slate-500 hover:text-slate-800"
                >
                  {expanded ? 'Hide' : 'Details'}
                </button>
              </div>

              {expanded && (
                <div className="mt-2 grid grid-cols-2 gap-3 border-t border-slate-100 pt-2 text-xs">
                  <div>
                    <span className="text-slate-400">Memory</span>
                    <p className="font-medium text-slate-700">{metrics.memory_used_gb} / {metrics.memory_total_gb} GB</p>
                  </div>
                  <div>
                    <span className="text-slate-400">Disk</span>
                    <p className="font-medium text-slate-700">{metrics.disk_used_gb} / {metrics.disk_total_gb} GB</p>
                  </div>
                  <div>
                    <span className="text-slate-400">Uptime</span>
                    <p className="font-medium text-slate-700">{Math.floor(metrics.uptime_seconds / 3600)}h</p>
                  </div>
                  <div>
                    <span className="text-slate-400">History DB</span>
                    <p className="font-medium text-slate-700">{metrics.history_file_size_mb} MB</p>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
