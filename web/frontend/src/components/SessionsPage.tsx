import { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import { useSearchParams } from 'react-router';
import { ChevronRight, Clock, DollarSign, FileText, AlertCircle, RefreshCw, Trash2 } from 'lucide-react';
import { fetchSessions, type SessionUsage, fmtCost, fmtTokens } from '../api/analytics';
import { deleteHistorySession } from '../api/audit';
import useActivityFilters from '../hooks/useActivityFilters';
import { useT } from '../i18n/context';
import { isWithinLocalDayRange } from '../utils/dateRange';
import ActivityFilterPanel from './ActivityFilterPanel';
import SessionDetailPanel from './SessionDetailPanel';
import ConfirmDialog from './shared/ConfirmDialog';
import ErrorState from './shared/ErrorState';
import FilterListSkeleton from './shared/FilterListSkeleton';

type SortKey = 'lastActivity' | 'cost' | 'tokens';
type SortDir = 'asc' | 'desc';

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

  // Guards setState calls in the async fetch below from firing after the
  // component has unmounted (e.g. a fast page switch while the request is
  // still in flight).
  const mountedRef = useRef(true);
  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // Project narrowing happens server-side: the response is capped at 500
  // sessions across every project, so filtering here instead would let a busy
  // neighbouring project crowd the selected one out of the window.
  useEffect(() => {
    if (!ready) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    setError(null);
    fetchSessions(500, project || undefined)
      .then(data => {
        if (!mountedRef.current) return;
        setSessions(data);
        setLoading(false);
      })
      .catch(() => {
        if (!mountedRef.current) return;
        setLoading(false);
        setError(t('sessions.loadFailed'));
      });
  }, [project, ready, reloadNonce, t]);

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

  const filtered = useMemo(() => {
    let result = sessions;
    if (search) {
      const q = search.toLowerCase();
      result = result.filter(s =>
        s.projectPath.toLowerCase().includes(q) ||
        s.sessionId.toLowerCase().includes(q) ||
        (s.title || '').toLowerCase().includes(q)
      );
    }
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
  }, [sessions, search, selectedEngines, dateStart, dateEnd, sortKey, sortDir]);

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
          {filtered.map((session, i) => {
            const key = sessionKey(session);
            const isSelected = selectedKey === key;
            const totalTokens = session.inputTokens + session.outputTokens;
            // Cap stagger at 6 so long lists don't cascade forever — items
            // past the sixth just fade in without a delay.
            const stagger = i < 6 ? `animate-fade-rise stagger-${i + 3}` : 'animate-fade-in';
            return (
              <div
                key={key}
                className={`${stagger} rounded-xl border p-4 transition-colors ${
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
                      <span className="text-xs text-slate-400 truncate" title={session.projectPath}>
                        {session.projectPath}
                      </span>
                    </div>
                    <span className="shrink-0 px-2 py-0.5 text-[10px] font-bold rounded-full uppercase bg-slate-100 text-slate-600">
                      {session.target}
                    </span>
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
            <p className="text-sm text-slate-400 text-center py-8">{t('sessions.empty')}</p>
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
