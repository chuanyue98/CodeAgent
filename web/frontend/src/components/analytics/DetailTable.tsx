import { useState } from 'react';
import { fmtCost, fmtTokens, type DailyUsage, type MonthlyUsage } from '../../api/analytics';
import { useT } from '../../i18n/context';
import { eb } from './present';
import { SectionTitle } from './ChartCards';
import ShowMoreToggle from './ShowMoreToggle';

export interface DetailTableProps {
  granularity: 'day' | 'month';
  monthly: MonthlyUsage[];
  rangeDaily: DailyUsage[];
  rangeLabel: string;
  hasRows: boolean;
}

/**
 * Rows shown before the tail is folded away. One row per day *per engine*, so
 * a 30-day range across four engines is well over a hundred — the table was
 * the single tallest thing on the page and the rows below the first screen
 * are ones you scrolled past, not to.
 */
const VISIBLE_ROWS = 15;

export default function DetailTable({
  granularity, monthly, rangeDaily, rangeLabel, hasRows,
}: DetailTableProps) {
  const t = useT();
  const [expanded, setExpanded] = useState(false);
  if (!hasRows) return null;

  const rows = granularity === 'month'
    ? [...monthly].reverse().map(m => ({
        key: `${m.month}-${m.target}`, label: m.month, target: m.target,
        inputTokens: m.inputTokens, outputTokens: m.outputTokens, cost: m.cost,
      }))
    : [...rangeDaily].reverse().map(d => ({
        key: `${d.date}-${d.target}`, label: d.date, target: d.target,
        inputTokens: d.inputTokens, outputTokens: d.outputTokens, cost: d.cost,
      }));
  const shown = expanded ? rows : rows.slice(0, VISIBLE_ROWS);

  return (
    <div className="animate-fade-rise stagger-6 glass-card-flat p-5">
      <SectionTitle>
        {granularity === 'month' ? t('detail.byMonth') : t('detail.byRange', { range: rangeLabel })}
      </SectionTitle>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-100 text-slate-400">
              <th className="text-left py-2 pr-4 font-medium">
                {granularity === 'month' ? t('detail.month') : t('detail.date')}
              </th>
              <th className="text-left py-2 pr-4 font-medium">{t('detail.engine')}</th>
              <th className="text-right py-2 pr-4 font-medium">{t('analytics.input')}</th>
              <th className="text-right py-2 pr-4 font-medium">{t('analytics.output')}</th>
              <th className="text-right py-2 font-medium">{t('detail.cost')}</th>
            </tr>
          </thead>
          <tbody>
            {shown.map(row => (
              <tr key={row.key} className="border-b border-slate-50 hover:bg-slate-50/60 transition-colors">
                <td className="py-1.5 pr-4 font-mono text-slate-500">{row.label}</td>
                <td className="py-1.5 pr-4">
                  <span className={`px-1.5 py-0.5 text-[10px] font-bold rounded-full uppercase ${eb(row.target)}`}>
                    {row.target}
                  </span>
                </td>
                <td className="py-1.5 pr-4 text-right text-slate-600">{fmtTokens(row.inputTokens)}</td>
                <td className="py-1.5 pr-4 text-right text-slate-600">{fmtTokens(row.outputTokens)}</td>
                <td className="py-1.5 text-right font-semibold text-slate-700">{fmtCost(row.cost)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > VISIBLE_ROWS && (
        <ShowMoreToggle
          expanded={expanded}
          total={rows.length}
          onToggle={() => setExpanded(value => !value)}
        />
      )}
    </div>
  );
}
