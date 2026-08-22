import { Link } from 'react-router';
import { ArrowUpRight as LinkArrow, Clock, Terminal } from 'lucide-react';
import { fmtCost, fmtTokens, type EngineSummary, type SessionUsage } from '../../api/analytics';
import { eb, ec, timeAgo } from './present';
import { SectionTitle } from './ChartCards';
import { CostDistributionCard, type PieDatum } from './ChartCards';

export interface EnginePanelProps {
  rangeEngines: EngineSummary[];
  pieData: PieDatum[];
  sessionCount: number;
  avgCostPerSession: number;
  totalLabel: string;
  recentSessions: SessionUsage[];
}

/** Engine cards column plus the pie / recent-sessions sidebar beside them. */
export default function EnginePanel({
  rangeEngines,
  pieData,
  sessionCount,
  avgCostPerSession,
  totalLabel,
  recentSessions,
}: EnginePanelProps) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div className="lg:col-span-2 grid grid-cols-1 sm:grid-cols-2 gap-3">
        {rangeEngines.map((eng, i) => (
          <div
            key={eng.target}
            className={`animate-fade-rise stagger-${Math.min(i + 2, 7)} glass-card group p-4 transition-all duration-300 hover:-translate-y-0.5 hover:shadow-[0_24px_36px_-16px_rgba(15,23,42,0.12)]`}
          >
            <div className="flex items-center justify-between mb-3">
              <span className={`text-[11px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full ${eb(eng.target)}`}>
                {eng.target}
              </span>
              <span className="text-xs text-slate-400">{eng.sessionCount} sessions</span>
            </div>
            <div className="space-y-1.5 text-xs">
              {[
                { label: 'Input', value: fmtTokens(eng.inputTokens) },
                { label: 'Output', value: fmtTokens(eng.outputTokens) },
                { label: 'Cache', value: fmtTokens(eng.cacheCreationTokens + eng.cacheReadTokens) },
              ].map(({ label, value }) => (
                <div key={label} className="flex justify-between">
                  <span className="text-slate-400">{label}</span>
                  <span className="font-semibold text-slate-700">{value}</span>
                </div>
              ))}
              <div className="flex justify-between pt-1.5 border-t border-slate-100">
                <span className="text-slate-500 font-medium">Est. Cost</span>
                <span className="font-bold" style={{ color: ec(eng.target) }}>
                  {fmtCost(eng.cost)}
                </span>
              </div>
            </div>
            <div className="mt-2 text-[10px] text-slate-300 truncate">
              {eng.models.slice(0, 2).join(', ')}{eng.models.length > 2 && ` +${eng.models.length - 2} more`}
            </div>
          </div>
        ))}
        {rangeEngines.length === 0 && (
          <p className="text-xs text-slate-400">No engine usage in this range.</p>
        )}
      </div>

      <div className="animate-fade-rise stagger-5 flex flex-col gap-3">
        <CostDistributionCard pieData={pieData} />

        <div className="glass-card p-4 flex-1">
          <SectionTitle
            action={
              <Link
                to="/activity/sessions"
                className="flex items-center gap-1 text-[10px] font-semibold text-primary hover:underline"
              >
                All sessions <LinkArrow className="h-3 w-3" />
              </Link>
            }
          >
            <span className="flex items-center gap-1.5"><Terminal className="w-3 h-3" /> Sessions</span>
          </SectionTitle>
          <div className="grid grid-cols-2 gap-2 mb-3">
            <div className="p-2 rounded-lg bg-slate-50 border border-slate-100 text-center">
              <p className="text-lg font-bold text-blue-600">{sessionCount}</p>
              <p className="text-[9px] text-slate-600 uppercase tracking-wide">
                {totalLabel}
              </p>
            </div>
            <div className="p-2 rounded-lg bg-slate-50 border border-slate-100 text-center">
              <p className="text-lg font-bold text-green-700">{fmtCost(avgCostPerSession)}</p>
              <p className="text-[9px] text-slate-600 uppercase tracking-wide">Avg / session</p>
            </div>
          </div>
          <div className="space-y-1.5">
            <div className="flex items-center gap-1 text-[10px] text-slate-400 font-medium mb-1">
              <Clock className="w-3 h-3" /> Recent activity
            </div>
            {recentSessions.map(s => (
              <div
                key={`${s.target}::${s.sessionId}`}
                className="flex items-center justify-between text-xs p-1.5 rounded-md bg-slate-50/80 hover:bg-slate-100/70 transition-colors border border-slate-100"
              >
                <div className="flex flex-col min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="font-medium truncate text-slate-700" title={s.projectPath}>
                      {s.projectPath.split(/[\\/]/).pop() || s.projectPath || '—'}
                    </span>
                    <span className={`shrink-0 px-1 py-0 text-[9px] font-bold rounded uppercase ${eb(s.target)}`}>
                      {s.target}
                    </span>
                  </div>
                  <span className="text-[10px] text-slate-400">{timeAgo(s.lastActivity)}</span>
                </div>
                <div className="text-right shrink-0 ml-2">
                  <div className="font-mono text-[11px] font-semibold text-slate-700">
                    {fmtCost(s.cost)}
                  </div>
                  <div className="text-[9px] text-slate-400">
                    {fmtTokens(s.inputTokens + s.outputTokens)}
                  </div>
                </div>
              </div>
            ))}
            {recentSessions.length === 0 && (
              <p className="text-[11px] text-slate-400">No sessions in this range.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
