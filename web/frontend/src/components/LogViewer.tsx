import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  Terminal,
  AlertCircle,
  CheckCircle2,
  Wifi,
  WifiOff,
  Search,
  Copy,
  Check,
  Maximize2,
  Minimize2,
} from 'lucide-react';
import { fetchLogFiles, fetchLogFile, useLogStream, type LogFile } from '../api/logs';
import usePolling from '../hooks/usePolling';
import { useT } from '../i18n/context';
import EmptyState from './shared/EmptyState';

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
  const [searchQuery, setSearchQuery] = useState('');
  const [copied, setCopied] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const copyTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  useEffect(() => {
    if (!fullscreen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setFullscreen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [fullscreen]);

  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) {
        clearTimeout(copyTimeoutRef.current);
      }
    };
  }, []);

  const allLines = useMemo(
    () => [
      ...(initialContent ?? '').split('\n'),
      ...(selectedTaskId ? streamLines : []),
    ].filter((l: string) => l.trim()),
    [initialContent, selectedTaskId, streamLines],
  );

  const filteredLines = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return allLines;
    return allLines.filter((l: string) => l.toLowerCase().includes(q));
  }, [allLines, searchQuery]);

  const truncated = !showAllLines && filteredLines.length > DEFAULT_VISIBLE_LINES;
  const visibleLines = truncated ? filteredLines.slice(-DEFAULT_VISIBLE_LINES) : filteredLines;

  const handleCopy = useCallback(async () => {
    try {
      const textToCopy = filteredLines.join('\n');
      await navigator.clipboard.writeText(textToCopy);
      setCopied(true);
      if (copyTimeoutRef.current) {
        clearTimeout(copyTimeoutRef.current);
      }
      copyTimeoutRef.current = setTimeout(() => {
        setCopied(false);
      }, 2000);
    } catch {
      // ignore clipboard errors
    }
  }, [filteredLines]);

  return (
    <div
      className={`glass-card flex flex-col h-full ${
        fullscreen ? 'fixed inset-0 z-50 p-4 bg-white/95 backdrop-blur-md' : ''
      }`}
    >
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

        <div className="flex flex-wrap items-center gap-2">
          {/* Keyword Search Filter */}
          <div className="relative flex items-center">
            <Search className="w-3.5 h-3.5 absolute left-2.5 text-slate-400 pointer-events-none" />
            <input
              type="text"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder={t('logs.searchPlaceholder')}
              className="pl-8 pr-2 py-1 text-xs border border-slate-200 rounded-md focus:outline-none focus:ring-1 focus:ring-primary-500 bg-white w-32 sm:w-44 transition-all"
            />
          </div>

          {/* Copy All */}
          <button
            type="button"
            onClick={handleCopy}
            className="flex items-center gap-1 px-2.5 py-1 rounded text-xs text-slate-600 hover:bg-slate-100 border border-slate-200 transition-colors"
            title={copied ? t('logs.copied') : t('logs.copyAll')}
          >
            {copied ? (
              <>
                <Check className="w-3.5 h-3.5 text-emerald-600" />
                <span className="text-emerald-600 font-medium">{t('logs.copied')}</span>
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                <span>{t('logs.copyAll')}</span>
              </>
            )}
          </button>

          {/* Auto-scroll toggle */}
          <button
            type="button"
            onClick={() => setAutoScroll(!autoScroll)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded border text-xs transition-colors ${
              autoScroll
                ? 'border-emerald-200 bg-emerald-50/50 text-emerald-700 font-medium'
                : 'border-slate-200 text-slate-500 hover:bg-slate-50'
            }`}
            title={autoScroll ? t('logs.autoScrollOn') : t('logs.autoScrollOff')}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${autoScroll ? 'bg-emerald-500' : 'bg-slate-300'}`}
            />
            <span>{autoScroll ? t('logs.autoScrollOn') : t('logs.autoScrollOff')}</span>
          </button>

          {/* Fullscreen toggle */}
          <button
            type="button"
            onClick={() => setFullscreen(!fullscreen)}
            className="p-1 rounded text-slate-500 hover:text-slate-800 hover:bg-slate-100 border border-slate-200 transition-colors"
            title={fullscreen ? t('logs.exitFullscreen') : t('logs.fullscreen')}
            aria-label={fullscreen ? t('logs.exitFullscreen') : t('logs.fullscreen')}
          >
            {fullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row flex-1 min-h-0">
        <div className="w-full sm:w-48 shrink-0 max-h-40 sm:max-h-none border-b sm:border-b-0 sm:border-r border-slate-100 overflow-y-auto p-2 space-y-1">
          {filesError && (
            <p className="text-xs text-red-600 px-2">{filesError}</p>
          )}
          {files?.map(f => (
            <button
              key={f.taskId}
              onClick={() => setSelectedTaskId(f.taskId)}
              className={`w-full text-left px-2 py-1.5 rounded-md text-xs truncate transition-colors ${
                selectedTaskId === f.taskId
                  ? 'bg-slate-100 text-slate-800 font-medium'
                  : 'text-slate-500 hover:bg-slate-50'
              }`}
            >
              {f.name}
            </button>
          ))}
          {files?.length === 0 && (
            <EmptyState compact title={t('logs.noFiles')} />
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
                  total: filteredLines.length.toLocaleString(),
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
          {searchQuery.trim() && filteredLines.length === 0 && !loading && (
            <div className="py-8 text-center text-xs text-slate-400">
              匹配 0 行
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
