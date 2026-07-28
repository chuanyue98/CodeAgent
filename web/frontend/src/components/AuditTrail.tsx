import { useState, useMemo, useEffect } from 'react';
import { useSearchParams } from 'react-router';
import { Search, Filter, ChevronDown, ChevronUp, Clock, Wrench, MessageSquare, AlertCircle, X, RefreshCw, TerminalSquare, Check } from 'lucide-react';
import { fetchAuditEvents, convertAndLaunchSession, type AuditEvent, type AuditEventType, type FetchAuditEventsParams } from '../api/audit';
import request from '../utils/request';

const ENGINE_LABELS: Record<string, string> = {
  claude: 'Claude',
  gemini: 'Gemini',
  opencode: 'OpenCode',
  codex: 'Codex',
};

const ALL_ENGINES = Object.keys(ENGINE_LABELS);

// Server caps /api/history/audit at this many events per request. When the
// response count hits this ceiling there may be more matching events beyond
// what we fetched, so the UI must say so instead of silently truncating.
const EVENT_LIMIT = 1000;

type ConvertState =
  | { status: 'idle' }
  | { status: 'loading'; targetEngine: string }
  | { status: 'success'; targetEngine: string; message: string }
  | { status: 'error'; targetEngine: string; message: string };

interface SessionMessage {
  role: string;
  content: string;
  timestamp: string;
  model: string;
  tool_calls: { name: string; args_preview: string; result_preview: string }[];
}

interface SessionDetail {
  session_id: string;
  engine: string;
  project_path: string;
  title: string;
  messages: SessionMessage[];
}

async function fetchSessionDetail(engine: string, sessionId: string, project: string): Promise<SessionDetail> {
  return request<SessionDetail>(`/api/history/${engine}/${sessionId}?project=${encodeURIComponent(project)}`);
}

export default function AuditTrail() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [selectedEngines, setSelectedEngines] = useState<string[]>([]);
  const [selectedTypes, setSelectedTypes] = useState<AuditEventType[]>([]);
  const [dateStart, setDateStart] = useState('');
  const [dateEnd, setDateEnd] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [drawerSession, setDrawerSession] = useState<{ engine: string; sessionId: string; project: string } | null>(null);
  const [sessionDetail, setSessionDetail] = useState<SessionDetail | null>(null);
  const [sessionLoading, setSessionLoading] = useState(false);
  const [convertState, setConvertState] = useState<ConvertState>({ status: 'idle' });
  const [searchParams] = useSearchParams();
  const [truncated, setTruncated] = useState(false);
  const [reloadNonce, setReloadNonce] = useState(0);

  // Deep link support: /activity/events?session=&engine=&project= auto-opens
  // the matching session's detail drawer, so other pages (History, Workspaces)
  // can link straight to a session instead of making the user re-search for it.
  useEffect(() => {
    const session = searchParams.get('session');
    const engine = searchParams.get('engine');
    const project = searchParams.get('project');
    if (session && engine && project) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setDrawerSession({ engine, sessionId: session, project });
    }
  }, [searchParams]);

  // Only one engine can be sent to the server at a time (single `engine`
  // query param). When the user multi-selects engines we fetch unfiltered
  // and fall back to client-side filtering for that dimension below.
  const engineParam = useMemo(
    () => (selectedEngines.length === 1 ? selectedEngines[0] : undefined),
    [selectedEngines],
  );

  const load = () => setReloadNonce(n => n + 1);

  // Refetches from the server whenever the server-supported filters (date
  // range, single-engine selection) or an explicit refresh change. Using
  // server-side since/until/engine params avoids the old bug where date
  // filtering only ever searched the fixed first 1000 client-cached events.
  useEffect(() => {
    let mounted = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    setError(null);

    const params: FetchAuditEventsParams = { limit: EVENT_LIMIT };
    if (engineParam) params.engine = engineParam;
    if (dateStart) params.since = dateStart;
    if (dateEnd) params.until = `${dateEnd}T23:59:59.999Z`;

    fetchAuditEvents(params)
      .then(data => {
        if (!mounted) return;
        setEvents(data.events);
        setTruncated(data.count >= EVENT_LIMIT);
        setLoading(false);
      })
      .catch(() => {
        if (!mounted) return;
        setLoading(false);
        setError('Failed to load audit events');
      });

    return () => {
      mounted = false;
    };
  }, [engineParam, dateStart, dateEnd, reloadNonce]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setConvertState({ status: 'idle' });
  }, [drawerSession]);

  useEffect(() => {
    if (!drawerSession) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSessionDetail(null);
      return;
    }
    let mounted = true;
    setSessionLoading(true);
    fetchSessionDetail(drawerSession.engine, drawerSession.sessionId, drawerSession.project)
      .then(data => {
        if (!mounted) return;
        setSessionDetail(data);
        setSessionLoading(false);
      })
      .catch(() => {
        if (!mounted) return;
        setSessionLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [drawerSession]);

  // Escape-key support for the session detail drawer (previously only
  // closable by clicking the backdrop or the X button).
  useEffect(() => {
    if (!drawerSession) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setDrawerSession(null);
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [drawerSession]);

  const filtered = useMemo(() => {
    let result = events;
    if (search) {
      const q = search.toLowerCase();
      result = result.filter(e =>
        (e.project_path ?? '').toLowerCase().includes(q) ||
        (e.session_title ?? '').toLowerCase().includes(q) ||
        (e.content_preview ?? '').toLowerCase().includes(q) ||
        (e.tool_name ?? '').toLowerCase().includes(q)
      );
    }
    if (selectedEngines.length > 0) {
      // Server already narrowed to this engine when exactly one was
      // selected (see engineParam); this also covers the multi-select case
      // where filtering has to happen client-side.
      result = result.filter(e => selectedEngines.includes(e.engine));
    }
    if (selectedTypes.length > 0) {
      result = result.filter(e => selectedTypes.includes(e.event_type));
    }
    return result;
  }, [events, search, selectedEngines, selectedTypes]);

  const toggleEngine = (engine: string) => {
    setSelectedEngines(prev => prev.includes(engine) ? prev.filter(e => e !== engine) : [...prev, engine]);
  };

  const toggleType = (type: AuditEventType) => {
    setSelectedTypes(prev => prev.includes(type) ? prev.filter(t => t !== type) : [...prev, type]);
  };

  const handleConvert = async (targetEngine: string) => {
    if (!drawerSession) return;
    setConvertState({ status: 'loading', targetEngine });
    try {
      const result = await convertAndLaunchSession({
        sourceEngine: drawerSession.engine,
        sessionId: drawerSession.sessionId,
        targetEngine,
        projectPath: drawerSession.project,
      });
      setConvertState({
        status: 'success',
        targetEngine,
        message: `Opened in ${ENGINE_LABELS[targetEngine] ?? targetEngine} — new session ${result.newSessionId}`,
      });
    } catch (err) {
      setConvertState({
        status: 'error',
        targetEngine,
        message: err instanceof Error ? err.message : 'Conversion failed',
      });
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="text-sm text-slate-400">Loading audit trail...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="glass-card p-5 flex items-center gap-3 bg-red-50/60 border-red-100">
          <AlertCircle className="w-5 h-5 text-red-500 shrink-0" />
          <span className="font-medium text-red-600 text-sm">{error}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col xl:flex-row gap-4 min-h-full xl:h-full">
      <aside className="w-full xl:w-56 shrink-0 glass-card p-4 space-y-4">
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
              placeholder="Project, session, content..."
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
          <label className="text-xs text-slate-400 font-medium block mb-1">Event Type</label>
          <div className="space-y-1">
            {(['message', 'tool_call'] as AuditEventType[]).map(type => (
              <button
                key={type}
                onClick={() => toggleType(type)}
                className={`w-full text-left px-2 py-1 rounded-md text-xs transition-colors ${
                  selectedTypes.includes(type)
                    ? 'bg-slate-100 text-slate-800 font-medium'
                    : 'text-slate-500 hover:bg-slate-50'
                }`}
              >
                {type === 'message' ? 'Message' : 'Tool Call'}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="text-xs text-slate-400 font-medium block mb-1">Engine</label>
          <div className="space-y-1">
            {ALL_ENGINES.map(eng => (
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

      <div className="flex-1 min-w-0 glass-card p-5 flex flex-col">
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs text-slate-400 font-medium">
            {filtered.length} event{filtered.length !== 1 ? 's' : ''}
          </p>
          <button
            onClick={load}
            className="flex items-center gap-1 px-2 py-1 text-xs rounded-md border border-slate-200 text-slate-500 hover:bg-slate-50 transition-colors"
          >
            <RefreshCw className="w-3 h-3" /> Refresh
          </button>
        </div>
        <p className="text-[11px] text-slate-400 mb-4">
          Message and tool-call history across all engines — not an approval or permission log.
        </p>

        {truncated && (
          <div className="flex items-center gap-2 mb-4 px-3 py-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            仅显示最近 {EVENT_LIMIT} 条事件，可能还有更多匹配结果——请缩小时间范围或按引擎筛选。
          </div>
        )}

        <div className="space-y-2 overflow-y-auto">
          {filtered.map(event => {
            const isExpanded = expandedId === event.event_id;
            return (
              <div
                key={event.event_id}
                className="border border-slate-100 rounded-xl p-4 hover:bg-slate-50/60 transition-colors"
              >
                <div
                  role="button"
                  tabIndex={0}
                  aria-expanded={isExpanded}
                  className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 cursor-pointer"
                  onClick={() => setExpandedId(isExpanded ? null : event.event_id)}
                  onKeyDown={keyboardEvent => {
                    if (keyboardEvent.key === 'Enter' || keyboardEvent.key === ' ') {
                      keyboardEvent.preventDefault();
                      setExpandedId(isExpanded ? null : event.event_id);
                    }
                  }}
                >
                  <div className="flex flex-wrap items-center gap-3 min-w-0 flex-1">
                    {event.event_type === 'tool_call'
                      ? <Wrench className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      : <MessageSquare className="w-3.5 h-3.5 text-slate-400 shrink-0" />}
                    <div className="flex flex-col min-w-0">
                      <span className="text-sm font-medium text-slate-700 truncate">
                        {event.event_type === 'tool_call' ? event.tool_name : `${event.role}: ${(event.content_preview ?? '').slice(0, 80)}`}
                      </span>
                      <span className="text-xs text-slate-400 truncate">{event.session_title || event.project_path}</span>
                    </div>
                    <span className="shrink-0 px-2 py-0.5 text-[10px] font-bold rounded-full uppercase bg-slate-100 text-slate-600">
                      {event.engine}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-4 shrink-0">
                    <span className="text-xs text-slate-400 flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {event.timestamp ? new Date(event.timestamp).toLocaleString() : '—'}
                    </span>
                    {isExpanded ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
                  </div>
                </div>

                {isExpanded && (
                  <div className="mt-3 pt-3 border-t border-slate-100 text-xs text-slate-600 space-y-2">
                    {event.event_type === 'message' ? (
                      <p className="whitespace-pre-wrap break-words">{event.content_preview || '(empty)'}</p>
                    ) : (
                      <>
                        <div><span className="text-slate-400">args: </span><span className="font-mono break-words">{event.args_preview || '—'}</span></div>
                        <div><span className="text-slate-400">result: </span><span className="font-mono break-words">{event.result_preview || '—'}</span></div>
                      </>
                    )}
                    <button
                      onClick={() => setDrawerSession({ engine: event.engine, sessionId: event.session_id, project: event.project_path })}
                      className="text-primary text-xs font-medium hover:underline"
                    >
                      View full session →
                    </button>
                  </div>
                )}
              </div>
            );
          })}
          {filtered.length === 0 && (
            <p className="text-sm text-slate-400 text-center py-8">No events match your filters</p>
          )}
        </div>
      </div>

      {drawerSession && (
        <div className="fixed inset-0 bg-black/20 flex justify-end z-50" role="presentation" onClick={() => setDrawerSession(null)}>
          <div
            className="w-[32rem] max-w-full h-full bg-white shadow-xl overflow-y-auto p-5"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-slate-700 truncate">
                {sessionDetail?.title || drawerSession.sessionId}
              </h3>
              <button aria-label="Close session details" onClick={() => setDrawerSession(null)} className="text-slate-400 hover:text-slate-600">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="mb-4 pb-4 border-b border-slate-100">
              <p className="text-xs text-slate-400 font-medium mb-2">Convert &amp; open in another engine</p>
              <div className="flex flex-wrap gap-2">
                {ALL_ENGINES.filter(engine => engine !== drawerSession.engine).map(engine => (
                  <button
                    key={engine}
                    disabled={convertState.status === 'loading'}
                    onClick={() => handleConvert(engine)}
                    className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    <TerminalSquare className="w-3.5 h-3.5" />
                    {ENGINE_LABELS[engine]}
                    {convertState.status === 'loading' && convertState.targetEngine === engine && '…'}
                  </button>
                ))}
              </div>
              {convertState.status === 'success' && (
                <p className="mt-2 flex items-center gap-1.5 text-xs text-emerald-600">
                  <Check className="w-3.5 h-3.5 shrink-0" /> {convertState.message}
                </p>
              )}
              {convertState.status === 'error' && (
                <p className="mt-2 flex items-center gap-1.5 text-xs text-red-600">
                  <AlertCircle className="w-3.5 h-3.5 shrink-0" /> {convertState.message}
                </p>
              )}
            </div>

            {sessionLoading && <p className="text-xs text-slate-400">Loading...</p>}
            {!sessionLoading && sessionDetail && (
              <div className="space-y-3">
                {sessionDetail.messages.map((msg, i) => (
                  <div key={`${msg.timestamp}-${msg.role}-${i}`} className="border border-slate-100 rounded-lg p-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-semibold text-slate-600 uppercase">{msg.role}</span>
                      <span className="text-[10px] text-slate-400">{msg.timestamp ? new Date(msg.timestamp).toLocaleString() : ''}</span>
                    </div>
                    <p className="text-xs text-slate-600 whitespace-pre-wrap break-words">{msg.content}</p>
                    {msg.tool_calls?.length > 0 && (
                      <div className="mt-2 space-y-1">
                        {msg.tool_calls.map((tc, j) => (
                          <div key={`${tc.name}-${j}`} className="text-[11px] bg-slate-50 rounded p-1.5">
                            <span className="font-mono font-semibold">{tc.name}</span>
                            {tc.args_preview && <span className="text-slate-500"> — {tc.args_preview}</span>}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
            {!sessionLoading && !sessionDetail && (
              <p className="text-xs text-slate-400">Failed to load session.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
