import { useMemo } from 'react';
import { FileText } from 'lucide-react';
import { type SessionUsage, fmtCost, fmtTokens } from '../api/analytics';
import type { SessionDetail } from '../api/audit';
import { formatDuration, summarizeSession } from '../utils/sessionProgress';
import { useT } from '../i18n/context';

export interface SessionProgressProps {
  detail: Pick<SessionDetail, 'messages'> | null;
  /** Usage totals, when the caller already has them. */
  usage?: SessionUsage;
}

/**
 * The one-line answer to "how far did this session get", above the transcript.
 *
 * Deliberately a summary and not a second usage panel: the per-model and cache
 * breakdown lives in the section below, and repeating it here would cost the
 * glanceability that is the whole point of this strip.
 */
export default function SessionProgress({ detail, usage }: SessionProgressProps) {
  const t = useT();
  const progress = useMemo(() => summarizeSession(detail), [detail]);

  const duration = formatDuration(progress.durationMs);
  const totalTokens = usage ? usage.inputTokens + usage.outputTokens : 0;

  const metrics = [
    progress.turns > 0 ? t('sessionProgress.turns', { count: String(progress.turns) }) : null,
    duration,
    usage && totalTokens > 0 ? fmtTokens(totalTokens) : null,
    usage && usage.cost > 0 ? fmtCost(usage.cost) : null,
    progress.files.length > 0
      ? t('sessionProgress.files', { count: String(progress.files.length) })
      : null,
  ].filter((part): part is string => Boolean(part));

  // A session with no timestamps, no tool calls and no usage would render an
  // empty box that says nothing — skip the strip entirely in that case.
  if (metrics.length === 0 && progress.recent.length === 0) return null;

  return (
    <section data-testid="session-progress">
      <p className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-slate-400">
        {t('sessionProgress.title')}
      </p>
      <div className="rounded-lg border border-slate-100 bg-slate-50/70 p-2.5">
        {metrics.length > 0 && (
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs font-medium text-slate-700">
            {metrics.map((part, i) => (
              <span key={`${part}-${i}`} className="flex items-center gap-2">
                {i > 0 && <span className="text-slate-300">·</span>}
                {part}
              </span>
            ))}
          </p>
        )}

        {progress.recent.length > 0 && (
          <div className="mt-2 space-y-1 border-t border-slate-200/70 pt-2">
            <p className="text-[10px] uppercase tracking-wide text-slate-400">
              {t('sessionProgress.lastActions')}
            </p>
            {progress.recent.map((action, i) => (
              <div
                key={`${action.name}-${i}`}
                className="flex items-baseline gap-2 text-[11px] text-slate-500"
              >
                <span className="shrink-0 font-mono font-semibold text-slate-700">
                  {action.name}
                </span>
                {action.detail && (
                  <span className="min-w-0 truncate" title={action.detail}>
                    {action.detail}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}

        {progress.files.length > 0 && (
          <div className="mt-2 flex items-start gap-1.5 border-t border-slate-200/70 pt-2 text-[11px] text-slate-500">
            <FileText className="mt-0.5 h-3 w-3 shrink-0 text-slate-400" />
            {/* Full list in the tooltip: a session touching 40 files would
                otherwise push the transcript off the panel. */}
            <span className="min-w-0 truncate" title={progress.files.join('\n')}>
              {progress.files.join(' · ')}
            </span>
          </div>
        )}
      </div>
    </section>
  );
}
