import { useState, useMemo, useEffect } from 'react';
import { useSearchParams } from 'react-router';
import { ChevronDown, ChevronUp, Clock, Wrench, MessageSquare, AlertCircle, RefreshCw } from 'lucide-react';
import { fetchAuditEvents, type AuditEvent, type FetchAuditEventsParams } from '../api/audit';
import useActivityFilters from '../hooks/useActivityFilters';
import { localDayEndISO, localDayStartISO } from '../utils/dateRange';
import { ALL_ENGINES } from '../utils/engines';
import ActivityFilterPanel from './ActivityFilterPanel';
import SessionDetailPanel from './SessionDetailPanel';
import ErrorState from './shared/ErrorState';
import FilterListSkeleton from './shared/FilterListSkeleton';

// How many events we ask for per engine. The server allows up to 5000, but a
// page this size already renders every event as its own DOM node. When a
// response comes back at the ceiling there may be more matching events beyond
// what we fetched, so the UI must say so instead of silently truncating.
const EVENT_LIMIT = 1000;

function eventTime(event: AuditEvent): number {
  const at = new Date(event.timestamp).getTime();
  return Number.isNaN(at) ? 0 : at;
}

export default function AuditTrail() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const filters = useActivityFilters();
  const {
    search,
    dateStart,
    dateEnd,
    engines: selectedEngines,
    types: selectedTypes,
    project,
    ready,
  } = filters;
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [drawerSession, setDrawerSession] = useState<{ engine: string; sessionId: string; project: string } | null>(null);
  const [searchParams] = useSearchParams();
  const [truncated, setTruncated] = useState(false);
  const [reloadNonce, setReloadNonce] = useState(0);

  // Deep link support: ?session=&sessionEngine=&sessionProject= auto-opens
  // the matching session's detail drawer, so other pages (History, Workspaces)
  // can link straight to a session instead of making the user re-search for
  // it. The unprefixed `engine`/`project` names are still accepted so links
  // built before the filter params claimed those names keep working.
  useEffect(() => {
    const session = searchParams.get('session');
    const engine = searchParams.get('sessionEngine') ?? searchParams.get('engine');
    const drawerProject = searchParams.get('sessionProject') ?? searchParams.get('project');
    if (session && engine && drawerProject) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setDrawerSession({ engine, sessionId: session, project: drawerProject });
    }
  }, [searchParams]);

  // The server takes one `engine` per request, so a multi-engine selection
  // becomes one request per engine, merged here. Fetching unfiltered and
  // narrowing client-side instead (the previous approach) silently dropped
  // matching events: the single EVENT_LIMIT window filled up with events
  // from engines the user had deselected.
  const engineKey = useMemo(
    () => [...selectedEngines].sort().join(','),
    [selectedEngines],
  );

  const load = () => setReloadNonce(n => n + 1);

  // Refetches from the server whenever the server-supported filters (date
  // range, engine selection) or an explicit refresh change. Using server-side
  // since/until/engine params avoids the old bug where date filtering only
  // ever searched the fixed first 1000 client-cached events.
  useEffect(() => {
    if (!ready) return;
    let mounted = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    setError(null);

    const base: FetchAuditEventsParams = { limit: EVENT_LIMIT };
    // `<input type="date">` yields a calendar day in the viewer's timezone;
    // send the instants that day actually spans, not UTC midnight.
    const since = localDayStartISO(dateStart);
    const until = localDayEndISO(dateEnd);
    if (since) base.since = since;
    if (until) base.until = until;
    if (project) base.project = project;

    const engines = engineKey ? engineKey.split(',') : [];
    const requests = engines.length > 0
      ? engines.map(engine => fetchAuditEvents({ ...base, engine }))
      : [fetchAuditEvents(base)];

    Promise.all(requests)
      .then(responses => {
        if (!mounted) return;
        const merged = responses
          .flatMap(response => response.events)
          .sort((a, b) => eventTime(b) - eventTime(a));
        setEvents(merged);
        setTruncated(responses.some(response => response.count >= EVENT_LIMIT));
        setLoading(false);
      })
      .catch(() => {
        if (!mounted) return;
        setLoading(false);
        setError('加载事件失败');
      });

    return () => {
      mounted = false;
    };
  }, [engineKey, dateStart, dateEnd, project, ready, reloadNonce]);

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
    // Engine needs no client-side pass: the fetch above already requested
    // exactly the selected engines.
    if (selectedTypes.length > 0) {
      result = result.filter(e => selectedTypes.includes(e.event_type));
    }
    return result;
  }, [events, search, selectedTypes]);

  if (loading) {
    return <FilterListSkeleton label="加载事件中" />;
  }

  if (error) {
    return <ErrorState message={error} onRetry={load} />;
  }

  return (
    <div className="flex flex-col xl:flex-row gap-4 min-h-full xl:h-full">
      <ActivityFilterPanel
        filters={filters}
        engineOptions={ALL_ENGINES}
        searchPlaceholder="项目、会话、内容…"
        showEventTypes
      />

      <div className="flex-1 min-w-0 glass-card p-5 flex flex-col">
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs text-slate-400 font-medium">
            {filtered.length} 条事件
          </p>
          <button
            onClick={load}
            className="flex items-center gap-1 px-2 py-1 text-xs rounded-md border border-slate-200 text-slate-500 hover:bg-slate-50 transition-colors"
          >
            <RefreshCw className="w-3 h-3" /> 刷新
          </button>
        </div>
        <p className="text-[11px] text-slate-400 mb-4">
          跨会话与引擎的全部消息和工具调用，按时间倒序——在这里搜索某件事发生在哪个会话。这不是审批或权限日志。
        </p>

        {truncated && (
          <div className="flex items-center gap-2 mb-4 px-3 py-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            每个引擎仅显示最近 {EVENT_LIMIT.toLocaleString()} 条事件。有更多结果匹配你的筛选——缩小日期范围以查看。
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
                      <p className="whitespace-pre-wrap break-words">{event.content_preview || '（空）'}</p>
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
                      查看完整会话 →
                    </button>
                  </div>
                )}
              </div>
            );
          })}
          {filtered.length === 0 && (
            <p className="text-sm text-slate-400 text-center py-8">没有符合筛选条件的事件</p>
          )}
        </div>
      </div>

      {drawerSession && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/20" role="presentation" onClick={() => setDrawerSession(null)}>
          <div
            className="h-full w-[32rem] max-w-full bg-white p-5 shadow-xl"
            onClick={e => e.stopPropagation()}
          >
            <SessionDetailPanel
              engine={drawerSession.engine}
              sessionId={drawerSession.sessionId}
              projectPath={drawerSession.project}
              onClose={() => setDrawerSession(null)}
              onDeleted={load}
            />
          </div>
        </div>
      )}
    </div>
  );
}
