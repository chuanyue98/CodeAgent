import { fmtCost, fmtTokens, type DailyUsage, type MonthlyUsage } from '../../api/analytics';
import { eb } from './present';
import { SectionTitle } from './ChartCards';

export interface DetailTableProps {
  granularity: 'day' | 'month';
  monthly: MonthlyUsage[];
  rangeDaily: DailyUsage[];
  rangeLabel: string;
  hasRows: boolean;
}

export default function DetailTable({
  granularity, monthly, rangeDaily, rangeLabel, hasRows,
}: DetailTableProps) {
  if (!hasRows) return null;
  return (
    <div className="animate-fade-rise stagger-6 glass-card p-5">
      <SectionTitle>
        {granularity === 'month' ? 'Detail by month' : `Detail — last ${rangeLabel}`}
      </SectionTitle>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-100 text-slate-400">
              <th className="text-left py-2 pr-4 font-medium">
                {granularity === 'month' ? 'Month' : 'Date'}
              </th>
              <th className="text-left py-2 pr-4 font-medium">Engine</th>
              <th className="text-right py-2 pr-4 font-medium">Input</th>
              <th className="text-right py-2 pr-4 font-medium">Output</th>
              <th className="text-right py-2 font-medium">Cost</th>
            </tr>
          </thead>
          <tbody>
            {(granularity === 'month'
              ? [...monthly].reverse().map(m => ({
                  key: `${m.month}-${m.target}`, label: m.month, target: m.target,
                  inputTokens: m.inputTokens, outputTokens: m.outputTokens, cost: m.cost,
                }))
              : [...rangeDaily].reverse().map(d => ({
                  key: `${d.date}-${d.target}`, label: d.date, target: d.target,
                  inputTokens: d.inputTokens, outputTokens: d.outputTokens, cost: d.cost,
                }))
            ).map(row => (
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
    </div>
  );
}
