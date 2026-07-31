import { useState } from 'react';
import { Loader2, Trash2, WifiOff } from 'lucide-react';
import { reconnectAgentProvider } from '../api/agent';
import type { AgentSession } from '../types/agent';
import type { ProviderConnectivity } from '../state/agentSessionReducer';
import { relativeTime, workspaceLabel } from '../utils/agentWorkspaceHelpers';

type Props = {
  session: AgentSession;
  connected: boolean;
  connecting: boolean;
  stateActiveTurnId: string | null;
  provider: ProviderConnectivity | null;
  sessionResourceSnapshot: { skills?: string[]; prompts?: string[]; hooks?: string[]; plugins?: string[] } | undefined;
  sessionResourceGroup: string;
  resourceCount: number;
  onConnect: () => void;
  onRemoveSession: () => void;
};

/**
 * Shown while the Gateway is retrying a provider that dropped.
 *
 * The Gateway reconnects on its own with an exponential backoff of up to a
 * minute, so the useful thing here is telling the user it is *working on
 * it* — and giving whoever just fixed the cause (installed the CLI, signed
 * in) a way to skip the remaining wait.
 */
function ProviderOutage({ provider, providerId }: { provider: ProviderConnectivity; providerId: string }) {
  const [retrying, setRetrying] = useState(false);

  const retryNow = () => {
    setRetrying(true);
    reconnectAgentProvider(providerId)
      .catch(() => { /* The banner stays up; the next event corrects it. */ })
      .finally(() => setRetrying(false));
  };

  return (
    <div
      role="status"
      className="mb-2 flex items-center justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900"
    >
      <span className="flex min-w-0 items-center gap-2">
        <WifiOff className="h-3.5 w-3.5 shrink-0" />
        <span className="min-w-0">
          <span className="font-semibold">{providerId} disconnected.</span>{' '}
          <span className="text-amber-800">
            Reconnecting automatically
            {provider.attempt > 0 && ` (attempt ${provider.attempt})`}.
          </span>
          {provider.reason && (
            <span className="mt-0.5 block truncate text-[10px] text-amber-700">{provider.reason}</span>
          )}
        </span>
      </span>
      <button
        onClick={retryNow}
        disabled={retrying}
        className="inline-flex shrink-0 items-center gap-1 rounded-md border border-amber-300 px-2 py-1 font-semibold hover:bg-amber-100 disabled:opacity-50"
      >
        {retrying && <Loader2 className="h-3 w-3 animate-spin" />}
        Retry now
      </button>
    </div>
  );
}

export default function AgentSessionBanner({
  session,
  connected,
  connecting,
  stateActiveTurnId,
  provider,
  sessionResourceSnapshot,
  sessionResourceGroup,
  resourceCount,
  onConnect,
  onRemoveSession,
}: Props) {
  const canAct = !connected && !connecting && !stateActiveTurnId;

  return (
    <>
    {provider && !provider.connected && (
      <ProviderOutage provider={provider} providerId={session.provider} />
    )}
    <div className="mb-3 flex items-center justify-between gap-3 rounded-lg border border-slate-100 bg-slate-50/70 px-3 py-2 text-xs text-slate-700">
      <div className="min-w-0">
        <p className="truncate font-semibold">
          {session.title || 'Untitled conversation'}
        </p>
        <p className="mt-0.5 truncate text-[10px] text-slate-500">
          {session.provider} · {workspaceLabel(session.cwd)} ·{' '}
          {relativeTime(session.updatedAt)}
        </p>
        <details className="mt-1 text-[10px] text-slate-500">
          <summary className="cursor-pointer font-medium text-primary hover:underline">
            Configured resources · {sessionResourceGroup} ({resourceCount})
          </summary>
          <div className="mt-1 space-y-0.5 rounded-md border border-slate-200 bg-white px-2 py-1.5">
            <p>
              <span className="font-semibold">Skills:</span>{' '}
              {sessionResourceSnapshot?.skills?.join(', ') || 'Unknown'}
            </p>
            <p>
              <span className="font-semibold">Prompts:</span>{' '}
              {sessionResourceSnapshot?.prompts?.join(', ') || 'Unknown'}
            </p>
            <p>
              <span className="font-semibold">Hooks:</span>{' '}
              {sessionResourceSnapshot?.hooks?.join(', ') || 'Unknown'}
            </p>
            <p>
              <span className="font-semibold">Plugins:</span>{' '}
              {sessionResourceSnapshot?.plugins?.join(', ') || 'Unknown'}
            </p>
            <p className="pt-0.5 italic">
              Snapshot captured at session creation; provider-native discovery
              may differ.
            </p>
          </div>
        </details>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {canAct && (
          <button
            className="font-semibold text-primary hover:underline"
            onClick={() => onConnect()}
          >
            Reconnect
          </button>
        )}
        <button
          aria-label="Remove current conversation"
          title="Remove local conversation"
          onClick={onRemoveSession}
          disabled={Boolean(stateActiveTurnId)}
          className="rounded-md p-1 text-slate-400 hover:bg-white hover:text-red-600 disabled:opacity-40"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
    </>
  );
}
