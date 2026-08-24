import { useEffect, useState } from 'react';
import { Wrench } from 'lucide-react';
import { useT } from '../../i18n/context';
import { engineLabel } from '../../utils/engines';
import request from '../../utils/request';
import LoadingState from '../shared/LoadingState';

interface ToolUsage {
  name: string;
  count: number;
  byEngine: Record<string, number>;
}

interface ToolUsageResponse {
  tools: ToolUsage[];
  totalCalls: number;
  sessions: number;
  engines: Record<string, number>;
}

export interface ToolRankingProps {
  /** Null means all history — matches the page's range selector. */
  rangeDays: number | null;
  rangeLabel: string;
}

/** How many rows before the tail is collapsed into one line. */
const VISIBLE_ROWS = 12;

/**
 * Which tools the agents actually reach for, counted across every engine.
 *
 * The numbers come from `/api/analytics/tools`, which reads the parsed
 * session history rather than the analytics cache — tool calls only exist on
 * the parsed sessions. Counting them across engines at once is the part no
 * single vendor CLI can do, since each one only sees its own history.
 */
export default function ToolRanking({ rangeDays, rangeLabel }: ToolRankingProps) {
  const t = useT();
  const [data, setData] = useState<ToolUsageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let active = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    setError(null);

    const query = rangeDays === null ? '' : `?days=${rangeDays}`;
    request<ToolUsageResponse>(`/api/analytics/tools${query}`, { timeout: 30000 })
      .then(result => {
        if (!active) return;
        setData(result);
        setLoading(false);
      })
      .catch(() => {
        if (!active) return;
        setError(t('tools.loadFailed'));
        setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [rangeDays, t]);

  const tools = data?.tools ?? [];
  const shown = expanded ? tools : tools.slice(0, VISIBLE_ROWS);
  const max = tools[0]?.count ?? 0;

  return (
    <div className="glass-card p-5">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <p className="flex items-center gap-1.5 text-sm font-semibold text-slate-700">
          <Wrench className="h-4 w-4" /> {t('tools.title')}
        </p>
        {data && data.totalCalls > 0 && (
          <p className="text-xs text-slate-400">
            {t('tools.subtitle', {
              calls: String(data.totalCalls),
              sessions: String(data.sessions),
              range: rangeLabel,
            })}
          </p>
        )}
      </div>

      {loading && <LoadingState message={t('tools.loading')} />}
      {!loading && error && <p className="text-xs text-slate-400">{error}</p>}
      {!loading && !error && tools.length === 0 && (
        <p className="py-6 text-center text-sm text-slate-400">{t('tools.empty')}</p>
      )}

      {!loading && !error && tools.length > 0 && (
        <>
          <ul className="space-y-2">
            {shown.map(tool => {
              // Guard against a zero max: an all-zero ranking cannot happen
              // today (unnamed calls are dropped server-side) but a 0/0 width
              // would render as NaN% rather than an empty bar.
              const width = max > 0 ? Math.max((tool.count / max) * 100, 2) : 0;
              const engines = Object.entries(tool.byEngine);
              return (
                <li key={tool.name} className="flex items-center gap-3">
                  <span className="w-28 shrink-0 truncate text-right font-mono text-xs text-slate-600" title={tool.name}>
                    {tool.name}
                  </span>
                  <span className="relative h-5 min-w-0 flex-1 overflow-hidden rounded bg-slate-50">
                    <span
                      className="absolute inset-y-0 left-0 rounded bg-primary/15"
                      style={{ width: `${width}%` }}
                    />
                    <span className="absolute inset-y-0 left-1.5 flex items-center text-[10px] font-medium text-slate-600">
                      {tool.count}
                    </span>
                  </span>
                  {/* The cross-engine split is the whole point — a single CLI
                      can only ever show you its own column. */}
                  <span className="hidden w-52 shrink-0 gap-2 text-[10px] text-slate-400 sm:flex sm:flex-wrap">
                    {engines.map(([engine, count]) => (
                      <span key={engine}>
                        {engineLabel(engine)} {count}
                      </span>
                    ))}
                  </span>
                </li>
              );
            })}
          </ul>

          {tools.length > VISIBLE_ROWS && (
            <button
              onClick={() => setExpanded(value => !value)}
              className="mt-3 text-xs font-medium text-primary transition-opacity hover:opacity-80"
            >
              {expanded
                ? t('tools.showLess')
                : t('tools.showAll', { count: String(tools.length) })}
            </button>
          )}
        </>
      )}
    </div>
  );
}
