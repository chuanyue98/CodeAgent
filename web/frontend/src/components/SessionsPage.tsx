import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import {
  AlertCircle,
  ChevronDown,
  ChevronUp,
  Clock,
  FileText,
  Filter,
  Play,
  Search,
  Trash2,
  ArrowUpRight,
  LoaderCircle,
  Send,
} from 'lucide-react';
import {
  continueHistorySession,
  fetchAllHistorySessions,
  fetchHistorySessionDetail,
} from '../api/agent';
import { convertAndLaunchSession, deleteHistorySession } from '../api/audit';
import { buildEventsLink } from '../utils/sessionLink';
import type { HistorySessionDetail, NativeAgentSession } from '../types/agent';
import ConfirmDialog from './shared/ConfirmDialog';
import ErrorState from './shared/ErrorState';

const TARGET_ENGINES = ['claude', 'gemini', 'opencode', 'codex'];

function sessionKey(session: NativeAgentSession): string {
  return `${session.engine}::${session.session_id}`;
}

function folderName(path: string): string {
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1] || path;
}

function formatDate(iso: string): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

type DetailState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'loaded'; detail: HistorySessionDetail };

export default function SessionsPage() {
  const [sessions, setSessions] = useState<NativeAgentSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);

  const [search, setSearch] = useState('');
  const [selectedEngines, setSelectedEngines] = useState<string[]>([]);
  const [expanded, setExpanded] = useState<Record<string, DetailState>>({});
  const [searchParams] = useSearchParams();

  // per-row actions / feedback — concurrent safe via Set
  const [busyKeys, setBusyKeys] = useState<Set<string>>(new Set());
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [convertTargets, setConvertTargets] = useState<Record<string, string>>({});

  // bulk delete
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const mountedRef = useRef(true);
  const expandedControllersRef = useRef<Map<string, AbortController>>(new Map());
  useEffect(() => {
    return () => {
      mountedRef.current = false;
      // abort any in-flight detail fetches on unmount
      expandedControllersRef.current.forEach(c => c.abort());
      expandedControllersRef.current.clear();
    };
  }, []);

  // prunes stale expanded keys when session list refreshes
  useEffect(() => {
    if (sessions.length === 0) return;
    const live = new Set(sessions.map(sessionKey));
    setExpanded(prev => {
      const next: Record<string, DetailState> = {};
      let changed = false;
      for (const [k, v] of Object.entries(prev)) {
        if (live.has(k)) next[k] = v;
        else changed = true;
      }
      return changed ? next : prev;
    });
  }, [sessions]);

  useEffect(() => {
    const controller = new AbortController();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    setError(null);
    fetchAllHistorySessions(500)
      .then(data => {
        if (controller.signal.aborted || !mountedRef.current) return;
        setSessions(data);
        setLoading(false);
      })
      .catch((e: unknown) => {
        if (controller.signal.aborted || !mountedRef.current) return;
        setLoading(false);
        setError(e instanceof Error ? e.message : 'Failed to load sessions');
      });
    return () => controller.abort();
  }, [reloadNonce]);

  useEffect(() => {
    const sessionId = searchParams.get('session');
    if (!sessionId) return;
    const match = sessions.find(s => s.session_id === sessionId);
    if (match) {
      const key = sessionKey(match);
      // directly trigger detail load with abort protection
      const existing = expanded[key];
      if (existing?.status === 'loaded' || existing?.status === 'loading') return;
      const controller = new AbortController();
      expandedControllersRef.current.set(key, controller);
      setExpanded(prev => ({ ...prev, [key]: { status: 'loading' } }));
      void fetchHistorySessionDetail(match.engine, match.session_id, match.project_path)
        .then(detail => {
          if (controller.signal.aborted || !mountedRef.current) return;
          setExpanded(prev => ({ ...prev, [key]: { status: 'loaded', detail } }));
        })
        .catch(() => {
          if (controller.signal.aborted || !mountedRef.current) return;
          setExpanded(prev => ({
            ...prev,
            [key]: { status: 'error', message: 'Failed to load conversation' },
          }));
        })
        .finally(() => {
          expandedControllersRef.current.delete(key);
        });
    }
  }, [sessions, searchParams, expanded]);

  const engines = useMemo(() => {
    const set = new Set(sessions.map(s => s.engine));
    return Array.from(set).sort();
  }, [sessions]);

  const filtered = useMemo(() => {
    let result = sessions;
    if (search) {
      const q = search.toLowerCase();
      result = result.filter(
        s =>
          (s.title ?? '').toLowerCase().includes(q) ||
          s.project_path.toLowerCase().includes(q) ||
          s.session_id.toLowerCase().includes(q),
      );
    }
    if (selectedEngines.length > 0) {
      result = result.filter(s => selectedEngines.includes(s.engine));
    }
    result = [...result].sort((a, b) => {
      const ta = new Date(a.started_at).getTime() || 0;
      const tb = new Date(b.started_at).getTime() || 0;
      return tb - ta;
    });
    return result;
  }, [sessions, search, selectedEngines]);

  const toggleEngine = (engine: string) => {
    setSelectedEngines(prev =>
      prev.includes(engine) ? prev.filter(e => e !== engine) : [...prev, engine],
    );
  };

  const toggleSelected = (key: string) => {
    setSelectedKeys(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const allFilteredSelected =
    filtered.length > 0 && filtered.every(s => selectedKeys.has(sessionKey(s)));

  const toggleSelectAllFiltered = () => {
    setSelectedKeys(prev => {
      const next = new Set(prev);
      if (allFilteredSelected) {
        filtered.forEach(s => next.delete(sessionKey(s)));
      } else {
        filtered.forEach(s => next.add(sessionKey(s)));
      }
      return next;
    });
  };

  const selectedSessions = useMemo(
    () => sessions.filter(s => selectedKeys.has(sessionKey(s))),
    [sessions, selectedKeys],
  );

  const handleBulkDelete = async () => {
    setDeleting(true);
    try {
      const results = await Promise.allSettled(
        selectedSessions.map(s =>
          deleteHistorySession(s.engine, s.session_id, s.project_path),
        ),
      );
      const deletedKeys = new Set(
        selectedSessions
          .filter((_s, i) => results[i].status === 'fulfilled')
          .map(sessionKey),
      );
      const failed = results.filter(r => r.status === 'rejected').length;
      if (!mountedRef.current) return;
      setSessions(prev => prev.filter(s => !deletedKeys.has(sessionKey(s))));
      setSelectedKeys(prev => {
        const next = new Set(prev);
        deletedKeys.forEach(key => next.delete(key));
        return next;
      });
      if (failed > 0) {
        setActionMessage(`Deleted ${deletedKeys.size}, failed ${failed} — check permissions or if file is in use`);
      } else if (deletedKeys.size > 0) {
        setActionMessage(`Deleted ${deletedKeys.size} session(s)`);
      }
    } finally {
      if (mountedRef.current) {
        setDeleting(false);
        setConfirmingDelete(false);
      }
    }
  };

  const setBusy = (key: string, busy: boolean) => {
    setBusyKeys(prev => {
      const next = new Set(prev);
      if (busy) next.add(key);
      else next.delete(key);
      return next;
    });
  };

  const handleContinue = async (session: NativeAgentSession) => {
    const key = sessionKey(session);
    setBusy(key, true);
    setActionMessage(null);
    try {
      await continueHistorySession(session.engine, session.session_id, session.project_path);
      if (!mountedRef.current) return;
      setActionMessage(`Opened in ${session.engine} — new terminal`);
    } catch (e) {
      if (!mountedRef.current) return;
      setActionMessage(e instanceof Error ? e.message : 'Failed to open terminal');
    } finally {
      if (mountedRef.current) setBusy(key, false);
    }
  };

  const handleConvertLaunch = async (session: NativeAgentSession, targetEngine: string) => {
    const key = sessionKey(session);
    setBusy(key, true);
    setActionMessage(null);
    try {
      const result = await convertAndLaunchSession({
        sourceEngine: session.engine,
        sessionId: session.session_id,
        targetEngine,
        projectPath: session.project_path,
      });
      if (!mountedRef.current) return;
      setActionMessage(`Converted to ${targetEngine}; launched (new session ${result.newSessionId})`);
    } catch (e) {
      if (!mountedRef.current) return;
      setActionMessage(e instanceof Error ? e.message : 'Conversion failed');
    } finally {
      if (mountedRef.current) setBusy(key, false);
    }
  };

  const handleToggleDetail = (session: NativeAgentSession) => {
    const target = sessionKey(session);
    const cur = expanded[target];
    if (cur?.status === 'loaded' || cur?.status === 'error') {
      // collapse — abort if still loading
      const ctrl = expandedControllersRef.current.get(target);
      if (ctrl) {
        ctrl.abort();
        expandedControllersRef.current.delete(target);
      }
      setExpanded(prev => {
        const next = { ...prev };
        delete next[target];
        return next;
      });
      return;
    }
    if (cur?.status === 'loading') return;
    const controller = new AbortController();
    // abort previous controller for same key if any
    expandedControllersRef.current.get(target)?.abort();
    expandedControllersRef.current.set(target, controller);
    setExpanded(prev => ({ ...prev, [target]: { status: 'loading' } }));
    void fetchHistorySessionDetail(session.engine, session.session_id, session.project_path)
      .then(detail => {
        if (controller.signal.aborted || !mountedRef.current) return;
        setExpanded(prev => ({ ...prev, [target]: { status: 'loaded', detail } }));
      })
      .catch(() => {
        if (controller.signal.aborted || !mountedRef.current) return;
        setExpanded(prev => ({
          ...prev,
          [target]: { status: 'error', message: 'Failed to load conversation' },
        }));
      })
      .finally(() => {
        if (expandedControllersRef.current.get(target) === controller) {
          expandedControllersRef.current.delete(target);
        }
      });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-full" aria-busy="true">
        <LoaderCircle className="animate-spin h-6 w-6 text-primary" />
        <span className="ml-2 text-sm text-slate-400">Loading sessions…</span>
      </div>
    );
  }

  if (error) {
    return <ErrorState message={error} onRetry={() => setReloadNonce(n => n + 1)} />;
  }

  return (
    <div className="flex flex-col xl:flex-row gap-4 min-h-full">
      <aside data-testid="session-filters" className="w-full xl:w-56 shrink-0 glass-card p-4 space-y-4">
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
              placeholder="Title, project or id…"
              className="w-full pl-7 pr-2 py-1.5 text-xs border border-slate-200 rounded-lg bg-white focus:outline-none focus:border-primary"
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

      <div className="flex-1 min-w-0 glass-card p-5">
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
        </div>

        {actionMessage && (
          <div className="mb-3 flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            {actionMessage}
          </div>
        )}

        <div className="space-y-2">
          {filtered.map(session => {
            const key = sessionKey(session);
            const state = expanded[key];
            const isExpanded = !!state && state.status !== 'loading' && state.status !== undefined;
            const isLoading = state?.status === 'loading';
            return (
              <div key={key} className="border border-slate-100 rounded-xl p-4 hover:bg-slate-50/60 transition-colors">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    <input
                      type="checkbox"
                      aria-label={`Select session ${session.session_id}`}
                      checked={selectedKeys.has(key)}
                      onChange={() => toggleSelected(key)}
                      className="h-3.5 w-3.5 shrink-0 rounded border-slate-300 text-primary focus:ring-primary"
                    />
                    <div className="flex flex-col min-w-0">
                      <span className="text-sm font-medium text-slate-700 truncate">
                        {session.title || 'Untitled'}
                      </span>
                      <span className="text-xs text-slate-400 truncate" title={session.project_path}>
                        {folderName(session.project_path)} · {session.project_path}
                      </span>
                    </div>
                    <span className="shrink-0 px-2 py-0.5 text-[10px] font-bold rounded-full uppercase bg-slate-100 text-slate-600">
                      {session.engine}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-2 shrink-0">
                    <span className="text-xs text-slate-400 flex items-center gap-1">
                      <FileText className="w-3 h-3" /> {session.message_count} msgs
                    </span>
                    <span className="text-xs text-slate-400 flex items-center gap-1">
                      <Clock className="w-3 h-3" /> {formatDate(session.started_at)}
                    </span>
                    <button
                      onClick={() => handleToggleDetail(session)}
                      aria-label={isExpanded || isLoading ? 'Collapse conversation' : 'Expand conversation'}
                      className="p-1 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                    >
                      {isLoading ? (
                        <LoaderCircle className="w-4 h-4 animate-spin" />
                      ) : isExpanded ? (
                        <ChevronUp className="w-4 h-4" />
                      ) : (
                        <ChevronDown className="w-4 h-4" />
                      )}
                    </button>
                  </div>
                </div>

                {isExpanded && state.status === 'loaded' && (
                  <ConversationDetail
                    detail={state.detail}
                    sessionKey={key}
                    busy={busyKeys.has(key)}
                    convertTarget={convertTargets[key] || ''}
                    onConvertTarget={target =>
                      setConvertTargets(prev => ({ ...prev, [key]: target }))
                    }
                    onContinue={() => handleContinue(session)}
                    onConvert={target => handleConvertLaunch(session, target)}
                  />
                )}
                {state?.status === 'error' && (
                  <p className="mt-3 pt-3 border-t border-slate-100 text-xs text-red-500">{state.message}</p>
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

function ConversationDetail(props: {
  detail: HistorySessionDetail;
  sessionKey: string;
  busy: boolean;
  convertTarget: string;
  onConvertTarget: (engine: string) => void;
  onContinue: () => void;
  onConvert: (engine: string) => void;
}) {
  const { detail, convertTarget, onContinue, onConvert } = props;
  const busy = props.busy;
  return (
    <div className="mt-3 pt-3 border-t border-slate-100">
      <div className="space-y-2 max-h-96 overflow-y-auto custom-scrollbar">
        {detail.messages.length === 0 && (
          <p className="text-xs text-slate-400">No messages</p>
        )}
        {detail.messages.map((msg, i) => (
          <div key={i} className="rounded-lg border border-slate-100 p-3">
            <div className="flex items-center justify-between gap-2 mb-1">
              <span
                className={`px-1.5 py-0.5 text-[10px] font-bold uppercase rounded ${
                  msg.role === 'user'
                    ? 'bg-primary/10 text-primary'
                    : 'bg-slate-100 text-slate-500'
                }`}
              >
                {msg.role}
              </span>
              {msg.model && <span className="text-[10px] text-slate-400 font-mono">{msg.model}</span>}
            </div>
            {msg.content && (
              <p className="text-xs text-slate-700 whitespace-pre-wrap">{msg.content}</p>
            )}
            {msg.tool_calls.length > 0 && (
              <div className="mt-2 space-y-1">
                {msg.tool_calls.map((tc, j) => (
                  <div key={j} className="rounded bg-slate-50 px-2 py-1 text-[11px] font-mono text-slate-500">
                    <span className="font-semibold text-slate-700">⚙ {tc.name}</span>
                    {tc.args_preview && <span className="ml-1 text-slate-400">{tc.args_preview}</span>}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="mt-2 pt-2 border-t border-slate-50 flex flex-wrap items-center gap-2 text-xs">
        <button
          onClick={onContinue}
          disabled={busy}
          className="flex items-center gap-1 px-2 py-1 rounded-md border border-primary/30 text-primary hover:bg-primary/10 disabled:opacity-50 font-medium"
        >
          <Play className="w-3 h-3" /> Continue
        </button>

        <select
          value={convertTarget}
          onChange={e => props.onConvertTarget(e.target.value)}
          className="px-2 py-1 text-xs border border-slate-200 rounded-md bg-white text-slate-600 focus:outline-none"
        >
          <option value="" disabled>Convert to…</option>
          {TARGET_ENGINES.filter(e => e !== detail.engine).map(e => (
            <option key={e} value={e}>{e}</option>
          ))}
        </select>
        <button
          onClick={() => convertTarget && onConvert(convertTarget)}
          disabled={busy || !convertTarget}
          className="flex items-center gap-1 px-2 py-1 rounded-md border border-slate-200 text-slate-500 hover:bg-slate-50 disabled:opacity-50 font-medium"
        >
          {busy ? <LoaderCircle className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
          Convert &amp; Launch
        </button>

        <Link
          to={buildEventsLink(detail.engine, detail.session_id, detail.project_path)}
          className="ml-auto flex items-center gap-1 font-medium text-primary hover:underline"
        >
          View in Events <ArrowUpRight className="h-3 w-3" />
        </Link>
      </div>
    </div>
  );
}
