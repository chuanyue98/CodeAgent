import { AlertTriangle, Loader2, X, Zap } from 'lucide-react';
import { useT } from '../i18n/context';
import { AGENT_ENGINES, findEngine } from './terminalEngines';

export interface SmartHandoffBannerProps {
  activeEngine: string;
  targetEngines?: Array<{ id: string; name: string }>;
  onHandoff: (targetEngine: string) => Promise<void> | void;
  onDismiss: () => void;
  loadingEngine?: string | null;
}

export default function SmartHandoffBanner({
  activeEngine,
  targetEngines,
  onHandoff,
  onDismiss,
  loadingEngine,
}: SmartHandoffBannerProps) {
  const t = useT();

  const engineObj = findEngine(activeEngine);
  const engineDisplayName =
    (engineObj?.nameKey ? t(engineObj.nameKey) : engineObj?.name) || activeEngine;

  const defaultTargets = AGENT_ENGINES.filter(
    e =>
      e.id.toLowerCase() !== activeEngine.toLowerCase() &&
      e.name?.toLowerCase() !== activeEngine.toLowerCase(),
  )
    .slice(0, 3)
    .map(e => ({
      id: e.id,
      name: (e.nameKey ? t(e.nameKey) : e.name) || e.id,
    }));

  const targets = targetEngines ?? defaultTargets;

  return (
    <div
      role="alert"
      aria-live="polite"
      data-testid="smart-handoff-banner"
      className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-300 bg-amber-50/95 px-4 py-2.5 text-xs text-amber-900 shadow-sm backdrop-blur"
    >
      <div className="flex min-w-0 items-center gap-2">
        <AlertTriangle size={16} className="shrink-0 text-amber-600" />
        <span className="font-medium leading-relaxed">
          {t('handoff.rateLimitMessage', { engine: engineDisplayName })}
        </span>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <div className="flex items-center gap-1.5">
          {targets.map(target => {
            const isLoading = loadingEngine === target.id;
            return (
              <button
                key={target.id}
                type="button"
                disabled={Boolean(loadingEngine)}
                aria-busy={isLoading}
                onClick={() => void onHandoff(target.id)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-amber-300/80 bg-amber-100/90 px-2.5 py-1 text-xs font-medium text-amber-800 shadow-xs transition hover:bg-amber-200 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isLoading ? (
                  <Loader2
                    size={13}
                    className="animate-spin text-amber-700"
                    data-testid="loading-spinner"
                  />
                ) : (
                  <Zap size={13} className="fill-amber-500/20 text-amber-600" />
                )}
                <span>{target.name}</span>
              </button>
            );
          })}
        </div>

        <button
          type="button"
          onClick={onDismiss}
          data-testid="smart-handoff-dismiss"
          aria-label={t('handoff.dismiss')}
          title={t('handoff.dismiss')}
          className="rounded-lg p-1 text-amber-600 transition hover:bg-amber-200/60 hover:text-amber-900"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
}
