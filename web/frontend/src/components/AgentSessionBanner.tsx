import { Trash2 } from 'lucide-react';
import type { AgentSession } from '../types/agent';
import { relativeTime, workspaceLabel } from '../utils/agentWorkspaceHelpers';

type Props = {
  session: AgentSession;
  connected: boolean;
  connecting: boolean;
  stateActiveTurnId: string | null;
  sessionResourceSnapshot: { skills?: string[]; prompts?: string[]; hooks?: string[]; plugins?: string[] } | undefined;
  sessionResourceGroup: string;
  resourceCount: number;
  onConnect: () => void;
  onRemoveSession: () => void;
};

export default function AgentSessionBanner({
  session,
  connected,
  connecting,
  stateActiveTurnId,
  sessionResourceSnapshot,
  sessionResourceGroup,
  resourceCount,
  onConnect,
  onRemoveSession,
}: Props) {
  const canAct = !connected && !connecting && !stateActiveTurnId;

  return (
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
          onClick={() => {
            if (
              window.confirm(
                'Remove this conversation from the list? Provider-side history is kept.',
              )
            ) {
              onRemoveSession();
            }
          }}
          disabled={Boolean(stateActiveTurnId)}
          className="rounded-md p-1 text-slate-400 hover:bg-white hover:text-red-600 disabled:opacity-40"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
