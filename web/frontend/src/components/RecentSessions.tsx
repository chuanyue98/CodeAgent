import { useEffect, useRef, useState } from 'react';
import { Loader2, Zap } from 'lucide-react';
import { fetchSessionPage, type SessionUsage } from '../api/analytics';
import { convertAndLaunchSession } from '../api/audit';
import { useLanguageCode, useT } from '../i18n/context';
import { relativeTime, workspaceLabel } from '../utils/workspaceFormat';
import { AGENT_ENGINES, engineAccent, findEngine } from './terminalEngines';
import SectionLabel from './shared/SectionLabel';

const LIMIT = 8;

interface RecentSessionsProps {
  /** Empty means nothing is selected yet; the list has nothing to scope to. */
  workspace: string;
  activeSessionId?: string;
  onOpen: (engine: string, cwd: string, sessionId: string) => void;
}

interface Result {
  /** The workspace this answers; a mismatch with the live one means stale. */
  workspace: string;
  sessions: SessionUsage[];
  /** False once the answer fell back to work from anywhere. */
  scoped: boolean;
  error: string | null;
}

/**
 * The most recent work in the workspace the launcher is pointed at, falling
 * back to recent work anywhere once that workspace has none.
 *
 * Not a second copy of the sidebar: that list is global, grouped by
 * workspace and searchable, and it is 256px wide. This one answers the
 * question the launcher screen was leaving to a wall of empty space —
 * "what was I doing in *this* project" — and resuming is a likelier reason
 * to be here than picking an engine from scratch.
 */
export default function RecentSessions({
  workspace,
  activeSessionId,
  onOpen,
}: RecentSessionsProps) {
  const t = useT();
  const language = useLanguageCode();
  const [result, setResult] = useState<Result | null>(null);

  const [handoffSessionId, setHandoffSessionId] = useState<string | null>(null);
  const [handoffLoading, setHandoffLoading] = useState<string | null>(null);
  const handoffRef = useRef<HTMLDivElement>(null);

  const fresh = result?.workspace === workspace ? result : null;

  // A slow answer for the previous workspace must not land on the new one.
  const requestRef = useRef(0);
  useEffect(() => {
    if (!workspace) return;
    const request = ++requestRef.current;
    fetchSessionPage({ limit: LIMIT, project: workspace })
      .then(async page => {
        if (page.sessions.length > 0) return { sessions: page.sessions, scoped: true };
        // A workspace you have not worked in yet is the case this block exists
        // for -- answering it with an empty state puts the launcher back to
        // staring at the blank half of the screen it was built to fill.
        const anywhere = await fetchSessionPage({ limit: LIMIT });
        return { sessions: anywhere.sessions, scoped: false };
      })
      .then(({ sessions, scoped }) => {
        if (requestRef.current !== request) return;
        setResult({ workspace, sessions, scoped, error: null });
      })
      .catch(err => {
        if (requestRef.current !== request) return;
        setResult({
          workspace,
          sessions: [],
          scoped: true,
          error: err instanceof Error ? err.message : String(err),
        });
      });
  }, [workspace]);

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

  if (!workspace) return null;

  const handleHandoff = async (session: SessionUsage, targetEngine: string) => {
    setHandoffLoading(session.sessionId);
    try {
      const result = await convertAndLaunchSession({
        sourceEngine: session.target,
        sessionId: session.sessionId,
        targetEngine,
        projectPath: session.projectPath,
      });
      setHandoffSessionId(null);
      onOpen(result.engine, result.project, result.sessionId);
    } catch (err) {
      console.error('Failed to handoff session:', err);
    } finally {
      setHandoffLoading(null);
    }
  };

  const engineName = (id: string) => {
    const engine = findEngine(id);
    if (!engine) return id;
    return engine.nameKey ? t(engine.nameKey) : engine.name;
  };

  return (
    <section className="space-y-2">
      <SectionLabel as="h2">
        {t(fresh && !fresh.scoped ? 'launch.recentElsewhere' : 'launch.recent')}
      </SectionLabel>

      {fresh === null && <p className="text-xs text-slate-400">{t('common.loading')}</p>}
      {fresh?.error && <p className="text-xs text-red-600">{fresh.error}</p>}
      {fresh && !fresh.error && fresh.sessions.length === 0 && (
        <p className="text-xs text-slate-400">{t('launch.recentEmpty')}</p>
      )}

      {fresh && fresh.sessions.length > 0 && (
        <ul className="grid auto-rows-fr grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {fresh.sessions.map(session => {
            const title = session.title || t('terminalSidebar.untitled');
            const active = session.sessionId === activeSessionId;
            return (
              <li key={`${session.target}:${session.sessionId}`} className="group relative">
                <button
                  type="button"
                  onClick={() => onOpen(session.target, session.projectPath, session.sessionId)}
                  aria-label={t('launch.resume', { title })}
                  title={title}
                  className={`flex h-full w-full flex-col gap-2 rounded-xl border bg-white/70 p-3 text-left transition-colors ${
                    active
                      ? 'border-primary/50 bg-primary/5'
                      : 'border-slate-200 hover:border-primary/40 hover:bg-white'
                  }`}
                >
                  <span className="line-clamp-2 text-sm font-medium text-slate-800 pr-6">{title}</span>
                  <span className="mt-auto flex items-center gap-2 text-[11px] text-slate-400">
                    <span className={`shrink-0 rounded px-1.5 py-0.5 font-medium ${engineAccent(session.target)}`}>
                      {engineName(session.target)}
                    </span>
                    {/* Which project it belongs to only matters once the list
                        stops being about one of them. */}
                    {!fresh.scoped && (
                      <span className="truncate font-medium text-slate-500">
                        {workspaceLabel(session.projectPath)}
                      </span>
                    )}
                    <span className="shrink-0">{relativeTime(session.lastActivity, language)}</span>
                  </span>
                </button>

                <div className="absolute right-2 top-2 z-10" onClick={e => e.stopPropagation()}>
                  <button
                    type="button"
                    disabled={handoffLoading === session.sessionId}
                    onClick={() => setHandoffSessionId(prev => prev === session.sessionId ? null : session.sessionId)}
                    title={t('launch.handoffTitle')}
                    aria-label={t('launch.handoffTitle')}
                    className={`rounded p-1 text-slate-400 transition-colors hover:bg-amber-100 hover:text-amber-700 ${
                      handoffSessionId === session.sessionId
                        ? 'bg-amber-100 text-amber-700'
                        : 'opacity-0 group-hover:opacity-100'
                    }`}
                  >
                    {handoffLoading === session.sessionId ? (
                      <Loader2 size={13} className="animate-spin text-amber-600" />
                    ) : (
                      <Zap size={13} />
                    )}
                  </button>
                  {handoffSessionId === session.sessionId && (
                    <div
                      ref={handoffRef}
                      className="absolute right-0 top-full z-50 mt-1 min-w-36 rounded-xl border border-slate-200 bg-white/95 p-1 shadow-lg backdrop-blur"
                    >
                      <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                        {t('launch.handoffTitle')}
                      </div>
                      {AGENT_ENGINES.filter(e => e.id !== session.target).map(target => (
                        <button
                          key={target.id}
                          disabled={Boolean(handoffLoading)}
                          onClick={() => void handleHandoff(session, target.id)}
                          className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs text-slate-700 transition-colors hover:bg-slate-100 disabled:opacity-50"
                        >
                          <span className={`h-2 w-2 rounded-full ${target.dot}`} />
                          <span className="font-medium">{target.nameKey ? t(target.nameKey) : target.name}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
