import { useEffect, useRef, useState } from 'react';
import { Activity, Cpu, HardDrive, Clock, FileText } from 'lucide-react';
import type { SystemMetrics } from '../api/system';
import { useSystemMetrics } from '../context/SystemMetricsContext';
import { useT } from '../i18n/context';
import ErrorBar from './shared/ErrorBar';

function colorFor(value: number, thresholds: [number, number]): string {
  if (value > thresholds[1]) return 'text-red-600 bg-red-50';
  if (value > thresholds[0]) return 'text-yellow-600 bg-yellow-50';
  return 'text-green-600 bg-green-50';
}

function statusDotFor(metrics: SystemMetrics | undefined, error: string | null): string {
  if (error) return 'bg-red-500';
  if (!metrics) return 'bg-slate-300';
  const worst = Math.max(metrics.cpuPercent, metrics.memoryPercent, metrics.diskPercent);
  if (worst > 90) return 'bg-red-500';
  if (worst > 70) return 'bg-yellow-500';
  return 'bg-emerald-500';
}

export default function SystemPanel() {
  const { metrics, error, refresh } = useSystemMetrics();
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const t = useT();
  const ref = useRef<HTMLDivElement>(null);

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
    void refresh();
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        data-testid="system-status-button"
        onClick={() => setOpen(!open)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={t('system.status')}
        title={t('system.status')}
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
          aria-label={t('system.metrics')}
          className="glass-card absolute right-0 z-50 mt-2 w-72 max-w-[calc(100vw-1rem)] overflow-hidden p-3"
        >
          {error ? (
            <ErrorBar message={error} onRetry={handleRetry} />
          ) : !metrics ? (
            <p className="text-xs text-slate-400">{t('system.loadingMetrics')}</p>
          ) : (
            <>
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 flex-wrap items-center gap-1.5 text-xs">
                  <span className={`flex items-center gap-1 rounded px-1.5 py-0.5 ${colorFor(metrics.cpuPercent, [70, 90])}`}>
                    <Cpu className="h-3 w-3" />{metrics.cpuPercent.toFixed(0)}%
                  </span>
                  <span className={`flex items-center gap-1 rounded px-1.5 py-0.5 ${colorFor(metrics.memoryPercent, [70, 90])}`}>
                    <Clock className="h-3 w-3" />{metrics.memoryPercent.toFixed(0)}%
                  </span>
                  <span className={`flex items-center gap-1 rounded px-1.5 py-0.5 ${colorFor(metrics.diskPercent, [70, 90])}`}>
                    <HardDrive className="h-3 w-3" />{metrics.diskPercent.toFixed(0)}%
                  </span>
                  <span className="flex items-center gap-1 text-slate-400">
                    <FileText className="h-3 w-3" />{t('system.logCount', { count: metrics.logFileCount })}
                  </span>
                </div>
                <button
                  onClick={() => setExpanded(!expanded)}
                  aria-expanded={expanded}
                  className="shrink-0 text-xs text-slate-500 hover:text-slate-800"
                >
                  {expanded ? t('system.hide') : t('system.details')}
                </button>
              </div>

              {expanded && (
                <div className="mt-2 grid grid-cols-2 gap-3 border-t border-slate-100 pt-2 text-xs">
                  <div>
                    <span className="text-slate-400">{t('system.memory')}</span>
                    <p className="font-medium text-slate-700">{metrics.memoryUsedGb} / {metrics.memoryTotalGb} GB</p>
                  </div>
                  <div>
                    <span className="text-slate-400">{t('system.disk')}</span>
                    <p className="font-medium text-slate-700">{metrics.diskUsedGb} / {metrics.diskTotalGb} GB</p>
                  </div>
                  <div>
                    <span className="text-slate-400">{t('system.uptime')}</span>
                    <p className="font-medium text-slate-700">{t('system.uptimeHours', { hours: Math.floor(metrics.uptimeSeconds / 3600) })}</p>
                  </div>
                  <div>
                    <span className="text-slate-400">{t('system.historyDb')}</span>
                    <p className="font-medium text-slate-700">{metrics.historyFileSizeMb} MB</p>
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
