import { useEffect, useRef, useState } from 'react';
import { fetchSessionPage, type SessionUsage } from '../api/analytics';
import { useLanguageCode, useT } from '../i18n/context';
import { relativeTime, workspaceLabel } from '../utils/workspaceFormat';
import { engineAccent, findEngine } from './terminalEngines';
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

  if (!workspace) return null;

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
              <li key={`${session.target}:${session.sessionId}`}>
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
                  <span className="line-clamp-2 text-sm font-medium text-slate-800">{title}</span>
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
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
