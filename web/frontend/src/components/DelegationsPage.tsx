import { useCallback, useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronRight, GitBranch, Send, Square } from 'lucide-react';
import {
  fetchDelegation,
  fetchDelegations,
  stopDelegation,
  type DelegationRun,
  type DelegationStatus,
} from '../api/delegations';
import { engineLabel } from '../utils/engines';
import usePolling from '../hooks/usePolling';
import Badge from './shared/Badge';
import ConfirmDialog from './shared/ConfirmDialog';
import EmptyState from './shared/EmptyState';
import ErrorState from './shared/ErrorState';
import LoadingState from './shared/LoadingState';
import StatusDot from './shared/StatusDot';
import { useT } from '../i18n/context';
import type { TranslationKey } from '../i18n/locales/en';

const LIVE: ReadonlySet<DelegationStatus> = new Set(['starting', 'running']);

const STATUS_TONE = {
  starting: 'pending',
  running: 'running',
  completed: 'success',
  failed: 'failed',
  stopped: 'neutral',
  unknown: 'neutral',
} as const;

const STATUS_LABEL_KEYS: Record<DelegationStatus, TranslationKey> = {
  starting: 'delegations.status.starting',
  running: 'delegations.status.running',
  completed: 'delegations.status.completed',
  failed: 'delegations.status.failed',
  stopped: 'delegations.status.stopped',
  unknown: 'delegations.status.unknown',
};

function durationLabel(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}min ${s % 60}s`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}min`;
}

/** 委派 id 里带着发起时间（engine-YYYYMMDD-HHMMSS-xxxxxx）。 */
function startedLabel(runId: string): string {
  const m = /-(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})-/.exec(runId);
  return m ? `${m[2]}-${m[3]} ${m[4]}:${m[5]}` : '';
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-1.5">
      <h3 className="text-xs font-semibold tracking-wider text-slate-400 uppercase">{title}</h3>
      {children}
    </section>
  );
}

const PRE = 'max-h-80 overflow-auto rounded-lg border border-slate-100 bg-slate-50 p-3 font-mono text-xs whitespace-pre-wrap';

function DelegationDetailPanel({ runId, status }: { runId: string; status: DelegationStatus }) {
  const t = useT();
  const { data, isPending, isError, error, refetch } = useQuery({
    // 状态进 key：跑完那一刻列表先看到，这里跟着重取一次拿到结果。
    queryKey: ['delegation', runId, status],
    queryFn: () => fetchDelegation(runId),
    refetchInterval: LIVE.has(status) ? 3000 : false,
  });

  if (isPending) return <LoadingState height="h-32" />;
  if (isError) {
    return (
      <ErrorState
        message={error instanceof Error ? error.message : String(error)}
        onRetry={() => void refetch()}
      />
    );
  }

  const result = data.result;
  const errorText = result?.error || data.error;
  return (
    <div className="space-y-4 border-t border-slate-100 px-4 py-4">
      <Section title={t('delegations.instruction')}>
        <pre className={PRE}>{data.instruction}</pre>
      </Section>

      {errorText && (
        <p className="rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-600">{errorText}</p>
      )}

      {result ? (
        <>
          <Section title={t('delegations.summary')}>
            <pre className={PRE}>{result.summary || t('delegations.noOutput')}</pre>
          </Section>
          {(result.branch || result.isolatedWorktree) && (
            <p className="flex items-center gap-1.5 text-xs text-slate-500">
              <GitBranch className="h-3.5 w-3.5" />
              {result.branch
                ? t('delegations.branch', { branch: result.branch })
                : t('delegations.isolatedWorktree')}
            </p>
          )}
          {result.filesChanged.length > 0 && (
            <Section title={t('delegations.filesChanged')}>
              <ul className="space-y-0.5 font-mono text-xs text-slate-700">
                {result.filesChanged.map(file => (
                  <li key={file} className="truncate">{file}</li>
                ))}
              </ul>
            </Section>
          )}
          {result.diff && (
            <Section title="Diff">
              <pre className={`${PRE} whitespace-pre`}>{result.diff}</pre>
              {result.diffTruncated && (
                <p className="text-xs text-slate-400 italic">{t('delegations.diffTruncated')}</p>
              )}
            </Section>
          )}
        </>
      ) : (
        <Section title={t('delegations.output')}>
          <pre className={PRE}>{data.outputTail || t('delegations.noOutput')}</pre>
        </Section>
      )}

      <p className="truncate font-mono text-[11px] text-slate-300" title={data.outputLog}>
        {data.outputLog}
      </p>
    </div>
  );
}

/**
 * 委派记录页：主会话通过 ca_delegate 交给其他引擎的任务。
 * 数据来自 ~/.codeagent/delegations/，与发起它的会话是否还开着无关。
 */
export default function DelegationsPage() {
  const t = useT();
  const [runs, setRuns] = useState<DelegationRun[] | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [pendingStop, setPendingStop] = useState<DelegationRun | null>(null);

  const refresh = useCallback(async () => {
    try {
      setRuns(await fetchDelegations());
    } catch {
      // 轮询失败静默，usePolling 自带退避重试。
    }
  }, []);
  usePolling(refresh, 5000);

  const onConfirmStop = useCallback(async () => {
    if (!pendingStop) return;
    try {
      await stopDelegation(pendingStop.runId);
    } finally {
      setPendingStop(null);
      void refresh();
    }
  }, [pendingStop, refresh]);

  if (runs === null) return <LoadingState height="h-40" />;

  const liveCount = runs.filter(run => LIVE.has(run.status)).length;

  return (
    <div className="max-w-5xl space-y-5">
      <div className="glass-card animate-fade-rise flex items-center gap-3 px-5 py-4">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <Send className="h-4 w-4" />
        </span>
        <div>
          <p className="text-sm font-semibold text-slate-800">
            {t('delegations.summaryLine', { live: String(liveCount), total: String(runs.length) })}
          </p>
          <p className="text-[11px] text-slate-400">{t('delegations.intro')}</p>
        </div>
      </div>

      {runs.length === 0 && (
        <EmptyState
          icon={Send}
          title={t('delegations.empty')}
          body={t('delegations.emptyHint')}
          className="animate-fade-rise stagger-2"
        />
      )}

      <div className="space-y-1.5">
        {runs.map(run => {
          const open = expanded === run.runId;
          const live = LIVE.has(run.status);
          return (
            <div key={run.runId} className="glass-card-flat animate-fade-rise overflow-hidden">
              <div className="flex items-center gap-4 px-4 py-3">
                <button
                  type="button"
                  onClick={() => setExpanded(open ? null : run.runId)}
                  aria-expanded={open}
                  className="flex min-w-0 flex-1 items-center gap-4 text-left"
                >
                  <ChevronRight
                    className={`h-3.5 w-3.5 shrink-0 text-slate-300 transition-transform ${open ? 'rotate-90' : ''}`}
                  />
                  <span title={t(STATUS_LABEL_KEYS[run.status] ?? STATUS_LABEL_KEYS.unknown)}>
                    <StatusDot tone={STATUS_TONE[run.status] ?? 'neutral'} pulse={live} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium text-slate-800">
                        {run.instruction.split('\n', 1)[0] || run.runId}
                      </span>
                      <Badge variant="engine" engine={run.engine} size="sm">
                        {engineLabel(run.engine)}
                      </Badge>
                      <Badge size="sm">
                        {t(run.mode === 'review' ? 'delegations.mode.review' : 'delegations.mode.write')}
                      </Badge>
                    </span>
                    <span className="mt-0.5 block truncate font-mono text-[11px] text-slate-400">
                      {run.workspace}
                    </span>
                  </span>
                </button>

                <div className="flex shrink-0 items-center gap-3 font-mono text-[11px] text-slate-400 tabular-nums">
                  <span>{startedLabel(run.runId)}</span>
                  <span>{durationLabel(run.elapsedSeconds)}</span>
                  {live && (
                    <button
                      type="button"
                      onClick={() => setPendingStop(run)}
                      aria-label={t('delegations.stop')}
                      className="flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 font-sans font-semibold text-slate-400 transition-colors hover:border-red-200 hover:bg-red-50 hover:text-red-600"
                    >
                      <Square className="h-3 w-3" />
                      {t('delegations.stop')}
                    </button>
                  )}
                </div>
              </div>
              {open && <DelegationDetailPanel runId={run.runId} status={run.status} />}
            </div>
          );
        })}
      </div>

      {pendingStop && (
        <ConfirmDialog
          title={t('delegations.stopConfirmTitle')}
          description={t('delegations.stopConfirmDescription', {
            engine: engineLabel(pendingStop.engine),
          })}
          confirmLabel={t('delegations.stop')}
          destructive
          onConfirm={onConfirmStop}
          onCancel={() => setPendingStop(null)}
        />
      )}
    </div>
  );
}
