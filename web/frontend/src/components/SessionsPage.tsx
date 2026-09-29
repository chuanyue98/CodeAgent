import { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import { useIsMounted, useLatestRequest } from '../hooks/useAsyncGuards';
import { useSearchParams } from 'react-router';
import { ChevronDown, ChevronRight, Clock, FileText, AlertCircle, Loader2, Play, RefreshCw, Trash2, Zap } from 'lucide-react';
import { fetchSessionPage, type SessionUsage, fmtTokens } from '../api/analytics';
import { convertAndLaunchSession, deleteHistorySession } from '../api/audit';
import useActivityFilters from '../hooks/useActivityFilters';
import { useTerminal } from '../context/TerminalContext';
import { useT } from '../i18n/context';
import { isWithinLocalDayRange } from '../utils/dateRange';
import ActivityFilterPanel from './ActivityFilterPanel';
import { AGENT_ENGINES, findEngine } from './terminalEngines';
import SessionDetailPanel from './SessionDetailPanel';
import ConfirmDialog from './shared/ConfirmDialog';
import EmptyState from './shared/EmptyState';
import ErrorState from './shared/ErrorState';
import FilterListSkeleton from './shared/FilterListSkeleton';

type SortKey = 'lastActivity' | 'tokens';
type SortDir = 'asc' | 'desc';

/**
 * Sessions fetched per request. The list used to ask for a hard-coded 500 --
 * more than fits on any screen, and still fewer than some machines have, so
 * the remainder was cut off before it reached the browser and every filter
 * below ran against that partial window.
 */
const PAGE_SIZE = 100;

/** Typing a query should not put one request per keystroke on the wire. */
const SEARCH_DEBOUNCE_MS = 250;

/**
 * A session is identified by (engine, id), not by id alone — the backend
 * aggregates on that pair, so the same id can legitimately appear under two
 * engines (cross-engine conversion is one way to get there). Keying rows or
 * expansion state on the bare id collides when it does.
 */
function sessionKey(session: SessionUsage): string {
  return `${session.target}::${session.sessionId}`;
}

export default function SessionsPage() {
  const [sessions, setSessions] = useState<SessionUsage[]>([]);
  const [loading, setLoading] = useState(true);
  const t = useT();
  const filters = useActivityFilters();
  const { search, dateStart, dateEnd, engines: selectedEngines, project, ready } = filters;
  const [sortKey, setSortKey] = useState<SortKey>('lastActivity');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [searchParams] = useSearchParams();
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const { openTab, openDrawer } = useTerminal();
  const [handoffSessionId, setHandoffSessionId] = useState<string | null>(null);
  const [handoffLoading, setHandoffLoading] = useState<string | null>(null);
  const handoffRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (handoffRef.current && !handoffRef.current.contains(event.target as Node)) {
        setHandoffSessionId(null);
      }
    }
    if (handoffSessionId) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [handoffSessionId]);

  const handleResumeSession = (session: SessionUsage) => {
    openTab(session.target, session.projectPath, session.sessionId);
    openDrawer();
  };

  const handleHandoffSession = async (session: SessionUsage, targetEngine: string) => {
    setHandoffLoading(session.sessionId);
    try {
      const result = await convertAndLaunchSession({
        sourceEngine: session.target,
        sessionId: session.sessionId,
        targetEngine,
        projectPath: session.projectPath,
      });
      setHandoffSessionId(null);
      openTab(result.engine, result.project, result.sessionId);
      openDrawer();
    } catch (err) {
      console.error('Failed to handoff session:', err);
    } finally {
      setHandoffLoading(null);
    }
  };

  const [error, setError] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [matchCount, setMatchCount] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  // `search` updates on every keystroke (it lives in the URL); the request
  // follows it only once typing settles.
  const [activeSearch, setActiveSearch] = useState(search);
  useEffect(() => {
    const timer = setTimeout(() => setActiveSearch(search), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [search]);

  const isMounted = useIsMounted();
  // Narrowing the query starts a new request while the old one is still out.
  // Being mounted is not enough to accept a response: the wider result would
  // land on top of the narrower one the user is now looking at.
  const claimPage = useLatestRequest();

  // Project narrowing and text search both happen server-side, and the page
  // is cut after them: filtering a fixed window here instead would let a busy
  // neighbouring project crowd the selected one out of it.
  useEffect(() => {
    if (!ready) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    setError(null);
    const isCurrent = claimPage();
    fetchSessionPage({
      limit: PAGE_SIZE,
      project: project || undefined,
      search: activeSearch || undefined,
    })
      .then(page => {
        if (!isMounted() || !isCurrent()) return;
        setSessions(page.sessions);
        setNextCursor(page.nextCursor);
        setMatchCount(page.total);
        setLoading(false);
      })
      .catch(() => {
        if (!isMounted() || !isCurrent()) return;
        setLoading(false);
        setError(t('sessions.loadFailed'));
      });
  }, [project, activeSearch, ready, reloadNonce, isMounted, claimPage, t]);

  const loadMore = useCallback(() => {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    fetchSessionPage({
      limit: PAGE_SIZE,
      project: project || undefined,
      search: activeSearch || undefined,
      cursor: nextCursor,
    })
      .then(page => {
        if (!isMounted()) return;
        setSessions(previous => [...previous, ...page.sessions]);
        setNextCursor(page.nextCursor);
        setMatchCount(page.total);
        setLoadingMore(false);
      })
      .catch(() => {
        if (!isMounted()) return;
        setLoadingMore(false);
        setError(t('sessions.loadFailed'));
      });
  }, [nextCursor, loadingMore, project, activeSearch, isMounted, t]);

  const reload = useCallback(() => setReloadNonce(n => n + 1), []);

  // Deep link from the command palette, Home, and the Agent sidebar:
  // `?session=<id>` (+ optional sessionEngine/sessionProject hints, the same
  // shape every other session link uses) expands that session in place once
  // the list has loaded. When the link's project is narrowed out by the
  // current project filter, pin the filter to that project once so the
  // fetch actually includes the linked session.
  const deepLinkProjectRef = useRef<string | null>(null);
  useEffect(() => {
    const sessionId = searchParams.get('session');
    if (!sessionId) return;
    const linkProject = searchParams.get('sessionProject');
    const match = sessions.find(s => s.sessionId === sessionId);
    if (match) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelectedKey(sessionKey(match));
      return;
    }
    if (
      linkProject &&
      deepLinkProjectRef.current !== sessionId &&
      filters.project !== linkProject
    ) {
      deepLinkProjectRef.current = sessionId;
      filters.setProject(linkProject);
    }
  }, [sessions, searchParams, filters]);

  const engines = useMemo(() => {
    const set = new Set(sessions.map(s => s.target));
    return Array.from(set).sort();
  }, [sessions]);

  // No text search here: the server matched it against the whole set, not
  // just the pages that happen to be loaded. Engine and date narrowing stay
  // client-side -- they apply to what has been fetched so far.
  const filtered = useMemo(() => {
    let result = sessions;
    if (selectedEngines.length > 0) {
      result = result.filter(s => selectedEngines.includes(s.target));
    }
    if (dateStart || dateEnd) {
      result = result.filter(s => isWithinLocalDayRange(s.lastActivity, dateStart, dateEnd));
    }
    result = [...result].sort((a, b) => {
      let cmp = 0;
      if (sortKey === 'lastActivity') {
        const ta = new Date(a.lastActivity).getTime() || 0;
        const tb = new Date(b.lastActivity).getTime() || 0;
        cmp = ta - tb;
      }
      else if (sortKey === 'tokens') cmp = (a.inputTokens + a.outputTokens) - (b.inputTokens + b.outputTokens);
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return result;
  }, [sessions, selectedEngines, dateStart, dateEnd, sortKey, sortDir]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortKey(key); setSortDir('desc'); }
  };

  const toggleSelected = (key: string) => {
    setSelectedKeys(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const allFilteredSelected = filtered.length > 0 && filtered.every(s => selectedKeys.has(sessionKey(s)));

  const toggleSelectAllFiltered = () => {
    setSelectedKeys(prev => {
      if (allFilteredSelected) {
        const next = new Set(prev);
        filtered.forEach(s => next.delete(sessionKey(s)));
        return next;
      }
      const next = new Set(prev);
      filtered.forEach(s => next.add(sessionKey(s)));
      return next;
    });
  };

  const selectedSessions = useMemo(
    () => sessions.filter(s => selectedKeys.has(sessionKey(s))),
    [sessions, selectedKeys],
  );

  /** The one session the detail panel is showing, if it is still in the list. */
  const openSession = useMemo(
    () => filtered.find(s => sessionKey(s) === selectedKey) ?? null,
    [filtered, selectedKey],
  );

  const dropSession = useCallback((target: SessionUsage) => {
    const key = sessionKey(target);
    setSessions(prev => prev.filter(s => sessionKey(s) !== key));
    setSelectedKeys(prev => {
      const next = new Set(prev);
      next.delete(key);
      return next;
    });
  }, []);

  const handleBulkDelete = async () => {
    setDeleting(true);
    setDeleteError(null);
    const results = await Promise.allSettled(
      selectedSessions.map(s => deleteHistorySession(s.target, s.sessionId, s.projectPath)),
    );
    const failedCount = results.filter(r => r.status === 'rejected').length;
    const deletedKeys = new Set(
      selectedSessions
        .filter((_s, i) => results[i].status === 'fulfilled')
        .map(sessionKey),
    );
    setSessions(prev => prev.filter(s => !deletedKeys.has(sessionKey(s))));
    setSelectedKeys(prev => {
      const next = new Set(prev);
      deletedKeys.forEach(key => next.delete(key));
      return next;
    });
    setDeleting(false);
    setConfirmingDelete(false);
    if (failedCount > 0) {
      setDeleteError(
        selectedSessions.length === 1
          ? t('sessions.deleteFailedOne', { failed: failedCount, total: selectedSessions.length })
          : t('sessions.deleteFailed', { failed: failedCount, total: selectedSessions.length }),
      );
    }
  };

  // Only the first load gets the skeleton. Refreshing used to swap the whole
  // page for it, which unmounted the open session's detail panel -- so the
  // transcript you were part-way through was refetched from scratch and lost
  // its scroll position. With data already on screen, keep showing it and let
  // the new response replace it underneath.
  const firstLoad = sessions.length === 0;

  if (loading && firstLoad) {
    return <FilterListSkeleton label={t('sessions.loading')} />;
  }

  if (error && firstLoad) {
    return <ErrorState message={error} onRetry={reload} />;
  }

  const sortButton = 'rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors';

  return (
    <div className="flex min-h-full flex-col gap-4 xl:h-full">
      <ActivityFilterPanel
        filters={filters}
        engineOptions={engines}
        searchPlaceholder={t('sessions.searchPlaceholder')}
      />

      <div className="flex min-h-0 flex-1 flex-col gap-4 xl:flex-row">
        <div data-testid="session-list" className="flex min-w-0 flex-1 flex-col">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-3">
              <label className="flex cursor-pointer select-none items-center gap-2 text-sm text-muted-foreground">
                <input
                  type="checkbox"
                  aria-label={t('sessions.selectAllFiltered')}
                  checked={allFilteredSelected}
                  onChange={toggleSelectAllFiltered}
                  disabled={filtered.length === 0}
                  className="h-3.5 w-3.5 rounded border-border text-primary focus:ring-primary"
                />
                {filtered.length === 1
                  ? t('sessions.countOne', { count: filtered.length })
                  : t('sessions.count', { count: filtered.length })}
              </label>
              {selectedKeys.size > 0 && (
                <span className="flex items-center gap-2 text-xs">
                  <span className="text-muted-foreground">{t('sessions.selected', { count: selectedKeys.size })}</span>
                  <button
                    onClick={() => setConfirmingDelete(true)}
                    className="flex items-center gap-1 rounded-lg border border-destructive/30 px-2 py-1 font-medium text-destructive transition-colors hover:bg-destructive/10"
                  >
                    <Trash2 className="h-3 w-3" /> {t('sessions.deleteSelected')}
                  </button>
                  <button
                    onClick={() => setSelectedKeys(new Set())}
                    className="rounded-lg px-2 py-1 text-muted-foreground transition-colors hover:text-foreground"
                  >
                    {t('common.clear')}
                  </button>
                </span>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              {(['lastActivity', 'tokens'] as SortKey[]).map(key => (
                <button
                  key={key}
                  onClick={() => toggleSort(key)}
                  className={`${sortButton} ${
                    sortKey === key
                      ? 'border-foreground/30 bg-muted text-foreground'
                      : 'border-border text-muted-foreground hover:bg-muted/60'
                  }`}
                >
                  {key === 'lastActivity' ? t('sessions.sortDate') : t('sessions.sortTokens')}
                  {sortKey === key && (sortDir === 'asc' ? ' ↑' : ' ↓')}
                </button>
              ))}
              <button
                onClick={reload}
                disabled={loading}
                className={`${sortButton} flex items-center gap-1 border-border text-muted-foreground hover:bg-muted/60 disabled:cursor-not-allowed disabled:opacity-60`}
              >
                <RefreshCw className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} /> {t('common.refresh')}
              </button>
            </div>
          </div>

          {error && (
            <div className="mb-3 flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              <AlertCircle className="h-3.5 w-3.5 shrink-0" />
              {error}
            </div>
          )}

          {deleteError && (
            <div className="mb-3 flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              <AlertCircle className="h-3.5 w-3.5 shrink-0" />
              {deleteError}
            </div>
          )}

          {/* One table, one row per session. The list scrolls inside its own
              box at xl, where the parent pins the page to the viewport. */}
          <div className="glass-card min-h-0 flex-1 divide-y divide-border overflow-y-auto">
            {filtered.map(session => {
              const key = sessionKey(session);
              const isSelected = selectedKey === key;
              const totalTokens = session.inputTokens + session.outputTokens;
              const subtaskCount = session.subtasks?.length ?? 0;
              const engine = findEngine(session.target);
              return (
                <div
                  key={key}
                  role="button"
                  tabIndex={0}
                  aria-pressed={isSelected}
                  aria-label={t('sessions.open', { id: session.sessionId })}
                  className={`flex cursor-pointer flex-col justify-between gap-3 px-4 py-3 transition-colors sm:flex-row sm:items-center ${
                    isSelected ? 'bg-muted' : 'hover:bg-muted/60'
                  }`}
                  onClick={() => setSelectedKey(isSelected ? null : key)}
                  onKeyDown={event => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      setSelectedKey(isSelected ? null : key);
                    }
                  }}
                >
                  <div className="flex min-w-0 flex-1 items-center gap-3">
                    <input
                      type="checkbox"
                      aria-label={t('sessions.select', { id: session.sessionId })}
                      checked={selectedKeys.has(key)}
                      onClick={event => event.stopPropagation()}
                      onChange={() => toggleSelected(key)}
                      className="h-3.5 w-3.5 shrink-0 rounded border-border text-primary focus:ring-primary"
                    />
                    <span className={`h-2 w-2 shrink-0 rounded-full ${engine?.dot ?? 'bg-slate-400'}`} />
                    <div className="flex min-w-0 flex-1 flex-col">
                      <div className="flex min-w-0 items-center gap-2">
                        <span className="truncate text-sm font-medium">
                          {session.title || session.projectPath.split(/[\\/]/).pop() || session.projectPath || '—'}
                        </span>
                        {/* Subagent runs are folded into the session that spawned
                            them; the count is what tells you the row's tokens cover
                            more than one transcript. */}
                        {subtaskCount > 0 && (
                          <span className="shrink-0 rounded-full bg-primary/15 px-2 py-0.5 text-xs font-medium text-primary">
                            {t('sessions.subtaskCount', { count: subtaskCount })}
                          </span>
                        )}
                        {/* A subagent run only reaches top level when its parent is
                            gone -- say the engine pruned that transcript. Marked
                            rather than hidden, so its usage stays visible. */}
                        {session.parentSessionId && (
                          <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                            {t('sessions.orphanSubtask')}
                          </span>
                        )}
                      </div>
                      {/* Under a workspace filter the path is the filter value
                          repeated on every row, so the line goes to the models
                          that actually ran the session. */}
                      <span className="truncate text-xs text-muted-foreground" title={session.projectPath}>
                        <span className="font-medium">{session.target}</span>
                        {' · '}
                        <span>{project ? session.modelsUsed.join(', ') : (session.projectPath || '—')}</span>
                      </span>
                    </div>
                  </div>

                  <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-2">
                    <span className="flex items-center gap-1 font-mono text-xs text-muted-foreground">
                      <FileText className="h-3 w-3" />{fmtTokens(totalTokens)}
                    </span>
                    <span className="flex items-center gap-1 font-mono text-xs text-muted-foreground">
                      <Clock className="h-3 w-3" />
                      {new Date(session.lastActivity).toLocaleDateString()}
                    </span>

                    <div className="flex shrink-0 items-center gap-1.5" onClick={event => event.stopPropagation()}>
                      <button
                        type="button"
                        onClick={() => handleResumeSession(session)}
                        title={t('sessions.resumeTitle')}
                        aria-label={t('sessions.resumeTitle')}
                        className="inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted"
                      >
                        <Play size={11} className="fill-current" />
                        <span className="hidden sm:inline">{t('sessions.resume')}</span>
                      </button>

                      <div className="relative">
                        <button
                          type="button"
                          disabled={handoffLoading === session.sessionId}
                          onClick={() => setHandoffSessionId(prev => prev === session.sessionId ? null : session.sessionId)}
                          title={t('launch.handoffTitle')}
                          aria-label={t('launch.handoffTitle')}
                          className={`inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted ${
                            handoffSessionId === session.sessionId ? 'bg-muted' : ''
                          }`}
                        >
                          {handoffLoading === session.sessionId ? (
                            <Loader2 size={11} className="animate-spin" />
                          ) : (
                            <Zap size={11} className="text-warn" />
                          )}
                          <span className="hidden sm:inline">{t('launch.handoff')}</span>
                          <ChevronDown size={10} className={handoffSessionId === session.sessionId ? 'rotate-180 transition-transform' : 'transition-transform'} />
                        </button>

                        {handoffSessionId === session.sessionId && (
                          <div
                            ref={handoffRef}
                            className="absolute right-0 top-full z-50 mt-1 min-w-36 rounded-xl border border-border bg-popover p-1 shadow-lg"
                          >
                            <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                              {t('launch.handoffTitle')}
                            </div>
                            {AGENT_ENGINES.filter(e => e.id !== session.target).map(target => (
                              <button
                                key={target.id}
                                type="button"
                                disabled={Boolean(handoffLoading)}
                                onClick={() => void handleHandoffSession(session, target.id)}
                                className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs transition-colors hover:bg-muted disabled:opacity-50"
                              >
                                <span className={`h-2 w-2 rounded-full ${target.dot}`} />
                                <span className="font-medium">{target.nameKey ? t(target.nameKey) : target.name}</span>
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>

                    <ChevronRight
                      className={`h-4 w-4 shrink-0 transition-colors ${isSelected ? 'text-foreground' : 'text-muted-foreground/50'}`}
                    />
                  </div>
                </div>
              );
            })}
            {filtered.length === 0 && (
              <EmptyState compact title={t('sessions.empty')} />
            )}

            {nextCursor && (
              <div className="flex flex-col items-center gap-1 py-4">
                <button
                  onClick={loadMore}
                  disabled={loadingMore}
                  className="rounded-lg border border-border px-4 py-1.5 text-xs font-medium transition-colors hover:bg-muted disabled:opacity-50"
                >
                  {loadingMore ? t('sessions.loadingMore') : t('sessions.loadMore')}
                </button>
                <p className="text-[11px] text-muted-foreground">
                  {t('sessions.loadedOfTotal', {
                    loaded: String(sessions.length),
                    total: String(matchCount),
                  })}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* One session, one place: usage, the actual conversation, and the
            actions that operate on it. Wide enough to read a transcript in --
            narrower and every fenced code block gets its own scrollbar. */}
        {openSession && (
          <div className="glass-card w-full shrink-0 p-5 xl:h-full xl:min-h-0 xl:w-[38rem] xl:max-w-[45%] 2xl:w-[46rem]">
            <SessionDetailPanel
              key={selectedKey}
              engine={openSession.target}
              sessionId={openSession.sessionId}
              projectPath={openSession.projectPath}
              usage={openSession}
              onClose={() => setSelectedKey(null)}
              onDeleted={() => dropSession(openSession)}
            />
          </div>
        )}
      </div>

      {confirmingDelete && (
        <ConfirmDialog
          title={
            selectedSessions.length === 1
              ? t('sessions.deleteTitleOne', { count: selectedSessions.length })
              : t('sessions.deleteTitle', { count: selectedSessions.length })
          }
          description={t('sessions.deleteDescription')}
          confirmLabel={deleting ? t('sessions.deleting') : t('common.delete')}
          onConfirm={() => { if (!deleting) void handleBulkDelete(); }}
          onCancel={() => { if (!deleting) setConfirmingDelete(false); }}
        />
      )}
    </div>
  );
}
