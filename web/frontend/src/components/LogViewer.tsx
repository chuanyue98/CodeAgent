import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { Terminal, AlertCircle, CheckCircle2, Wifi, WifiOff } from 'lucide-react';
import { fetchLogFiles, fetchLogFile, useLogStream, type LogFile } from '../api/logs';
import usePolling from '../hooks/usePolling';
import { useT } from '../i18n/context';

// Rendering every line of a long-running task's log as its own DOM node gets
// sluggish well before the 10,000-line cap in api/logs.ts is reached. Only
// the most recent lines are rendered by default; the rest are one click away
// via the banner below, rather than reaching for a virtualization library.
const DEFAULT_VISIBLE_LINES = 1500;

export default function LogViewer({ taskId: initialTaskId }: { taskId?: string }) {
  const t = useT();
  const [files, setFiles] = useState<LogFile[] | undefined>(undefined);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(initialTaskId ?? null);
  const [initialContent, setInitialContent] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [filesError, setFilesError] = useState<string | null>(null);
  const [showAllLines, setShowAllLines] = useState(false);

  const { lines: streamLines, error, connected, finished } = useLogStream(selectedTaskId);

  const loadFiles = useCallback(async () => {
    try {
      await fetchLogFiles().then(setFiles);
      setFilesError(null);
    } catch (e) {
      setFilesError(e instanceof Error ? e.message : t('logs.loadFailed'));
    }
  }, [t]);

  usePolling(loadFiles, 10000);

  useEffect(() => {
    if (!selectedTaskId) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    setShowAllLines(false);
    fetchLogFile(selectedTaskId).then(res => {
      setInitialContent(res.content);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [selectedTaskId]);

  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const threshold = 80;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
    setAutoScroll(atBottom);
  }, []);

  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [streamLines, autoScroll, initialContent]);

  const allLines = useMemo(
    () => [
      ...(initialContent ?? '').split('\n'),
      ...(selectedTaskId ? streamLines : []),
    ].filter((l: string) => l.trim()),
    [initialContent, selectedTaskId, streamLines],
  );

  const truncated = !showAllLines && allLines.length > DEFAULT_VISIBLE_LINES;
  const visibleLines = truncated ? allLines.slice(-DEFAULT_VISIBLE_LINES) : allLines;

  return (
    <div className="glass-card flex flex-col h-full">
      <div className="flex flex-wrap items-center justify-between gap-2 p-3 border-b border-slate-100">
        <div className="flex flex-wrap items-center gap-2">
          <Terminal className="w-4 h-4 text-slate-500" />
          <span className="text-sm font-semibold text-slate-700">{t('logs.title')}</span>
          {selectedTaskId && (
            /* A run that ended closed the stream on purpose. Reporting that
               as "disconnected" reads as a fault the viewer should retry. */
            <span
              className={`flex items-center gap-1 text-xs ${
                finished ? 'text-slate-500' : connected ? 'text-green-600' : 'text-red-500'
              }`}
            >
              {finished ? (
                <CheckCircle2 className="w-3 h-3" />
              ) : connected ? (
                <Wifi className="w-3 h-3" />
              ) : (
                <WifiOff className="w-3 h-3" />
              )}
              {finished
                ? t('logs.finished', { status: finished })
                : connected
                  ? t('logs.live')
                  : t('logs.disconnected')}
            </span>
          )}
        </div>
        <button
          onClick={() => setAutoScroll(!autoScroll)}
          className="text-xs text-slate-500 hover:text-slate-800"
        >
          {autoScroll ? t('logs.autoScrollOn') : t('logs.autoScrollOff')}
        </button>
      </div>

      <div className="flex flex-col sm:flex-row flex-1 min-h-0">
        <div className="w-full sm:w-48 shrink-0 max-h-40 sm:max-h-none border-b sm:border-b-0 sm:border-r border-slate-100 overflow-y-auto p-2 space-y-1">
          {filesError && (
            <p className="text-xs text-red-600 px-2">{filesError}</p>
          )}
          {files?.map(f => (
            <button
              key={f.task_id}
              onClick={() => setSelectedTaskId(f.task_id)}
              className={`w-full text-left px-2 py-1.5 rounded-md text-xs truncate transition-colors ${
                selectedTaskId === f.task_id
                  ? 'bg-slate-100 text-slate-800 font-medium'
                  : 'text-slate-500 hover:bg-slate-50'
              }`}
            >
              {f.name}
            </button>
          ))}
          {files?.length === 0 && (
            <p className="text-xs text-slate-400 px-2">{t('logs.noFiles')}</p>
          )}
        </div>

        <div
          ref={containerRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto p-3 font-mono text-xs leading-relaxed bg-slate-50/50"
        >
          {loading && <p className="text-slate-400">{t('common.loading')}</p>}
          {error && (
            <div className="flex items-center gap-2 text-red-600 mb-2">
              <AlertCircle className="w-3 h-3" />
              <span className="text-xs">{error}</span>
            </div>
          )}
          {truncated && (
            <div className="sticky top-0 z-10 mb-2 flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-200 bg-amber-50 px-2 py-1.5 text-[11px] text-amber-800">
              <span>
                {t('logs.truncated', {
            visible: DEFAULT_VISIBLE_LINES.toLocaleString(),
            total: allLines.length.toLocaleString(),
          })}
              </span>
              <button
                onClick={() => setShowAllLines(true)}
                className="font-semibold text-amber-900 underline hover:no-underline"
              >
                {t('logs.showAll')}
              </button>
            </div>
          )}
          {visibleLines.map((line, i) => (
            <div key={i} className="text-slate-600 whitespace-pre-wrap break-all">{line}</div>
          ))}
        </div>
      </div>
    </div>
  );
}
