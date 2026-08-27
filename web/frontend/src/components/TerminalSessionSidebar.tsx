import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ChevronRight, Plus, Search } from 'lucide-react';
import { fetchSessionPage, type SessionUsage } from '../api/analytics';
import { relativeTime, workspaceLabel } from '../utils/workspaceFormat';
import { useLanguageCode } from '../i18n/context';
import { useT } from '../i18n/context';

const PAGE_SIZE = 30;
const SEARCH_DEBOUNCE_MS = 250;

interface TerminalSessionSidebarProps {
  /** Workspace to expand by default -- the one the launcher is pointed at. */
  currentWorkspace: string;
  /** Session currently shown in the active terminal tab, if any. */
  activeSessionId?: string;
  onOpenSession: (engine: string, cwd: string, sessionId: string) => void;
  onNewSession: () => void;
}

interface PageResult {
  /** The query this page answers; a mismatch with the live query means stale. */
  query: string;
  sessions: SessionUsage[];
  cursor: string | null;
  error: string | null;
}

interface WorkspaceGroup {
  path: string;
  sessions: SessionUsage[];
}

/**
 * The terminal's own session list.
 *
 * These are engine-native sessions -- the same ones `ca history` lists and
 * `ca switch` converts -- so picking one hands it straight back to its engine
 * CLI in a terminal tab. Before this, the browser terminal could resume a
 * session (the PTY endpoint has always taken a session id) but offered no way
 * to *choose* one: you had to arrive from Activity's detail panel by deep link.
 */
export default function TerminalSessionSidebar({
  currentWorkspace,
  activeSessionId,
  onOpenSession,
  onNewSession,
}: TerminalSessionSidebarProps) {
  const t = useT();
  const language = useLanguageCode();

  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  // Carries the query it answers, so "still loading" is derived from a stale
  // query rather than from synchronously blanking state inside the effect.
  const [result, setResult] = useState<PageResult | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  // Tracks the groups whose state differs from the default, which is "only
  // the workspace you are pointed at is open". Listing every workspace
  // expanded turned a handful of projects into a wall you had to scroll past
  // to reach the one you were working in.
  const [toggled, setToggled] = useState<Set<string>>(new Set());

  const fresh = result?.query === query ? result : null;
  const sessions = fresh?.sessions ?? null;
  const cursor = fresh?.cursor ?? null;
  const error = fresh?.error ?? null;

  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [search]);

  // A slow first page must not overwrite a later, narrower one.
  const requestRef = useRef(0);
  useEffect(() => {
    const request = ++requestRef.current;
    fetchSessionPage({ limit: PAGE_SIZE, search: query || undefined })
      .then(page => {
        if (requestRef.current !== request) return;
        setResult({
          query,
          sessions: page.sessions,
          cursor: page.nextCursor ?? null,
          error: null,
        });
      })
      .catch(err => {
        if (requestRef.current !== request) return;
        setResult({
          query,
          sessions: [],
          cursor: null,
          error: err instanceof Error ? err.message : String(err),
        });
      });
  }, [query]);

  const loadMore = useCallback(() => {
    if (!cursor || loadingMore) return;
    setLoadingMore(true);
    const request = requestRef.current;
    fetchSessionPage({ limit: PAGE_SIZE, search: query || undefined, cursor })
      .then(page => {
        if (requestRef.current !== request) return;
        setResult(previous =>
          previous && previous.query === query
            ? {
                ...previous,
                sessions: [...previous.sessions, ...page.sessions],
                cursor: page.nextCursor ?? null,
              }
            : previous,
        );
      })
      .catch(() => {})
      .finally(() => setLoadingMore(false));
  }, [cursor, loadingMore, query]);

  const groups = useMemo<WorkspaceGroup[]>(() => {
    const byPath = new Map<string, SessionUsage[]>();
    for (const session of sessions ?? []) {
      const path = session.projectPath || '';
      const bucket = byPath.get(path);
      if (bucket) bucket.push(session);
      else byPath.set(path, [session]);
    }
    return [...byPath.entries()]
      .map(([path, list]) => ({ path, sessions: list }))
      // The workspace the launcher points at leads; the rest keep the
      // recency order the API returned them in.
      .sort((a, b) => Number(b.path === currentWorkspace) - Number(a.path === currentWorkspace));
  }, [sessions, currentWorkspace]);

  const toggle = (path: string) =>
    setToggled(previous => {
      const next = new Set(previous);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });

  // Open by default: the workspace you are pointed at, or -- when it has
  // nothing in it -- the one with the most recent work, so the sidebar never
  // greets you as an empty list of folder names.
  const defaultOpen = useMemo(() => {
    const current = groups.find(group => group.path === currentWorkspace);
    return current?.sessions.length ? current.path : (groups[0]?.path ?? '');
  }, [groups, currentWorkspace]);

  const isOpen = (path: string) =>
    // A search is a request to see what matched, wherever it lives.
    Boolean(query) || (path === defaultOpen) !== toggled.has(path);

  return (
    <aside className="flex w-64 shrink-0 flex-col gap-2 overflow-hidden">
      <div className="flex items-center justify-between px-1">
        <span className="text-xs font-semibold text-slate-600">{t('terminalSidebar.title')}</span>
        <button
          onClick={onNewSession}
          className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-primary transition-colors hover:bg-primary/10"
        >
          <Plus size={13} /> {t('terminalSidebar.new')}
        </button>
      </div>

      <label className="relative block px-1">
        <span className="sr-only">{t('terminalSidebar.search')}</span>
        <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
        <input
          type="search"
          value={search}
          onChange={event => setSearch(event.target.value)}
          placeholder={t('terminalSidebar.search')}
          className="w-full rounded-lg border border-slate-200 py-1.5 pl-8 pr-2 text-xs"
        />
      </label>

      <div className="custom-scrollbar min-h-0 flex-1 space-y-1 overflow-y-auto px-1 pb-2">
        {sessions === null && (
          <p className="px-2 py-4 text-xs text-slate-400">{t('common.loading')}</p>
        )}
        {error && <p className="px-2 py-4 text-xs text-red-600">{error}</p>}
        {sessions !== null && !error && sessions.length === 0 && (
          <p className="px-2 py-4 text-xs text-slate-400">{t('terminalSidebar.empty')}</p>
        )}

        {groups.map(group => {
          const open = isOpen(group.path);
          return (
            <div key={group.path}>
              <button
                onClick={() => toggle(group.path)}
                title={group.path}
                className="flex w-full items-center gap-1 rounded-lg px-2 py-1 text-left text-[11px] font-semibold text-slate-500 hover:bg-slate-50"
              >
                <ChevronRight
                  size={12}
                  className={`shrink-0 transition-transform ${open ? 'rotate-90' : ''}`}
                />
                <span className="min-w-0 flex-1 truncate">{workspaceLabel(group.path)}</span>
                <span className="shrink-0 text-slate-400">{group.sessions.length}</span>
              </button>
              {open && (
                <ul>
                  {group.sessions.map(session => {
                    const active = session.sessionId === activeSessionId;
                    return (
                      <li key={`${session.target}:${session.sessionId}`}>
                        <button
                          onClick={() =>
                            onOpenSession(session.target, session.projectPath, session.sessionId)
                          }
                          title={session.title || session.sessionId}
                          className={`w-full rounded-lg px-2 py-1.5 text-left transition-colors ${
                            active ? 'bg-primary/10' : 'hover:bg-slate-50'
                          }`}
                        >
                          <span className="block truncate text-xs text-slate-700">
                            {session.title || t('terminalSidebar.untitled')}
                          </span>
                          <span className="mt-0.5 flex items-center gap-1.5 text-[10px] text-slate-400">
                            <span className="rounded bg-slate-100 px-1 font-mono uppercase">
                              {session.target}
                            </span>
                            <span className="truncate">{relativeTime(session.lastActivity, language)}</span>
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          );
        })}

        {cursor && (
          <button
            onClick={loadMore}
            disabled={loadingMore}
            className="w-full rounded-lg px-2 py-2 text-xs font-medium text-primary hover:bg-primary/5 disabled:opacity-50"
          >
            {loadingMore ? t('common.loading') : t('terminalSidebar.loadMore')}
          </button>
        )}
      </div>
    </aside>
  );
}
