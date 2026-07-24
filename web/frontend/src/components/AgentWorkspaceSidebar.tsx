import {
  ChevronDown,
  ChevronRight,
  FolderGit2,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Trash2,
} from 'lucide-react';
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
  unavailableNativeSessions: NativeAgentSession[];
  visibleNativeSessions: NativeAgentSession[];
  visibleUnavailableSessions: NativeAgentSession[];
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
  onRegisterAndResumeNativeSession: (native: NativeAgentSession) => void;
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
  unavailableNativeSessions,
  visibleNativeSessions,
  visibleUnavailableSessions,
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
  onRegisterAndResumeNativeSession,
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
    <aside className="glass-card flex w-60 shrink-0 flex-col p-3">
      <div className="mb-3 flex items-center justify-between border-b border-slate-100 pb-3">
        <span className="flex items-center gap-2 text-sm font-semibold text-slate-700">
          <Search className="h-4 w-4" /> Conversations
        </span>
        <button
          onClick={onNewSession}
          disabled={Boolean(state.activeTurnId)}
          className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs font-semibold text-primary hover:bg-primary/10 disabled:opacity-40"
        >
          <Plus className="h-3.5 w-3.5" /> New
        </button>
      </div>
      <label className="relative mb-2 block">
        <span className="sr-only">Search conversations</span>
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
          placeholder="Search conversations"
          className="w-full rounded-lg border border-slate-200 bg-white py-2 pl-8 pr-2 text-xs outline-none focus:border-primary"
        />
      </label>
      <div className="custom-scrollbar min-h-0 flex-1 space-y-1 overflow-y-auto">
        {loading && (
          <p className="px-2 text-xs text-slate-400">Loading sessions…</p>
        )}
        <p className="px-2 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
          Workspaces
        </p>
        {!loading && workspaceConversations.length === 0 && (
          <p className="px-2 text-xs italic text-slate-400">
            {normalizedSessionSearch
              ? 'No conversations match.'
              : 'No conversations in registered workspaces yet'}
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
                      No conversations yet
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
                              {item.session.title || 'Untitled conversation'}
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
                          aria-label={`Remove conversation ${item.session.title || item.session.id}`}
                          title="Remove local conversation"
                          className="mr-1 hidden rounded-md p-1.5 text-slate-400 hover:bg-white hover:text-red-600 disabled:opacity-40 group-hover:block focus:block"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ) : (
                      <button
                        key={item.key}
                        onClick={() => void onSelectNativeSession(item.session)}
                        disabled={Boolean(state.activeTurnId) || Boolean(selectingKey)}
                        className="w-full rounded-lg px-2 py-2 text-left text-xs text-slate-600 transition-colors hover:bg-slate-50 disabled:opacity-40"
                      >
                        <span className="flex items-center gap-1.5">
                          <span className="block min-w-0 flex-1 truncate font-medium">
                            {item.session.title || 'Untitled conversation'}
                          </span>
                          {selectingKey === item.key && (
                            <Loader2 className="h-3 w-3 shrink-0 animate-spin text-primary" />
                          )}
                        </span>
                        <span className="mt-0.5 block truncate text-[10px] opacity-60">
                          {item.session.engine} · {item.session.message_count} msgs ·{' '}
                          {relativeTime(
                            item.session.ended_at || item.session.started_at,
                          )}
                        </span>
                      </button>
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
            Load more conversations (
            {filteredGatewaySessions.length - recentSessions.length})
          </button>
        )}
        {nativeSessionsLoading && (
          <p className="px-2 pt-1 text-xs text-slate-400">
            Loading {selectedCapabilities?.displayName || selectedProvider} history…
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
              <RefreshCw className="h-3 w-3" /> Retry
            </button>
          </div>
        )}
        {!nativeSessionsLoading &&
          visibleNativeSessions.length < resumableNativeSessions.length && (
            <button
              onClick={() => onNativeLimitChange(nativeSessionLimit + PAGE_SIZE)}
              className="w-full rounded-lg px-2 py-1.5 text-center text-[11px] font-medium text-primary hover:bg-primary/5"
            >
              Load more history (
              {resumableNativeSessions.length - visibleNativeSessions.length})
            </button>
          )}
        {!nativeSessionsLoading && unavailableNativeSessions.length > 0 && (
          <>
            <button
              onClick={() =>
                onShowUnavailableHistoryChange(!showUnavailableHistory)
              }
              aria-expanded={unavailableHistoryExpanded}
              className="mt-2 flex w-full items-center justify-between border-t border-slate-100 px-2 pb-1 pt-3 text-left text-[10px] font-semibold uppercase tracking-wide text-slate-400 hover:text-slate-700"
            >
              <span>
                Unavailable workspaces ({unavailableNativeSessions.length})
              </span>
              <ChevronDown
                className={`h-3.5 w-3.5 transition-transform ${
                  unavailableHistoryExpanded ? 'rotate-180' : ''
                }`}
              />
            </button>
            {unavailableHistoryExpanded &&
              visibleUnavailableSessions.map(session => {
                const key = `${session.engine}:${session.session_id}`;
                return (
                  <div
                    key={key}
                    title={session.project_path}
                    className="rounded-lg px-2 py-2 text-xs text-slate-500"
                  >
                    <span className="block truncate">
                      {session.title || 'Untitled conversation'}
                    </span>
                    <span className="mt-0.5 block truncate text-[10px] opacity-70">
                      {session.engine} · {workspaceLabel(session.project_path)} ·{' '}
                      {session.message_count} msgs ·{' '}
                      {relativeTime(
                        session.ended_at || session.started_at,
                      )}
                    </span>
                    <button
                      onClick={() => void onRegisterAndResumeNativeSession(session)}
                      disabled={Boolean(state.activeTurnId) || Boolean(selectingKey)}
                      className="mt-1 flex items-center gap-1 text-[10px] font-semibold text-primary hover:underline disabled:opacity-40"
                    >
                      Register &amp; resume
                      {selectingKey === key && (
                        <Loader2 className="h-3 w-3 shrink-0 animate-spin" />
                      )}
                    </button>
                  </div>
                );
              })}
            {unavailableHistoryExpanded &&
              visibleUnavailableSessions.length <
                unavailableNativeSessions.length && (
                <button
                  onClick={() =>
                    onUnavailableLimitChange(unavailableSessionLimit + PAGE_SIZE)
                  }
                  className="w-full rounded-lg px-2 py-1.5 text-center text-[11px] font-medium text-primary hover:bg-primary/5"
                >
                  Load more unavailable (
                  {unavailableNativeSessions.length -
                    visibleUnavailableSessions.length})
                </button>
              )}
          </>
        )}
      </div>
    </aside>
  );
}
