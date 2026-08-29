import { useCallback, useMemo, useState } from 'react';
import {
  Clock3,
  MessageSquareText,
  Square,
  TerminalSquare,
  Radar,
} from 'lucide-react';
import { fetchInstances, stopInstance, type AgentInstance, type InstanceKind } from '../api/instances';
import { engineLabel } from '../utils/engines';
import { eb } from './analytics/present';
import usePolling from '../hooks/usePolling';
import ConfirmDialog from './shared/ConfirmDialog';
import { useT } from '../i18n/context';
import type { TranslationKey } from '../i18n/locales/en';

const KIND_ORDER: InstanceKind[] = ['chat', 'terminal', 'task'];

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

/** 活着的状态：就绪/忙碌/运行中/启动中，状态点带脉冲光环。 */
const LIVE_STATUSES = new Set(['ready', 'busy', 'running', 'starting']);

const STATUS_DOT: Record<string, string> = {
  ready: 'bg-emerald-500',
  running: 'bg-emerald-500',
  busy: 'bg-blue-500',
  starting: 'bg-amber-500',
  disconnected: 'bg-slate-300',
  error: 'bg-red-500',
  failed: 'bg-red-500',
};

const TWO_DAYS_IN_SECONDS = 48 * 3600;

/** Uptime for something still running, age for something that is not. Past two
 *  days the hours stop carrying meaning -- a chat from last month read as
 *  "1081h 59min". */
function elapsedLabel(startedAt: string): string {
  const seconds = Math.max(0, (Date.now() - new Date(startedAt).getTime()) / 1000);
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}min`;
  if (seconds < TWO_DAYS_IN_SECONDS) {
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}min`;
  }
  return `${Math.floor(seconds / 86400)}d`;
}

function StatusDot({ status }: { status: string }) {
  const color = STATUS_DOT[status] ?? 'bg-slate-300';
  if (!LIVE_STATUSES.has(status)) {
    return <span className={`h-2 w-2 rounded-full ${color}`} />;
  }
  return (
    <span className="relative flex h-2 w-2">
      <span className={`absolute inline-flex h-full w-full rounded-full ${color} opacity-60 animate-ping`} />
      <span className={`relative inline-flex h-2 w-2 rounded-full ${color}`} />
    </span>
  );
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

  const groups = useMemo(() => {
    const byKind = new Map<InstanceKind, AgentInstance[]>();
    for (const instance of instances) {
      const list = byKind.get(instance.kind) ?? [];
      list.push(instance);
      byKind.set(instance.kind, list);
    }
    return KIND_ORDER.filter(kind => byKind.has(kind)).map(kind => ({
      kind,
      items: byKind.get(kind) ?? [],
    }));
  }, [instances]);

  const liveCount = instances.filter(i => LIVE_STATUSES.has(i.status)).length;

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
    // Capped: a full-width row put its title on the far left and its age on
    // the far right, with a third of the screen of nothing in between.
    <div className="max-w-5xl space-y-5">
      {/* ── 概览条 ── */}
      <div className="glass-card animate-fade-rise flex items-center gap-6 px-5 py-4">
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <Radar className="h-4 w-4" />
          </span>
          <div>
            <p className="text-sm font-semibold text-slate-800">
              {t('instances.summary', {
                live: String(liveCount),
                total: String(instances.length),
              })}
            </p>
            <p className="text-[11px] text-slate-400">{t('instances.intro')}</p>
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {KIND_ORDER.map(kind => {
            const count = instances.filter(i => i.kind === kind).length;
            const KindIcon = KIND_ICONS[kind];
            return (
              <span
                key={kind}
                className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors ${
                  count > 0
                    ? 'border-slate-200 bg-white text-slate-700'
                    : 'border-slate-100 bg-slate-50 text-slate-300'
                }`}
              >
                <KindIcon className="h-3.5 w-3.5" />
                {t(KIND_LABEL_KEYS[kind])}
                <span className={`font-mono text-[11px] ${count > 0 ? 'text-primary' : ''}`}>
                  {count}
                </span>
              </span>
            );
          })}
        </div>
      </div>

      {/* ── 空态 ── */}
      {instances.length === 0 && (
        <div className="glass-card animate-fade-rise stagger-2 flex flex-col items-center gap-2 p-12 text-center">
          <Radar className="h-8 w-8 text-slate-200" />
          <p className="text-sm font-medium text-slate-500">{t('instances.empty')}</p>
          <p className="max-w-sm text-xs text-slate-400">{t('instances.emptyHint')}</p>
        </div>
      )}

      {/* ── 分组列表 ── */}
      {groups.map((group, groupIndex) => {
        const KindIcon = KIND_ICONS[group.kind];
        return (
          <section
            key={group.kind}
            className={`animate-fade-rise stagger-${Math.min(groupIndex + 2, 7)} space-y-2`}
          >
            <header className="flex items-center gap-2 px-1">
              <KindIcon className="h-3.5 w-3.5 text-slate-400" />
              <h3 className="text-xs font-semibold tracking-wide text-slate-500 uppercase">
                {t(KIND_LABEL_KEYS[group.kind])}
              </h3>
              <span className="font-mono text-[11px] text-slate-300">{group.items.length}</span>
              <span className="h-px flex-1 bg-slate-100" />
            </header>

            <div className="space-y-1.5">
              {group.items.map(instance => (
                <div
                  key={`${instance.kind}:${instance.id}`}
                  className="group glass-card-flat flex items-center gap-4 px-4 py-3 transition-all duration-200 hover:-translate-y-px hover:shadow-[0_24px_36px_-14px_rgba(15,23,42,0.14)]"
                >
                  <StatusDot status={instance.status} />

                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium text-slate-800">
                        {instance.title || engineLabel(instance.engine)}
                      </span>
                      <span className={`shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-semibold ${eb(instance.engine)}`}>
                        {engineLabel(instance.engine)}
                      </span>
                    </div>
                    <div className="mt-0.5 truncate font-mono text-[11px] text-slate-400">
                      {instance.cwd}
                      {instance.pid != null && <span className="text-slate-300"> · pid {instance.pid}</span>}
                    </div>
                  </div>

                  <div className="flex shrink-0 items-center gap-3">
                    <span
                      className="font-mono text-[11px] text-slate-400 tabular-nums"
                      title={new Date(instance.started_at).toLocaleString()}
                    >
                      {elapsedLabel(instance.started_at)}
                    </span>
                    {instance.stoppable && (
                      <button
                        type="button"
                        onClick={() => setPendingStop(instance)}
                        aria-label={t('instances.stop')}
                        className="flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-[11px] font-semibold text-slate-400 transition-colors hover:border-red-200 hover:bg-red-50 hover:text-red-600"
                      >
                        <Square className="h-3 w-3" />
                        {t('instances.stop')}
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>
        );
      })}

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
