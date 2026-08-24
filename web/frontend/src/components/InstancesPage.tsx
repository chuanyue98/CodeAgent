import { useCallback, useState } from 'react';
import { Link } from 'react-router';
import {
  Clock3,
  MessageSquareText,
  Square,
  TerminalSquare,
} from 'lucide-react';
import { fetchInstances, stopInstance, type AgentInstance, type InstanceKind } from '../api/instances';
import { engineLabel } from '../utils/engines';
import usePolling from '../hooks/usePolling';
import ConfirmDialog from './shared/ConfirmDialog';
import { useT } from '../i18n/context';
import type { TranslationKey } from '../i18n/locales/en';

const KIND_ICONS: Record<InstanceKind, typeof Clock3> = {
  chat: MessageSquareText,
  terminal: TerminalSquare,
  task: Clock3,
};

const KIND_LABEL_KEYS: Record<InstanceKind, TranslationKey> = {
  chat: 'instances.kind.chat',
  terminal: 'instances.kind.terminal',
  task: 'instances.kind.task',
};

const STATUS_COLORS: Record<string, string> = {
  ready: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  running: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  busy: 'bg-blue-50 text-blue-700 border-blue-200',
  starting: 'bg-amber-50 text-amber-700 border-amber-200',
  disconnected: 'bg-slate-100 text-slate-500 border-slate-200',
  error: 'bg-red-50 text-red-700 border-red-200',
  failed: 'bg-red-50 text-red-700 border-red-200',
};

function elapsedLabel(startedAt: string): string {
  const seconds = Math.max(0, (Date.now() - new Date(startedAt).getTime()) / 1000);
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}min`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}min`;
}

/**
 * 实例管理页：回答"我现在到底有几个 Agent 在跑"。
 * 汇总 Web 聊天会话、浏览器 PTY 终端、后台任务运行三类实例，
 * 终端/任务可在此直接停止，聊天会话可跳回工作台。
 */
export default function InstancesPage() {
  const t = useT();
  const [instances, setInstances] = useState<AgentInstance[]>([]);
  const [pendingStop, setPendingStop] = useState<AgentInstance | null>(null);

  const refresh = useCallback(async () => {
    try {
      setInstances(await fetchInstances());
    } catch {
      // 轮询场景下静默失败，下一 tick 会重试（usePolling 自带退避）。
    }
  }, []);
  usePolling(refresh, 5000);

  const onConfirmStop = useCallback(async () => {
    if (!pendingStop) return;
    try {
      await stopInstance(pendingStop.kind, pendingStop.id);
    } finally {
      setPendingStop(null);
      void refresh();
    }
  }, [pendingStop, refresh]);

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600">{t('instances.intro')}</p>

      {instances.length === 0 ? (
        <div className="glass-card p-8 text-center text-sm text-slate-400">
          {t('instances.empty')}
        </div>
      ) : (
        <div className="space-y-2">
          {instances.map(instance => {
            const KindIcon = KIND_ICONS[instance.kind];
            return (
              <div
                key={`${instance.kind}:${instance.id}`}
                className="glass-card flex items-center gap-4 p-4"
              >
                <KindIcon className="h-5 w-5 shrink-0 text-slate-400" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-slate-800">
                      {instance.title || engineLabel(instance.engine)}
                    </span>
                    <span className="rounded-md border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] font-medium text-slate-500">
                      {t(KIND_LABEL_KEYS[instance.kind])}
                    </span>
                    <span
                      className={`rounded-md border px-1.5 py-0.5 text-[10px] font-medium ${
                        STATUS_COLORS[instance.status] ?? 'bg-slate-100 text-slate-500 border-slate-200'
                      }`}
                    >
                      {instance.status}
                    </span>
                  </div>
                  <div className="mt-0.5 truncate text-xs text-slate-400">
                    {engineLabel(instance.engine)} · {instance.cwd}
                    {instance.pid != null && ` · PID ${instance.pid}`}
                    {` · ${elapsedLabel(instance.started_at)}`}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {instance.kind === 'chat' && (
                    <Link
                      to="/agent/web"
                      className="rounded-lg border border-primary/30 px-3 py-1.5 text-xs font-semibold text-primary hover:bg-primary/10"
                    >
                      {t('instances.openChat')}
                    </Link>
                  )}
                  {instance.stoppable && (
                    <button
                      type="button"
                      onClick={() => setPendingStop(instance)}
                      className="flex items-center gap-1 rounded-lg border border-red-200 px-3 py-1.5 text-xs font-semibold text-red-600 hover:bg-red-50"
                    >
                      <Square className="h-3 w-3" />
                      {t('instances.stop')}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {pendingStop && (
        <ConfirmDialog
          title={t('instances.stopConfirmTitle')}
          description={t('instances.stopConfirmDescription', {
            name: pendingStop.title || engineLabel(pendingStop.engine),
          })}
          confirmLabel={t('instances.stop')}
          onConfirm={onConfirmStop}
          onCancel={() => setPendingStop(null)}
        />
      )}
    </div>
  );
}
