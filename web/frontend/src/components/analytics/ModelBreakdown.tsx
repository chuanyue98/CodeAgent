import { fmtCost, fmtTokens } from '../../api/analytics';
import { useT } from '../../i18n/context';
import { eb, ec } from './present';
import { SectionTitle } from './ChartCards';
import type { RangeModelStat } from './rangeStats';

export interface ModelBreakdownProps {
  rangeModels: RangeModelStat[];
  selectedModel: string | null;
  onSelectModel: (model: string | null) => void;
  totalCost: number;
}

export default function ModelBreakdown({
  rangeModels,
  selectedModel,
  onSelectModel,
  totalCost,
}: ModelBreakdownProps) {
  const t = useT();
  if (rangeModels.length === 0) return null;
  const activeModel = rangeModels.find(m => m.model === selectedModel) ?? null;

  return (
    <div className="animate-fade-rise stagger-6 glass-card p-5">
      <SectionTitle>{t('model.breakdown')}</SectionTitle>
      <div className="flex flex-col lg:flex-row gap-4">
        <div className="flex-1 space-y-1.5 min-w-0">
          {rangeModels.map(m => {
            const pct = totalCost > 0 ? (m.cost / totalCost) * 100 : 0;
            const isSelected = selectedModel === m.model;
            return (
              <button
                key={m.model}
                aria-pressed={isSelected}
                onClick={() => onSelectModel(isSelected ? null : m.model)}
                className={`w-full text-left rounded-xl px-3 py-2.5 transition-all border ${
                  isSelected
                    ? 'bg-slate-100 border-slate-300'
                    : 'bg-slate-50/60 border-transparent hover:bg-slate-100/70 hover:border-slate-200'
                }`}
              >
                <div className="flex items-center justify-between gap-2 mb-1.5">
                  <span className="text-xs font-semibold text-slate-700 truncate">{m.model}</span>
                  <div className="flex items-center gap-2 shrink-0">
                    {m.targets.map(t => (
                      <span key={t} className={`text-[9px] font-black uppercase px-1.5 py-0.5 rounded-full ${eb(t)}`}>{t}</span>
                    ))}
                    <span className="text-xs font-bold text-slate-600">{fmtCost(m.cost)}</span>
                    <span className="text-[10px] text-slate-400">{pct.toFixed(1)}%</span>
                  </div>
                </div>
                <div className="w-full h-1 bg-slate-200 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${Math.min(pct, 100)}%`,
                      background: m.targets[0] ? ec(m.targets[0]) : '#94a3b8',
                    }}
                  />
                </div>
              </button>
            );
          })}
        </div>

        {activeModel && (() => {
          const m = activeModel;
          const pct = totalCost > 0 ? (m.cost / totalCost) * 100 : 0;
          const totalTok = m.inputTokens + m.outputTokens + m.cacheCreationTokens + m.cacheReadTokens;
          const ioRatio = m.outputTokens > 0 ? m.inputTokens / m.outputTokens : 0;
          const ioLabel = ioRatio < 0.1 ? '0:1' : ioRatio > 10 ? '1:0' : `${ioRatio.toFixed(1)}:1`;
          const ioText = ioRatio < 0.3
            ? t('model.generationHeavy')
            : ioRatio > 3
            ? t('model.contextHeavy')
            : t('model.balanced');
          const rows = [
            { label: t('analytics.input'), cost: m.inputCost, tokens: m.inputTokens },
            { label: t('analytics.output'), cost: m.outputCost, tokens: m.outputTokens },
            { label: t('model.cacheWrite'), cost: m.cacheWriteCost, tokens: m.cacheCreationTokens },
            { label: t('model.cacheRead'), cost: m.cacheReadCost, tokens: m.cacheReadTokens },
          ];
          return (
            <div className="w-full lg:w-72 shrink-0 rounded-xl border border-slate-200 bg-slate-50/80 p-4 space-y-4">
              <div>
                <p className="text-sm font-bold text-slate-800 truncate">{m.model}</p>
                <div className="flex items-center gap-2 mt-1 text-xs text-slate-500">
                  <span className="font-semibold text-slate-700">{pct.toFixed(1)}%</span>
                  <span>{t('model.usage')}</span>
                  <span className="text-slate-300">•</span>
                  <span className="font-semibold text-slate-700">{ioLabel}</span>
                  <span>I/O</span>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-lg bg-white border border-slate-200 p-2.5">
                  <p className="text-base font-bold text-slate-800">{fmtCost(m.cost)}</p>
                  <p className="text-[10px] text-slate-400 mt-0.5">{t('model.totalCost')}</p>
                </div>
                <div className="rounded-lg bg-white border border-slate-200 p-2.5">
                  <p className="text-base font-bold text-slate-800">{fmtTokens(totalTok)}</p>
                  <p className="text-[10px] text-slate-400 mt-0.5">{t('model.allTokens')}</p>
                </div>
              </div>

              <div>
                <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest mb-1.5">
                  {t('model.tokenBreakdown')}
                </p>
                <div className="space-y-1">
                  {rows.map(({ label, cost, tokens }) => (
                    <div key={label} className="flex items-center justify-between text-xs">
                      <span className="text-slate-500 w-20">{label}</span>
                      <span className="font-semibold text-slate-700 w-16 text-right">{fmtCost(cost)}</span>
                      <span className="text-slate-400 text-right">{fmtTokens(tokens)}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-lg bg-white border border-slate-200 p-2.5">
                <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest mb-1">
                  {t('model.ioRatio')}
                </p>
                <p className="text-xs text-slate-600">{ioText}</p>
              </div>
            </div>
          );
        })()}
      </div>
    </div>
  );
}
