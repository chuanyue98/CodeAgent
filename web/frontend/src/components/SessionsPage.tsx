import { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import { useIsMounted, useLatestRequest } from '../hooks/useAsyncGuards';
import { useSearchParams } from 'react-router';
import { ChevronRight, Clock, DollarSign, FileText, AlertCircle, RefreshCw, Trash2 } from 'lucide-react';
import { fetchSessionPage, type SessionUsage, fmtCost, fmtTokens } from '../api/analytics';
import { deleteHistorySession } from '../api/audit';
import useActivityFilters from '../hooks/useActivityFilters';
import { useT } from '../i18n/context';
import { isWithinLocalDayRange } from '../utils/dateRange';
import ActivityFilterPanel from './ActivityFilterPanel';
import { eb } from './analytics/present';
import SessionDetailPanel from './SessionDetailPanel';
import ConfirmDialog from './shared/ConfirmDialog';
import EmptyState from './shared/EmptyState';
import ErrorState from './shared/ErrorState';
import FilterListSkeleton from './shared/FilterListSkeleton';

type SortKey = 'lastActivity' | 'cost' | 'tokens';
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
      else if (sortKey === 'cost') cmp = a.cost - b.cost;
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

  return (
    <div className="flex flex-col xl:flex-row gap-4 min-h-full xl:h-full">
      <ActivityFilterPanel
        filters={filters}
        engineOptions={engines}
        searchPlaceholder={t('sessions.searchPlaceholder')}
      />

      <div data-testid="session-list" className="animate-fade-rise stagger-2 flex-1 min-w-0 glass-card-flat p-5 flex flex-col">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-xs text-slate-400 font-medium cursor-pointer select-none">
              <input
                type="checkbox"
                aria-label={t('sessions.selectAllFiltered')}
                checked={allFilteredSelected}
                onChange={toggleSelectAllFiltered}
                disabled={filtered.length === 0}
                className="h-3.5 w-3.5 rounded border-slate-300 text-primary focus:ring-primary"
              />
              {filtered.length === 1
                ? t('sessions.countOne', { count: filtered.length })
                : t('sessions.count', { count: filtered.length })}
            </label>
            {selectedKeys.size > 0 && (
              <span className="flex items-center gap-2 text-xs">
                <span className="text-slate-500">{t('sessions.selected', { count: selectedKeys.size })}</span>
                <button
                  onClick={() => setConfirmingDelete(true)}
                  className="flex items-center gap-1 px-2 py-1 rounded-md border border-red-200 text-red-600 hover:bg-red-50 transition-colors font-medium"
                >
                  <Trash2 className="w-3 h-3" /> {t('sessions.deleteSelected')}
                </button>
                <button
                  onClick={() => setSelectedKeys(new Set())}
                  className="px-2 py-1 rounded-md text-slate-400 hover:text-slate-600 transition-colors"
                >
                  {t('common.clear')}
                </button>
              </span>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {(['lastActivity', 'cost', 'tokens'] as SortKey[]).map(key => (
              <button
                key={key}
                onClick={() => toggleSort(key)}
                className={`px-2 py-1 text-xs rounded-md border transition-colors ${
                  sortKey === key
                    ? 'bg-slate-100 border-slate-300 text-slate-800'
                    : 'border-slate-200 text-slate-500 hover:bg-slate-50'
                }`}
              >
                {key === 'lastActivity' ? t('sessions.sortDate') : key === 'cost' ? t('sessions.sortCost') : t('sessions.sortTokens')}
                {sortKey === key && (sortDir === 'asc' ? ' ↑' : ' ↓')}
              </button>
            ))}
            <button
              onClick={reload}
              disabled={loading}
              className="flex items-center gap-1 px-2 py-1 text-xs rounded-md border border-slate-200 text-slate-500 hover:bg-slate-50 transition-colors disabled:cursor-not-allowed disabled:opacity-60"
            >
              <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} /> {t('common.refresh')}
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-3 flex items-center gap-2 rounded-lg border border-red-100 bg-red-50/60 px-3 py-2 text-xs text-red-600">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            {error}
          </div>
        )}

        {deleteError && (
          <div className="mb-3 flex items-center gap-2 rounded-lg border border-red-100 bg-red-50/60 px-3 py-2 text-xs text-red-600">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            {deleteError}
          </div>
        )}

        {/* The parent pins this card to the viewport height at xl, so the rows
            have to scroll inside it — without this they overflow a card whose
            overflow is visible and paint outside its background. Timeline and
            Schedules already do it this way. */}
        <div className="space-y-2 flex-1 min-h-0 overflow-y-auto">
          {filtered.map(session => {
            const key = sessionKey(session);
            const isSelected = selectedKey === key;
            const totalTokens = session.inputTokens + session.outputTokens;
            const subtaskCount = session.subtasks?.length ?? 0;
            return (
              <div
                key={key}
                className={`animate-fade-rise rounded-xl border p-4 transition-colors ${
                  isSelected
                    ? 'border-primary/40 bg-primary/[0.04]'
                    : 'border-slate-100 hover:bg-slate-50/60'
                }`}
              >
                <div
                  role="button"
                  tabIndex={0}
                  aria-pressed={isSelected}
                  aria-label={t('sessions.open', { id: session.sessionId })}
                  className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 cursor-pointer"
                  onClick={() => setSelectedKey(isSelected ? null : key)}
                  onKeyDown={event => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      setSelectedKey(isSelected ? null : key);
                    }
                  }}
                >
                  <div className="flex flex-wrap items-center gap-3 min-w-0 flex-1">
                    <input
                      type="checkbox"
                      aria-label={t('sessions.select', { id: session.sessionId })}
                      checked={selectedKeys.has(key)}
                      onClick={event => event.stopPropagation()}
                      onChange={() => toggleSelected(key)}
                      className="h-3.5 w-3.5 shrink-0 rounded border-slate-300 text-primary focus:ring-primary"
                    />
                    <div className="flex flex-col min-w-0">
                      <span className="text-sm font-medium text-slate-700 truncate">
                        {session.title || session.projectPath.split(/[\\/]/).pop() || session.projectPath || '—'}
                      </span>
                      {/* Under a workspace filter the path is the filter value
                          repeated on every row, so the line goes to the models
                          that actually ran the session -- which the list shows
                          nowhere else. */}
                      <span
                        className="text-xs text-slate-400 truncate"
                        title={session.projectPath}
                      >
                        {project
                          ? session.modelsUsed.join(', ')
                          : session.projectPath}
                      </span>
                    </div>
                    <span className={`shrink-0 px-2 py-0.5 text-[10px] font-bold rounded-full uppercase ${eb(session.target)}`}>
                      {session.target}
                    </span>
                    {/* Subagent runs are folded into the session that spawned
                        them; the count is what tells you the row's tokens and
                        cost cover more than one transcript. */}
                    {subtaskCount > 0 && (
                      <span className="shrink-0 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold text-primary">
                        {t('sessions.subtaskCount', { count: subtaskCount })}
                      </span>
                    )}
                    {/* A subagent run only reaches top level when its parent is
                        gone -- say the engine pruned that transcript. Marked
                        rather than hidden, so its cost stays visible. */}
                    {session.parentSessionId && (
                      <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[10px] font-semibold text-muted-foreground">
                        {t('sessions.orphanSubtask')}
                      </span>
                    )}
                  </div>
                  {/* Allowed to shrink: it already wraps its chips, but
                      `shrink-0` kept them on one line and gave the whole row a
                      hard minimum width, so a narrower list scrolled sideways
                      instead of wrapping. */}
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-2 min-w-0">
                    <span className="text-xs text-slate-500 flex items-center gap-1">
                      <FileText className="w-3 h-3" />{fmtTokens(totalTokens)}
                    </span>
                    <span className="text-xs text-slate-500 flex items-center gap-1">
                      <DollarSign className="w-3 h-3" />{fmtCost(session.cost)}
                    </span>
                    <span className="text-xs text-slate-400 flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {new Date(session.lastActivity).toLocaleDateString()}
                    </span>
                    <ChevronRight
                      className={`w-4 h-4 transition-colors ${isSelected ? 'text-primary' : 'text-slate-300'}`}
                    />
                  </div>
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
                className="rounded-lg border border-slate-200 px-4 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-50 disabled:opacity-50"
              >
                {loadingMore ? t('sessions.loadingMore') : t('sessions.loadMore')}
              </button>
              <p className="text-[11px] text-slate-400">
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
          actions that operate on it. Reading a transcript used to mean
          hopping to the Events tab and re-finding the session there. */}
      {/* Wide enough to read a transcript in: at 26rem the markdown body was
          narrower than the code blocks inside it, so every fenced block got its
          own horizontal scrollbar. Steps up on larger screens, where the list
          has width to spare. */}
      {openSession && (
        <div className="w-full xl:w-[38rem] xl:max-w-[45%] 2xl:w-[46rem] shrink-0 glass-card-flat p-5 xl:h-full xl:min-h-0">
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
