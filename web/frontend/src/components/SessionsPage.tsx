import { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import { Link, useSearchParams } from 'react-router';
import { Search, Filter, ChevronDown, ChevronUp, Clock, DollarSign, FileText, AlertCircle, ArrowUpRight, Trash2 } from 'lucide-react';
import { fetchSessions, type SessionUsage, fmtCost, fmtTokens } from '../api/analytics';
import { deleteHistorySession } from '../api/audit';
import { buildEventsLink } from '../utils/sessionLink';
import ConfirmDialog from './shared/ConfirmDialog';
import ErrorState from './shared/ErrorState';

type SortKey = 'lastActivity' | 'cost' | 'tokens';
type SortDir = 'asc' | 'desc';

function sessionKey(session: SessionUsage): string {
  return `${session.target}::${session.sessionId}`;
}

export default function SessionsPage() {
  const [sessions, setSessions] = useState<SessionUsage[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selectedEngines, setSelectedEngines] = useState<string[]>([]);
  const [dateStart, setDateStart] = useState('');
  const [dateEnd, setDateEnd] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('lastActivity');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [expandedId, setExpandedId] = useState<string | null>(null);
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

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    setError(null);
    fetchSessions(500)
      .then(data => {
        if (!mountedRef.current) return;
        setSessions(data);
        setLoading(false);
      })
      .catch(() => {
        if (!mountedRef.current) return;
        setLoading(false);
        setError('Failed to load sessions');
      });
  }, [reloadNonce]);

  const retryLoad = useCallback(() => setReloadNonce(n => n + 1), []);

  // Deep link from the command palette: `?session=<id>` expands that
  // session in place once the list has loaded, instead of forcing the
  // user to re-search for it in the filter box.
  useEffect(() => {
    const sessionId = searchParams.get('session');
    if (sessionId && sessions.some(s => s.sessionId === sessionId)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setExpandedId(sessionId);
    }
  }, [sessions, searchParams]);

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
        s.sessionId.toLowerCase().includes(q)
      );
    }
    if (selectedEngines.length > 0) {
      result = result.filter(s => selectedEngines.includes(s.target));
    }
    if (dateStart) {
      result = result.filter(s => s.lastActivity >= dateStart);
    }
    if (dateEnd) {
      result = result.filter(s => s.lastActivity <= dateEnd + 'T23:59:59');
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

  const toggleEngine = (engine: string) => {
    setSelectedEngines(prev =>
      prev.includes(engine) ? prev.filter(e => e !== engine) : [...prev, engine]
    );
  };

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
        `${failedCount} of ${selectedSessions.length} session${selectedSessions.length === 1 ? '' : 's'} could not be deleted.`,
      );
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col xl:flex-row gap-4 min-h-full xl:h-full animate-fade-in" aria-busy="true" aria-label="Loading sessions">
        <div className="w-full xl:w-56 shrink-0 glass-card p-4 space-y-4">
          <div className="h-4 w-16 rounded bg-slate-100 animate-pulse" />
          <div className="h-8 w-full rounded-lg bg-slate-100 animate-pulse" />
          <div className="space-y-2">
            <div className="h-3 w-24 rounded bg-slate-100 animate-pulse" />
            <div className="h-8 w-full rounded-lg bg-slate-100 animate-pulse" />
            <div className="h-8 w-full rounded-lg bg-slate-100 animate-pulse" />
          </div>
          <div className="space-y-2">
            <div className="h-3 w-16 rounded bg-slate-100 animate-pulse" />
            {[0, 1, 2].map(i => (
              <div key={i} className="h-6 w-full rounded-md bg-slate-100 animate-pulse" />
            ))}
          </div>
        </div>
        <div className="flex-1 min-w-0 glass-card p-5 space-y-2">
          <div className="h-4 w-24 rounded bg-slate-100 animate-pulse mb-4" />
          {[0, 1, 2, 3, 4, 5].map(i => (
            <div key={i} className="border border-slate-100 rounded-xl p-4 flex items-center justify-between gap-3">
              <div className="space-y-2 min-w-0 flex-1">
                <div className="h-3.5 w-40 rounded bg-slate-100 animate-pulse" />
                <div className="h-3 w-64 max-w-full rounded bg-slate-100 animate-pulse" />
              </div>
              <div className="flex items-center gap-4 shrink-0">
                <div className="h-3 w-12 rounded bg-slate-100 animate-pulse" />
                <div className="h-3 w-12 rounded bg-slate-100 animate-pulse" />
                <div className="h-3 w-16 rounded bg-slate-100 animate-pulse" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return <ErrorState message={error} onRetry={retryLoad} />;
  }

  return (
    <div className="flex flex-col xl:flex-row gap-4 min-h-full xl:h-full">
      <aside data-testid="session-filters" className="animate-slide-left stagger-1 w-full xl:w-56 shrink-0 glass-card p-4 space-y-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
          <Filter className="w-4 h-4" /> Filters
        </div>

        <div>
          <label className="text-xs text-slate-400 font-medium block mb-1">Search</label>
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Project or session..."
              className="w-full pl-7 pr-2 py-1.5 text-xs border border-slate-200 rounded-lg bg-white focus:outline-none focus:border-primary"
            />
          </div>
        </div>

        <div>
          <label className="text-xs text-slate-400 font-medium block mb-1">Date Range</label>
          <div className="grid grid-cols-1 gap-2">
            <input
              type="date"
              aria-label="Date range start"
              value={dateStart}
              onChange={e => setDateStart(e.target.value)}
              className="w-full px-2 py-1.5 text-xs border border-slate-200 rounded-lg bg-white focus:outline-none focus:border-primary"
            />
            <input
              type="date"
              aria-label="Date range end"
              value={dateEnd}
              onChange={e => setDateEnd(e.target.value)}
              className="w-full px-2 py-1.5 text-xs border border-slate-200 rounded-lg bg-white focus:outline-none focus:border-primary"
            />
          </div>
        </div>

        <div>
          <label className="text-xs text-slate-400 font-medium block mb-1">Engine</label>
          <div className="space-y-1">
            {engines.map(eng => (
              <button
                key={eng}
                onClick={() => toggleEngine(eng)}
                className={`w-full text-left px-2 py-1 rounded-md text-xs transition-colors ${
                  selectedEngines.includes(eng)
                    ? 'bg-slate-100 text-slate-800 font-medium'
                    : 'text-slate-500 hover:bg-slate-50'
                }`}
              >
                {eng}
              </button>
            ))}
          </div>
        </div>
      </aside>

      <div data-testid="session-list" className="animate-fade-rise stagger-2 flex-1 min-w-0 glass-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-xs text-slate-400 font-medium cursor-pointer select-none">
              <input
                type="checkbox"
                aria-label="Select all sessions matching the current filters"
                checked={allFilteredSelected}
                onChange={toggleSelectAllFiltered}
                disabled={filtered.length === 0}
                className="h-3.5 w-3.5 rounded border-slate-300 text-primary focus:ring-primary"
              />
              {filtered.length} session{filtered.length !== 1 ? 's' : ''}
            </label>
            {selectedKeys.size > 0 && (
              <span className="flex items-center gap-2 text-xs">
                <span className="text-slate-500">{selectedKeys.size} selected</span>
                <button
                  onClick={() => setConfirmingDelete(true)}
                  className="flex items-center gap-1 px-2 py-1 rounded-md border border-red-200 text-red-600 hover:bg-red-50 transition-colors font-medium"
                >
                  <Trash2 className="w-3 h-3" /> Delete selected
                </button>
                <button
                  onClick={() => setSelectedKeys(new Set())}
                  className="px-2 py-1 rounded-md text-slate-400 hover:text-slate-600 transition-colors"
                >
                  Clear
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
                {key === 'lastActivity' ? 'Date' : key === 'cost' ? 'Cost' : 'Tokens'}
                {sortKey === key && (sortDir === 'asc' ? ' ↑' : ' ↓')}
              </button>
            ))}
          </div>
        </div>

        {deleteError && (
          <div className="mb-3 flex items-center gap-2 rounded-lg border border-red-100 bg-red-50/60 px-3 py-2 text-xs text-red-600">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            {deleteError}
          </div>
        )}

        <div className="space-y-2">
          {filtered.map((session, i) => {
            const isExpanded = expandedId === session.sessionId;
            const totalTokens = session.inputTokens + session.outputTokens;
            // Cap stagger at 6 so long lists don't cascade forever — items
            // past the sixth just fade in without a delay.
            const stagger = i < 6 ? `animate-fade-rise stagger-${i + 3}` : 'animate-fade-in';
            return (
              <div
                key={session.sessionId}
                className={`${stagger} border border-slate-100 rounded-xl p-4 hover:bg-slate-50/60 transition-colors`}
              >
                <div
                  role="button"
                  tabIndex={0}
                  aria-expanded={isExpanded}
                  className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 cursor-pointer"
                  onClick={() => setExpandedId(isExpanded ? null : session.sessionId)}
                  onKeyDown={event => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      setExpandedId(isExpanded ? null : session.sessionId);
                    }
                  }}
                >
                  <div className="flex flex-wrap items-center gap-3 min-w-0 flex-1">
                    <input
                      type="checkbox"
                      aria-label={`Select session ${session.sessionId}`}
                      checked={selectedKeys.has(sessionKey(session))}
                      onClick={event => event.stopPropagation()}
                      onChange={() => toggleSelected(sessionKey(session))}
                      className="h-3.5 w-3.5 shrink-0 rounded border-slate-300 text-primary focus:ring-primary"
                    />
                    <div className="flex flex-col min-w-0">
                      <span className="text-sm font-medium text-slate-700 truncate">
                        {session.projectPath.split(/[\\/]/).pop() || session.projectPath || '—'}
                      </span>
                      <span className="text-xs text-slate-400 truncate" title={session.projectPath}>
                        {session.projectPath}
                      </span>
                    </div>
                    <span className="shrink-0 px-2 py-0.5 text-[10px] font-bold rounded-full uppercase bg-slate-100 text-slate-600">
                      {session.target}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-2 shrink-0">
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
                    {isExpanded ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
                  </div>
                </div>

                {isExpanded && (
                  <div className="mt-3 pt-3 border-t border-slate-100">
                    <p className="text-xs text-slate-400 font-medium mb-2">Model Breakdown</p>
                    {session.modelBreakdowns?.length > 0 ? (
                      <div className="space-y-1.5">
                        {session.modelBreakdowns.map((mb, i) => (
                          <div key={i} className="flex flex-wrap items-center justify-between gap-2 text-xs">
                            <span className="min-w-0 break-all text-slate-600 font-mono">{mb.modelName}</span>
                            <div className="flex flex-wrap gap-3 text-slate-500">
                              <span>in: {fmtTokens(mb.inputTokens)}</span>
                              <span>out: {fmtTokens(mb.outputTokens)}</span>
                              <span className="font-semibold text-slate-700">{fmtCost(mb.cost)}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-slate-400">No model breakdown available</p>
                    )}
                    <div className="mt-2 pt-2 border-t border-slate-50 flex flex-wrap items-center gap-4 text-xs text-slate-500">
                      <span>Cache write: {fmtTokens(session.cacheCreationTokens)}</span>
                      <span>Cache read: {fmtTokens(session.cacheReadTokens)}</span>
                      <span className="font-mono text-slate-400 truncate">{session.sessionId}</span>
                      <Link
                        to={buildEventsLink(session.target, session.sessionId, session.projectPath)}
                        onClick={event => event.stopPropagation()}
                        className="ml-auto flex items-center gap-1 font-medium text-primary hover:underline"
                      >
                        View in Events <ArrowUpRight className="h-3 w-3" />
                      </Link>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
          {filtered.length === 0 && (
            <p className="text-sm text-slate-400 text-center py-8">No sessions match your filters</p>
          )}
        </div>
      </div>

      {confirmingDelete && (
        <ConfirmDialog
          title={`Delete ${selectedSessions.length} session${selectedSessions.length === 1 ? '' : 's'}?`}
          description="This permanently removes the underlying history file(s) for the selected sessions. This cannot be undone."
          confirmLabel={deleting ? 'Deleting…' : 'Delete'}
          onConfirm={() => { if (!deleting) void handleBulkDelete(); }}
          onCancel={() => { if (!deleting) setConfirmingDelete(false); }}
        />
      )}
    </div>
  );
}
