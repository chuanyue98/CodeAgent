import {
  ChevronDown,
  ChevronRight,
  EyeOff,
  FolderGit2,
  History,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  UserPlus,
} from 'lucide-react';
import { Link } from 'react-router';
import type { AgentSession, NativeAgentSession, ProviderCapabilities } from '../types/agent';
import {
  agentSessionReducer,
} from '../state/agentSessionReducer';
import {
  SESSION_PAGE_SIZE,
  relativeTime,
  sessionStatusLabel,
  workspaceLabel,
} from '../utils/agentWorkspaceHelpers';
import type { ConversationListItem } from '../utils/agentWorkspaceHelpers';
import type { UnavailableWorkspaceGroup } from '../pages/useAgentWorkspaceSessions';
import { buildTimelineLink } from '../utils/sessionLink';

const PAGE_SIZE = SESSION_PAGE_SIZE;

type Props = {
  nativeLoadingProviders: Set<string>;
  nativeSessionErrors: Record<string, string>;
  selectedProvider: string;
  sessionSearch: string;
  normalizedSessionSearch: string;
  filteredGatewaySessions: AgentSession[];
  recentSessions: AgentSession[];
  gatewaySessionLimit: number;
  nativeSessionLimit: number;
  unavailableSessionLimit: number;
  resumableNativeSessions: NativeAgentSession[];
  visibleNativeSessions: NativeAgentSession[];
  unavailableSessionCount: number;
  unavailableWorkspaceGroups: UnavailableWorkspaceGroup[];
  visibleUnavailableWorkspaceGroups: UnavailableWorkspaceGroup[];
  hiddenWorkspaceCount: number;
  showHiddenWorkspaces: boolean;
  onHideWorkspace: (path: string) => void;
  onUnhideWorkspace: (path: string) => void;
  onHideAllUnavailable: () => void;
  onToggleShowHiddenWorkspaces: () => void;
  onRegisterWorkspace: (path: string) => Promise<void>;
  registeringWorkspace: string | null;
  workspaceConversations: {
    path: string;
    label: string;
    conversations: ConversationListItem[];
  }[];
  showUnavailableHistory: boolean;
  expandedWorkspaces: Set<string>;
  collapsedWorkspaces: Set<string>;
  workspace: string;
  state: ReturnType<typeof agentSessionReducer>;
  loading: boolean;
  selectingKey: string | null;
  providers: ProviderCapabilities[];
  onNewSession: () => void;
  onSelectSession: (session: AgentSession) => void;
  onSelectNativeSession: (native: NativeAgentSession) => void;
  onRemoveSession: (session: AgentSession) => void;
  onRetryNativeSessions: () => void;
  onSearchChange: (value: string) => void;
  onGatewayLimitChange: (value: number) => void;
  onNativeLimitChange: (value: number) => void;
  onUnavailableLimitChange: (value: number) => void;
  onToggleExpandedWorkspace: (path: string) => void;
  onToggleCollapsedWorkspace: (path: string) => void;
  onShowUnavailableHistoryChange: (value: boolean) => void;
};

export default function AgentWorkspaceSidebar({
  nativeLoadingProviders,
  nativeSessionErrors,
  selectedProvider,
  sessionSearch,
  normalizedSessionSearch,
  filteredGatewaySessions,
  recentSessions,
  gatewaySessionLimit,
  nativeSessionLimit,
  unavailableSessionLimit,
  resumableNativeSessions,
  visibleNativeSessions,
  unavailableSessionCount,
  unavailableWorkspaceGroups,
  visibleUnavailableWorkspaceGroups,
  hiddenWorkspaceCount,
  showHiddenWorkspaces,
  onHideWorkspace,
  onUnhideWorkspace,
  onHideAllUnavailable,
  onToggleShowHiddenWorkspaces,
  onRegisterWorkspace,
  registeringWorkspace,
  workspaceConversations,
  showUnavailableHistory,
  expandedWorkspaces,
  collapsedWorkspaces,
  workspace,
  state,
  loading,
  selectingKey,
  providers,
  onNewSession,
  onSelectSession,
  onSelectNativeSession,
  onRemoveSession,
  onRetryNativeSessions,
  onSearchChange,
  onGatewayLimitChange,
  onNativeLimitChange,
  onUnavailableLimitChange,
  onToggleExpandedWorkspace,
  onToggleCollapsedWorkspace,
  onShowUnavailableHistoryChange,
}: Props) {
  const selectedCapabilities = providers.find(provider => provider.providerId === selectedProvider);
  const nativeSessionsLoading = nativeLoadingProviders.has(selectedProvider);
  const nativeSessionsError = nativeSessionErrors[selectedProvider] || null;
  const unavailableHistoryExpanded =
    showUnavailableHistory || Boolean(normalizedSessionSearch);

  return (
    <aside aria-label="会话列表" className="glass-card flex w-60 shrink-0 flex-col p-3">
      <div className="mb-3 flex items-center justify-between border-b border-slate-100 pb-3">
        <span className="flex items-center gap-2 text-sm font-semibold text-slate-700">
          <Search className="h-4 w-4" /> 会话
        </span>
        <button
          onClick={onNewSession}
          disabled={Boolean(state.activeTurnId)}
          className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs font-semibold text-primary hover:bg-primary/10 disabled:opacity-40"
        >
          <Plus className="h-3.5 w-3.5" /> 新建
        </button>
      </div>
      <label className="relative mb-2 block">
        <span className="sr-only">搜索会话</span>
        <Search className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-400" />
        <input
          type="search"
          value={sessionSearch}
          onChange={event => {
            onSearchChange(event.target.value);
            onGatewayLimitChange(PAGE_SIZE);
            onNativeLimitChange(PAGE_SIZE);
            onUnavailableLimitChange(PAGE_SIZE);
          }}
          placeholder="搜索会话"
          className="w-full rounded-lg border border-slate-200 bg-white py-2 pl-8 pr-2 text-xs outline-none focus:border-primary"
        />
      </label>
      <div className="custom-scrollbar min-h-0 flex-1 space-y-1 overflow-y-auto">
        {loading && (
          <p className="px-2 text-xs text-slate-400">正在加载会话…</p>
        )}
        <p className="px-2 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
          工作区
        </p>
        {!loading && workspaceConversations.length === 0 && (
          <p className="px-2 text-xs italic text-slate-400">
            {normalizedSessionSearch
              ? '没有匹配的会话。'
              : '已注册的工作区中还没有会话'}
          </p>
        )}
        {workspaceConversations.map(group => {
          const expanded = Boolean(normalizedSessionSearch)
            || (group.path === workspace
              ? !collapsedWorkspaces.has(group.path)
              : expandedWorkspaces.has(group.path));
          return (
            <div key={group.path}>
              <button
                onClick={() => {
                  if (group.path === workspace) {
                    onToggleCollapsedWorkspace(group.path);
                    return;
                  }
                  onToggleExpandedWorkspace(group.path);
                }}
                aria-expanded={expanded}
                title={group.path}
                className="flex w-full items-center gap-1.5 rounded-lg px-2 py-2 text-left text-xs font-medium text-slate-600 hover:bg-slate-50"
              >
                {expanded ? (
                  <ChevronDown className="h-3.5 w-3.5 shrink-0" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5 shrink-0" />
                )}
                <FolderGit2 className="h-3.5 w-3.5 shrink-0 text-slate-400" />
                <span className="min-w-0 flex-1 truncate">{group.label}</span>
                <span className="text-[10px] text-slate-400">
                  {group.conversations.length}
                </span>
              </button>
              {expanded && (
                <div className="ml-3 border-l border-slate-100 pl-1">
                  {group.conversations.length === 0 ? (
                    <p className="px-2 py-1.5 text-[11px] italic text-slate-400">
                      还没有会话
                    </p>
                  ) : group.conversations.map(item =>
                    item.source === 'gateway' ? (
                      <div
                        key={item.key}
                        className={`group flex items-center gap-1 rounded-lg transition-colors ${
                          state.session?.id === item.session.id
                            ? 'bg-primary/10 text-primary'
                            : item.session.status === 'error'
                              ? 'bg-amber-50 text-amber-900 hover:bg-amber-100'
                              : 'text-slate-600 hover:bg-slate-50'
                        }`}
                      >
                        <button
                          onClick={() => void onSelectSession(item.session)}
                          disabled={Boolean(state.activeTurnId) || Boolean(selectingKey)}
                          title={`${item.session.cwd} · ${relativeTime(item.session.updatedAt)}`}
                          className="min-w-0 flex-1 rounded-lg px-2 py-2 text-left text-xs disabled:opacity-40"
                        >
                          <span className="flex items-center gap-1.5">
                            <span className="block min-w-0 flex-1 truncate font-medium">
                              {item.session.title || '未命名会话'}
                            </span>
                            {selectingKey === item.key && (
                              <Loader2 className="h-3 w-3 shrink-0 animate-spin text-primary" />
                            )}
                          </span>
                          <span className="mt-0.5 block truncate text-[10px] opacity-70">
                            {item.session.provider} ·{' '}
                            {relativeTime(item.session.updatedAt)} ·{' '}
                            {sessionStatusLabel(item.session.status)}
                          </span>
                        </button>
                        <button
                          onClick={() => void onRemoveSession(item.session)}
                          disabled={Boolean(state.activeTurnId) || Boolean(selectingKey)}
                          aria-label={`移除会话 ${item.session.title || item.session.id}`}
                          title="移除本地会话"
                          className="mr-1 hidden rounded-md p-1.5 text-slate-400 hover:bg-white hover:text-red-600 disabled:opacity-40 group-hover:block focus:block"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ) : (
                      <div
                        key={item.key}
                        className="group flex items-center gap-1 rounded-lg text-slate-600 transition-colors hover:bg-slate-50"
                      >
                        <button
                          onClick={() => void onSelectNativeSession(item.session)}
                          disabled={Boolean(state.activeTurnId) || Boolean(selectingKey)}
                          className="min-w-0 flex-1 rounded-lg px-2 py-2 text-left text-xs disabled:opacity-40"
                        >
                          <span className="flex items-center gap-1.5">
                            <span className="block min-w-0 flex-1 truncate font-medium">
                              {item.session.title || '未命名会话'}
                            </span>
                            {selectingKey === item.key && (
                              <Loader2 className="h-3 w-3 shrink-0 animate-spin text-primary" />
                            )}
                          </span>
                          <span className="mt-0.5 block truncate text-[10px] opacity-60">
                            {item.session.engine} · {item.session.message_count} 条消息 ·{' '}
                            {relativeTime(
                              item.session.ended_at || item.session.started_at,
                            )}
                          </span>
                        </button>
                        <Link
                          to={buildTimelineLink(item.session.engine, item.session.session_id, item.session.project_path)}
                          title="在时间线中查看"
                          aria-label="在时间线中查看"
                          className="mr-1 hidden rounded-md p-1.5 text-slate-400 hover:bg-white hover:text-primary group-hover:block focus:block"
                        >
                          <History className="h-3.5 w-3.5" />
                        </Link>
                      </div>
                    ),
                  )}
                </div>
              )}
            </div>
          );
        })}
        {recentSessions.length < filteredGatewaySessions.length && (
          <button
            onClick={() => onGatewayLimitChange(gatewaySessionLimit + PAGE_SIZE)}
            className="w-full rounded-lg px-2 py-1.5 text-center text-[11px] font-medium text-primary hover:bg-primary/5"
          >
            加载更多会话（
            {filteredGatewaySessions.length - recentSessions.length}）
          </button>
        )}
        {nativeSessionsLoading && (
          <p className="px-2 pt-1 text-xs text-slate-400">
            正在加载 {selectedCapabilities?.displayName || selectedProvider} 历史记录…
          </p>
        )}
        {!nativeSessionsLoading && nativeSessionsError && (
          <div
            className="mx-1 rounded-lg border border-red-100 bg-red-50 px-2 py-2 text-[11px] text-red-700"
            role="alert"
          >
            <p>
              {selectedCapabilities?.displayName || selectedProvider}:{' '}
              {nativeSessionsError}
            </p>
            <button
              onClick={onRetryNativeSessions}
              className="mt-1 flex items-center gap-1 font-semibold underline"
            >
              <RefreshCw className="h-3 w-3" /> 重试
            </button>
          </div>
        )}
        {!nativeSessionsLoading &&
          visibleNativeSessions.length < resumableNativeSessions.length && (
            <button
              onClick={() => onNativeLimitChange(nativeSessionLimit + PAGE_SIZE)}
              className="w-full rounded-lg px-2 py-1.5 text-center text-[11px] font-medium text-primary hover:bg-primary/5"
            >
              加载更多历史记录（
              {resumableNativeSessions.length - visibleNativeSessions.length}）
            </button>
          )}
        {!nativeSessionsLoading && unavailableSessionCount > 0 && (
          <>
            <div className="mt-2 flex items-center justify-between gap-2 border-t border-slate-100 px-2 pb-1 pt-3">
              <button
                onClick={() =>
                  onShowUnavailableHistoryChange(!showUnavailableHistory)
                }
                aria-expanded={unavailableHistoryExpanded}
                className="flex min-w-0 flex-1 items-center justify-between gap-2 text-left text-[10px] font-semibold uppercase tracking-wide text-slate-400 hover:text-slate-700"
              >
                <span className="truncate">
                  不可用工作区（{unavailableWorkspaceGroups.length}）
                </span>
                <ChevronDown
                  className={`h-3.5 w-3.5 shrink-0 transition-transform ${
                    unavailableHistoryExpanded ? 'rotate-180' : ''
                  }`}
                />
              </button>
              {/* With dozens of stale history paths, hiding one at a time is
                  its own chore -- offer the bulk form of the same action. */}
              {unavailableWorkspaceGroups.length > 1 && (
                <button
                  onClick={onHideAllUnavailable}
                  title="忽略此列表中的所有不可用工作区"
                  className="shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-semibold normal-case tracking-normal text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                >
                  全部隐藏
                </button>
              )}
            </div>
            {unavailableHistoryExpanded &&
              visibleUnavailableWorkspaceGroups.map(group => {
                const { latestSession, isHidden } = group;
                return (
                  <div
                    key={group.path}
                    title={group.path}
                    className="rounded-lg px-2 py-2 text-xs text-slate-500"
                  >
                    <span className="block truncate font-medium text-slate-600">
                      {workspaceLabel(group.path)}
                    </span>
                    <span className="mt-0.5 block truncate text-[10px] opacity-70">
                      {group.sessions.length} 个会话 ·{' '}
                      {latestSession.engine} · 上次活动 {relativeTime(
                        latestSession.ended_at || latestSession.started_at,
                      )}
                    </span>
                    <span className="mt-1 flex items-center gap-2">
                      <button
                        onClick={() => void onRegisterWorkspace(group.path)}
                        disabled={registeringWorkspace === group.path}
                        className="inline-flex items-center gap-1 text-[10px] font-semibold text-primary hover:underline disabled:opacity-50"
                      >
                        {registeringWorkspace === group.path ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <UserPlus className="h-3 w-3" />
                        )}
                        注册
                      </button>
                      {isHidden ? (
                        <button
                          onClick={() => onUnhideWorkspace(group.path)}
                          className="inline-flex items-center gap-1 text-[10px] font-semibold text-primary hover:underline"
                        >
                          <EyeOff className="h-3 w-3" /> 取消隐藏
                        </button>
                      ) : (
                        <button
                          onClick={() => onHideWorkspace(group.path)}
                          className="inline-flex items-center gap-1 text-[10px] font-semibold text-slate-400 hover:text-slate-700 hover:underline"
                        >
                          <EyeOff className="h-3 w-3" /> 隐藏
                        </button>
                      )}
                      <Link
                        to={buildTimelineLink(latestSession.engine, latestSession.session_id, latestSession.project_path)}
                        className="inline-block text-[10px] font-semibold text-primary hover:underline"
                      >
                        在时间线中查看
                      </Link>
                    </span>
                  </div>
                );
              })}
            {unavailableHistoryExpanded &&
              visibleUnavailableWorkspaceGroups.length <
                unavailableWorkspaceGroups.length && (
                <button
                  onClick={() =>
                    onUnavailableLimitChange(unavailableSessionLimit + PAGE_SIZE)
                  }
                  className="w-full rounded-lg px-2 py-1.5 text-center text-[11px] font-medium text-primary hover:bg-primary/5"
                >
                  加载更多不可用项（
                  {unavailableWorkspaceGroups.length -
                    visibleUnavailableWorkspaceGroups.length}）
                </button>
              )}
            {unavailableHistoryExpanded && hiddenWorkspaceCount > 0 && (
              <button
                onClick={onToggleShowHiddenWorkspaces}
                className="w-full rounded-lg px-2 py-1.5 text-center text-[11px] font-medium text-slate-400 hover:bg-slate-50 hover:text-slate-700"
              >
                {showHiddenWorkspaces
                  ? '再次隐藏已忽略的工作区'
                  : `显示 ${hiddenWorkspaceCount} 个已隐藏的工作区`}
              </button>
            )}
          </>
        )}
      </div>
    </aside>
  );
}
