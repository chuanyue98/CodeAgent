import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Anchor, ChevronDown, ChevronUp, Package, Zap } from 'lucide-react';
import {
  fetchChatCapabilities,
  type ChatCapabilities,
  type ChatResourceSet,
} from '../api/chat';

interface SessionCapabilitiesProps {
  engine: string;
  group: string;
  projectPath: string | null;
}

const RESOURCE_META: Array<{
  key: keyof ChatResourceSet;
  label: string;
  icon: typeof Package;
}> = [
  { key: 'skills', label: 'Skills', icon: Package },
  { key: 'hooks', label: 'Hooks', icon: Anchor },
  { key: 'plugins', label: 'Plugins', icon: Zap },
];

export default function SessionCapabilities({
  engine,
  group,
  projectPath,
}: SessionCapabilitiesProps) {
  const requestKey = `${engine}\u0000${group}\u0000${projectPath ?? ''}`;
  const [result, setResult] = useState<{
    key: string;
    capabilities: ChatCapabilities | null;
    failed: boolean;
  }>({ key: '', capabilities: null, failed: false });
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!engine) return;
    let cancelled = false;
    fetchChatCapabilities({ engine, group, projectPath })
      .then(data => {
        if (!cancelled) {
          setResult({ key: requestKey, capabilities: data, failed: false });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setResult({ key: requestKey, capabilities: null, failed: true });
        }
      });
    return () => { cancelled = true; };
  }, [engine, group, projectPath, requestKey]);

  const isCurrent = result.key === requestKey;
  const capabilities = isCurrent ? result.capabilities : null;
  const failed = isCurrent && result.failed;

  const activeCount = useMemo(() => {
    if (!capabilities) return 0;
    return Object.values(capabilities.active).reduce((sum, items) => sum + items.length, 0);
  }, [capabilities]);

  if (!engine) return null;

  if (failed) {
    return (
      <div role="status" className="mb-3 rounded-xl border border-amber-100 bg-amber-50/70 px-3 py-2 text-xs text-amber-800">
        Session capability status is unavailable. No capability assumptions were made.
      </div>
    );
  }

  if (!capabilities) {
    return <div className="mb-3 h-9 animate-pulse rounded-xl bg-slate-100" aria-label="Loading session capabilities" />;
  }

  return (
    <section aria-label="Current session capabilities" className="mb-3 rounded-xl border border-amber-100 bg-amber-50/60">
      <button
        type="button"
        onClick={() => setExpanded(value => !value)}
        aria-expanded={expanded}
        className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left"
      >
        <span className="flex min-w-0 items-center gap-2 text-xs text-amber-900">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate">
            Legacy Web Chat · {activeCount} CodeAgent-managed resources active
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-1 text-[11px] font-medium text-amber-800">
          Details {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </span>
      </button>

      {expanded && (
        <div className="space-y-3 border-t border-amber-100 px-3 py-3 text-xs">
          <p className="text-amber-900">{capabilities.notice}</p>

          <div className="grid gap-2 sm:grid-cols-3">
            {RESOURCE_META.map(({ key, label, icon: Icon }) => {
              const active = capabilities.active[key];
              const inactive = capabilities.configuredButInactive[key];
              return (
                <div key={key} className="rounded-lg border border-amber-100 bg-white/70 p-2.5">
                  <div className="mb-1.5 flex items-center gap-1.5 font-semibold text-slate-700">
                    <Icon className="h-3.5 w-3.5" /> {label}
                  </div>
                  <p className="text-slate-700">Active: {active.length}</p>
                  <p className="mt-1 text-slate-500">
                    Configured but inactive: {inactive.length}
                  </p>
                  {inactive.length > 0 && (
                    <ul className="mt-1.5 space-y-1 text-slate-500">
                      {inactive.map(item => <li key={item} className="truncate" title={item}>{item}</li>)}
                    </ul>
                  )}
                </div>
              );
            })}
          </div>

          <p className="text-[11px] text-slate-500">
            Provider-native capabilities: unknown — the legacy one-shot protocol does not expose discovery results.
          </p>
        </div>
      )}
    </section>
  );
}
