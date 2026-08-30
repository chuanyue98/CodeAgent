import { useQuery } from '@tanstack/react-query';
import { getRunChanges } from '../../api/tasks';
import { useT } from '../../i18n/context';
import ErrorState from '../shared/ErrorState';
import LoadingState from '../shared/LoadingState';

const KNOWN_REASONS = ['no_workspace', 'git_missing', 'not_git_repo'] as const;
type KnownReason = (typeof KNOWN_REASONS)[number] | 'git_error';

function reasonKey(reason: string | undefined): KnownReason {
  return (KNOWN_REASONS as readonly string[]).includes(reason ?? '')
    ? (reason as KnownReason)
    : 'git_error';
}

/**
 * Git changes one run made in its workspace. Mounted only while the Changes
 * tab is open, so the query fires (and refetches) exactly when visible.
 */
export default function RunChanges({ taskId }: { taskId: string }) {
  const t = useT();
  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ['runChanges', taskId],
    queryFn: () => getRunChanges(taskId),
  });

  if (isPending) return <LoadingState height="h-40" />;
  if (isError) {
    return (
      <ErrorState
        message={error instanceof Error ? error.message : String(error)}
        onRetry={() => void refetch()}
      />
    );
  }
  if (!data.available) {
    return (
      <p className="p-6 text-sm text-slate-400 italic">
        {t(`taskDetail.changesUnavailable.${reasonKey(data.reason)}`)}
      </p>
    );
  }

  return (
    <div className="space-y-4 bg-white p-4">
      {data.mode === 'uncommitted' && (
        <p className="text-xs text-amber-600 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
          {t('taskDetail.changesUncommittedNote')}
        </p>
      )}

      {data.mode === 'commits' && data.commits && data.commits.length > 0 && (
        <section className="space-y-1.5">
          <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
            {t('taskDetail.changesCommits')}
          </h3>
          {data.commits.map(commit => (
            <div key={commit.sha} className="flex items-baseline gap-2 text-sm">
              <span className="font-mono text-xs text-primary shrink-0">{commit.sha.slice(0, 7)}</span>
              <span className="text-slate-800 truncate">{commit.message}</span>
              <span className="text-xs text-slate-400 ml-auto whitespace-nowrap">
                {commit.author} · {new Date(commit.committedAt).toLocaleString()}
              </span>
            </div>
          ))}
        </section>
      )}

      {data.mode === 'commits' && data.files && data.files.length > 0 && (
        <section className="space-y-1.5">
          <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
            {t('taskDetail.changesFiles')}
          </h3>
          {data.files.map(file => (
            <div key={file.path} className="flex items-center gap-2 text-xs font-mono">
              <span className="text-emerald-600 w-10 text-right shrink-0">
                {file.additions === null ? '-' : `+${file.additions}`}
              </span>
              <span className="text-red-500 w-10 text-right shrink-0">
                {file.deletions === null ? '-' : `-${file.deletions}`}
              </span>
              <span className="text-slate-700 truncate">{file.path}</span>
            </div>
          ))}
        </section>
      )}

      {data.mode === 'uncommitted' && data.entries && (
        <section className="space-y-1.5">
          <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
            {t('taskDetail.changesFiles')}
          </h3>
          {data.entries.length > 0 ? (
            data.entries.map(entry => (
              <div key={`${entry.status}:${entry.path}`} className="flex items-center gap-2 text-xs font-mono">
                <span className="text-primary w-6 text-right shrink-0">{entry.status}</span>
                <span className="text-slate-700 truncate">{entry.path}</span>
              </div>
            ))
          ) : (
            <p className="text-xs text-slate-400 italic">{t('taskDetail.changesCleanTree')}</p>
          )}
        </section>
      )}

      {data.diff && (
        <section className="space-y-1.5">
          <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Diff</h3>
          <pre className="text-xs font-mono bg-slate-50 border border-slate-100 rounded-lg p-3 overflow-auto max-h-96 whitespace-pre">
            {data.diff}
          </pre>
          {data.diffTruncated && (
            <p className="text-xs text-slate-400 italic">{t('taskDetail.changesDiffTruncated')}</p>
          )}
        </section>
      )}
    </div>
  );
}
