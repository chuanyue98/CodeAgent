import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { fetchDelegations } from '../api/delegations';
import { useT } from '../i18n/context';
import type { TerminalTab } from '../context/TerminalContext';
import { queryClient as defaultQueryClient } from '../utils/queryClient';
import { findEngine } from './terminalEngines';

const POLL_MS = 5000;

const STATUS_TONE: Record<string, string> = {
  starting: 'bg-primary/15 text-primary',
  running: 'bg-primary/15 text-primary',
  completed: 'bg-ok/15 text-ok',
  failed: 'bg-destructive/15 text-destructive',
  stopped: 'bg-muted text-muted-foreground',
  unknown: 'bg-muted text-muted-foreground',
};

/**
 * What surrounds the open session: which engine and directory it is, and any
 * work it has handed to another engine. Only what the gateway actually knows
 * is shown -- a fresh session has no id yet and the terminal's own output is
 * the engine's, so there are no token or file figures to make up here.
 */
export default function SessionInspector({ tab }: { tab: TerminalTab }) {
  const t = useT();
  const engine = findEngine(tab.engine);
  const { data: allDelegations } = useQuery(
    {
      queryKey: ['delegations'],
      queryFn: async () => (await fetchDelegations()) ?? [],
      refetchInterval: POLL_MS,
    },
    defaultQueryClient,
  );

  const runs = allDelegations ? allDelegations.filter(run => run.workspace === tab.cwd) : null;

  const row = (label: string, value: string) => (
    <div className="flex items-baseline justify-between gap-4 text-sm">
      <dt className="shrink-0 text-muted-foreground">{label}</dt>
      <dd className="min-w-0 truncate text-right font-mono text-xs" title={value}>{value}</dd>
    </div>
  );

  return (
    <aside className="custom-scrollbar hidden w-72 shrink-0 flex-col gap-6 overflow-y-auto border-l border-border bg-card px-4 py-5 xl:flex">
      <section>
        <h2 className="mb-2.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{t('inspector.status')}</h2>
        <dl className="space-y-1.5">
          {row(t('inspector.engine'), engine?.nameKey ? t(engine.nameKey) : (engine?.name ?? tab.engine))}
          {row(t('inspector.workspace'), tab.cwd)}
          {tab.sessionId && row(t('inspector.sessionId'), tab.sessionId)}
        </dl>
      </section>

      <section>
        <h2 className="mb-2.5 flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          <span>{t('inspector.delegations')}</span>
          <Link to="/agent/delegations" className="font-medium normal-case tracking-normal text-primary hover:underline">
            {t('inspector.allDelegations')}
          </Link>
        </h2>
        {runs !== null && runs.length === 0 && (
          <p className="text-sm text-muted-foreground">{t('inspector.noDelegations')}</p>
        )}
        <ul className="space-y-2">
          {(runs ?? []).map(run => {
            const target = findEngine(run.engine);
            return (
              <li key={run.runId} className="flex items-start gap-2.5">
                <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${target?.dot ?? 'bg-slate-400'}`} />
                <span className="min-w-0 flex-1">
                  <span className="line-clamp-2 block text-sm">{run.instruction}</span>
                  <span className="text-xs text-muted-foreground">{target?.name ?? run.engine}</span>
                </span>
                <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${STATUS_TONE[run.status] ?? STATUS_TONE.unknown}`}>
                  {run.status}
                </span>
              </li>
            );
          })}
        </ul>
      </section>
    </aside>
  );
}
