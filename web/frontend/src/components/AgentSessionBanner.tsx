import { useState } from 'react';
import { Loader2, Trash2, WifiOff } from 'lucide-react';
import { reconnectAgentProvider } from '../api/agent';
import type { AgentSession, ResourceSnapshot } from '../types/agent';
import type { ProviderConnectivity } from '../state/agentSessionReducer';
import { relativeTime, workspaceLabel } from '../utils/agentWorkspaceHelpers';

type Props = {
  session: AgentSession;
  connected: boolean;
  connecting: boolean;
  stateActiveTurnId: string | null;
  provider: ProviderConnectivity | null;
  sessionResourceSnapshot: ResourceSnapshot | undefined;
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
          <span className="font-semibold">{providerId} 连接已断开。</span>{' '}
          <span className="text-amber-800">
            正在自动重连
            {provider.attempt > 0 && `（第 ${provider.attempt} 次尝试）`}。
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
        立即重试
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
  // appliedKinds is the per-kind injection receipt: a kind absent from it
  // was never sent to the provider, so presenting it as loaded would be a lie.
  const applied = new Set(sessionResourceSnapshot?.appliedKinds ?? []);
  const kinds: { label: string; names?: string[]; isApplied: boolean }[] = [
    { label: '技能', names: sessionResourceSnapshot?.skills, isApplied: applied.has('skills') },
    { label: '提示词', names: sessionResourceSnapshot?.prompts, isApplied: applied.has('prompts') },
    { label: '钩子', names: sessionResourceSnapshot?.hooks, isApplied: applied.has('hooks') },
    { label: '插件', names: sessionResourceSnapshot?.plugins, isApplied: applied.has('plugins') },
  ];
  const anyConfigured = resourceCount > 0;
  const allApplied = kinds.filter(k => (k.names?.length ?? 0) > 0).every(k => k.isApplied);
  const showNotApplied = anyConfigured && !allApplied;

  return (
    <>
    {provider && !provider.connected && (
      <ProviderOutage provider={provider} providerId={session.provider} />
    )}
    <div className="mb-3 flex items-center justify-between gap-3 rounded-lg border border-slate-100 bg-slate-50/70 px-3 py-2 text-xs text-slate-700">
      <div className="min-w-0">
        <p className="truncate font-semibold">
          {session.title || '未命名会话'}
        </p>
        <p className="mt-0.5 truncate text-[10px] text-slate-500">
          {session.provider} · {workspaceLabel(session.cwd)} ·{' '}
          {relativeTime(session.updatedAt)}
        </p>
        <details className="mt-1 text-[10px] text-slate-500">
          <summary className="cursor-pointer font-medium text-primary hover:underline">
            已配置资源 · {sessionResourceGroup}（{resourceCount}）
            {showNotApplied && (
              <span className="ml-1.5 rounded bg-amber-100 px-1 py-0.5 font-semibold text-amber-800">
                未应用
              </span>
            )}
            {anyConfigured && allApplied && (
              <span className="ml-1.5 rounded bg-emerald-100 px-1 py-0.5 font-semibold text-emerald-800">
                已应用
              </span>
            )}
          </summary>
          <div className="mt-1 space-y-0.5 rounded-md border border-slate-200 bg-white px-2 py-1.5">
            {kinds.map(({ label, names, isApplied }) => (
              <p key={label}>
                <span className="font-semibold">{label}：</span>{' '}
                {names?.join(', ') || '未知'}
                {anyConfigured && (names?.length ?? 0) > 0 && !isApplied && (
                  <span className="ml-1.5 rounded bg-amber-50 px-1 font-medium text-amber-800">
                    未注入
                  </span>
                )}
              </p>
            ))}
            <p className="pt-0.5 italic">
              {showNotApplied
                ? '琥珀色标记的资源类型已在资源组中配置，但未注入本会话——智能体将在缺少这些资源的情况下运行。'
                : '快照在会话创建时捕获；引擎自身的发现结果可能不同。'}
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
            重新连接
          </button>
        )}
        <button
          aria-label="移除当前会话"
          title="移除本地会话"
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
