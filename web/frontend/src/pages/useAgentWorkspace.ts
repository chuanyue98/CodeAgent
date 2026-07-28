import { useCallback, useRef, useState } from 'react';
import { useProject } from '../context/ProjectContext';
import type { ConversationListItem } from '../utils/agentWorkspaceHelpers';
import { SESSION_PAGE_SIZE } from '../utils/agentWorkspaceHelpers';
import type { AgentGatewayStatus, AgentSession, NativeAgentSession, ProviderCapabilities, ApprovalDecision, PermissionMode } from '../types/agent';
import type { AgentSessionState } from '../state/agentSessionReducer';
import useNativeAgentSessions from './useNativeAgentSessions';
import useAgentWorkspaceSessions from './useAgentWorkspaceSessions';
import type { UnavailableWorkspaceGroup } from './useAgentWorkspaceSessions';
import useAgentGatewayBootstrap from './useAgentGatewayBootstrap';
import useWorkspaceRegistration from './useWorkspaceRegistration';
import useAgentSessionConnection from './useAgentSessionConnection';
import useAgentMessageSend from './useAgentMessageSend';
import useSessionRemoval from './useSessionRemoval';
import useWorkspaceComposerUI from './useWorkspaceComposerUI';

export type UseAgentWorkspaceReturn = {
  currentGroup: string;
  validProjects: { path: string; group: string; available?: boolean }[];
  providers: ProviderCapabilities[];
  gatewayStatus: AgentGatewayStatus;
  nativeLoadingProviders: Set<string>;
  nativeSessionErrors: Record<string, string>;
  selectedProvider: string;
  sessionSearch: string;
  gatewaySessionLimit: number;
  nativeSessionLimit: number;
  unavailableSessionLimit: number;
  showUnavailableHistory: boolean;
  expandedWorkspaces: Set<string>;
  collapsedWorkspaces: Set<string>;
  workspace: string;
  state: AgentSessionState;
  loading: boolean;
  connecting: boolean;
  sending: boolean;
  connected: boolean;
  selectingKey: string | null;
  error: string | null;
  onDismissError: () => void;
  showActivity: boolean;
  input: string;
  permissionMode: PermissionMode;
  showScrollToBottom: boolean;
  loadingOlderMessages: boolean;
  hasOlderMessages: boolean;
  selectedCapabilities: ProviderCapabilities | undefined;
  noGatewayProvider: boolean;
  normalizedSessionSearch: string;
  filteredGatewaySessions: AgentSession[];
  recentSessions: AgentSession[];
  resumableNativeSessions: NativeAgentSession[];
  visibleNativeSessions: NativeAgentSession[];
  unavailableSessionCount: number;
  unavailableWorkspaceGroups: UnavailableWorkspaceGroup[];
  visibleUnavailableWorkspaceGroups: UnavailableWorkspaceGroup[];
  hiddenWorkspaceCount: number;
  showHiddenWorkspaces: boolean;
  onHideWorkspace: (path: string) => void;
  onUnhideWorkspace: (path: string) => void;
  onToggleShowHiddenWorkspaces: () => void;
  onRegisterWorkspace: (path: string) => Promise<void>;
  registeringWorkspace: string | null;
  workspaceConversations: { path: string; label: string; conversations: ConversationListItem[] }[];
  connectionLabel: string;
  canCompose: boolean;
  /** True only when `workspace` names a currently registered, reachable project. */
  workspaceIsUsable: boolean;
  composerPlaceholder: string;
  sessionResourceSnapshot: { skills?: string[]; prompts?: string[]; hooks?: string[]; plugins?: string[] } | undefined;
  sessionResourceGroup: string;
  resourceCount: number;
  onNewSession: () => void;
  onSelectSession: (session: AgentSession) => void;
  onSelectNativeSession: (native: NativeAgentSession) => void;
  onRemoveSession: (session: AgentSession) => void;
  pendingRemoveSession: AgentSession | null;
  onConfirmRemoveSession: () => void;
  onCancelRemoveSession: () => void;
  onSend: () => void;
  onCancel: () => void;
  onRespondApproval: (approvalId: string, decision: ApprovalDecision) => void;
  onConnect: (session: AgentSession, afterSequence?: number, reset?: boolean) => Promise<WebSocket>;
  onRetryNativeSessions: () => void;
  onSearchChange: (value: string) => void;
  onGatewayLimitChange: (value: number) => void;
  onNativeLimitChange: (value: number) => void;
  onUnavailableLimitChange: (value: number) => void;
  onToggleExpandedWorkspace: (path: string) => void;
  onToggleCollapsedWorkspace: (path: string) => void;
  onShowUnavailableHistoryChange: (value: boolean) => void;
  onWorkspaceChange: (value: string) => void;
  onProviderChange: (value: string) => void;
  onPermissionModeChange: (value: PermissionMode) => void;
  onShowActivityChange: (value: boolean) => void;
  onSetCurrentGroup: (group: string) => void;
  onInputChange: (value: string) => void;
  focusComposer: () => void;
  setScrollRef: (element: HTMLDivElement | null) => void;
  setComposerRef: (element: HTMLTextAreaElement | null) => void;
  onScroll: (event: React.UIEvent<HTMLDivElement>) => void;
  scrollToLatest: (behavior?: ScrollBehavior) => void;
};

/**
 * Thin orchestrator composing the sub-hooks below in dependency order:
 * gateway bootstrap -> session connection -> send/removal/composer-UI ->
 * registration. Returns the same flat shape AgentWorkspace.tsx consumes.
 */
export default function useAgentWorkspace(): UseAgentWorkspaceReturn {
  const {
    projects,
    currentGroup,
    setCurrentGroup,
    selectedWorkspace: workspace,
    setSelectedWorkspace: setWorkspace,
    refreshConfig,
  } = useProject();

  const [sessionSearch, setSessionSearch] = useState('');
  const [gatewaySessionLimit, setGatewaySessionLimit] = useState(SESSION_PAGE_SIZE);
  const [nativeSessionLimit, setNativeSessionLimit] = useState(SESSION_PAGE_SIZE);
  const [unavailableSessionLimit, setUnavailableSessionLimit] = useState(SESSION_PAGE_SIZE);
  const [showUnavailableHistory, setShowUnavailableHistory] = useState(false);
  const [permissionMode, setPermissionMode] = useState<PermissionMode>('workspace-write');
  const [showActivity, setShowActivity] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const onDismissError = useCallback(() => setError(null), []);

  // Shared across the connection + composer-UI hooks -- lifted here instead
  // of owned by either one, since onScroll (composer-UI) reads refs that
  // connect/loadOlderHistory (connection) writes.
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const historyCursorRef = useRef<number | null>(null);
  const hasOlderHistoryRef = useRef(false);
  const loadingOlderHistoryRef = useRef(false);
  const loadOlderHistoryRef = useRef<() => void>(() => {});

  const bootstrap = useAgentGatewayBootstrap({ setError });
  const { providers, gatewayStatus, sessions, selectedProvider, setSelectedProvider, loading, addSession, removeSession } = bootstrap;

  const {
    nativeSessionsByProvider,
    nativeLoadingProviders,
    nativeSessionErrors,
    loadNativeSessions,
    removeNativeSession,
  } = useNativeAgentSessions(providers, selectedProvider);

  const { registeringWorkspace, registerWorkspace } = useWorkspaceRegistration({ refreshConfig, setError });

  const {
    validProjects,
    normalizedSessionSearch,
    filteredGatewaySessions,
    recentSessions,
    resumableNativeSessions,
    unavailableSessionCount,
    visibleNativeSessions,
    unavailableWorkspaceGroups,
    visibleUnavailableWorkspaceGroups,
    hiddenWorkspaceCount,
    showHiddenWorkspaces,
    onHideWorkspace,
    onUnhideWorkspace,
    onToggleShowHiddenWorkspaces,
    workspaceConversations,
  } = useAgentWorkspaceSessions({
    projects,
    sessions,
    nativeSessionsByProvider,
    sessionSearch,
    gatewaySessionLimit,
    nativeSessionLimit,
    unavailableSessionLimit,
    workspace,
  });

  const connection = useAgentSessionConnection({
    workspace,
    setWorkspace,
    selectedProvider,
    setSelectedProvider,
    permissionMode,
    setPermissionMode,
    validProjects,
    setCurrentGroup,
    removeNativeSession,
    addSession,
    setNativeSessionLimit,
    setUnavailableSessionLimit,
    setShowUnavailableHistory,
    setError,
    scrollRef,
    composerRef,
    historyCursorRef,
    hasOlderHistoryRef,
    loadingOlderHistoryRef,
    loadOlderHistoryRef,
  });
  const {
    state, stateRef, socketRef, connecting, connected, selectingKey,
    hasOlderMessages, loadingOlderMessages,
    connect, selectSession, selectNativeSession, newSession, cancel, respondApproval,
  } = connection;

  const composerUI = useWorkspaceComposerUI({
    messages: state.messages,
    scrollRef,
    composerRef,
    hasOlderHistoryRef,
    loadingOlderHistoryRef,
    loadOlderHistoryRef,
  });
  const {
    showScrollToBottom, expandedWorkspaces, collapsedWorkspaces,
    focusComposer, setScrollRef, setComposerRef, onScroll, scrollToLatest,
    onToggleExpandedWorkspace, onToggleCollapsedWorkspace,
  } = composerUI;

  const removal = useSessionRemoval({
    activeTurnId: state.activeTurnId,
    currentSessionId: state.session?.id,
    removeSession,
    newSession,
    setError,
  });
  const { pendingRemoveSession, requestRemoveSession, cancelRemoveSession, confirmRemoveSession } = removal;

  const messageSend = useAgentMessageSend({
    workspace,
    selectedProvider,
    permissionMode,
    state,
    stateRef,
    connecting,
    connect,
    socketRef,
    addSession,
    composerRef,
    setError,
  });
  const { input, setInput, sending, send } = messageSend;

  const retryNativeSessions = useCallback(() => {
    if (selectedProvider) loadNativeSessions(selectedProvider, true);
  }, [loadNativeSessions, selectedProvider]);

  const selectedCapabilities = providers.find(provider => provider.providerId === selectedProvider);
  const availableProviders = providers.filter(provider => provider.available);
  const noGatewayProvider = !loading && gatewayStatus.enabled && availableProviders.length === 0;
  const connectionLabel = connecting
    ? 'Connecting'
    : connected
      ? 'Connected'
      : state.session
        ? 'Disconnected'
        : 'Ready to start';
  // The shared workspace is restored from localStorage, so it can name a
  // path that is no longer registered (or not registered yet, before
  // /api/projects resolves). Compose only against one that actually resolves,
  // otherwise the composer looks ready and the send fails server-side.
  const workspaceIsUsable = validProjects.some(project => project.path === workspace);
  const canCompose = Boolean(workspaceIsUsable && selectedProvider && selectedCapabilities?.available && !noGatewayProvider);
  const composerPlaceholder = !workspaceIsUsable
    ? 'Select a workspace to begin'
    : !selectedProvider
      ? 'Select a provider to begin'
      : noGatewayProvider
        ? 'No interactive provider is available'
        : `Message ${selectedCapabilities?.displayName || 'the agent'}… (Enter to send, Shift+Enter for newline)`;
  const sessionResourceSnapshot = state.session?.resourceSnapshot;
  const sessionResourceGroup = sessionResourceSnapshot?.group || 'Unknown';
  const resourceCount = (sessionResourceSnapshot?.skills?.length ?? 0)
    + (sessionResourceSnapshot?.prompts?.length ?? 0)
    + (sessionResourceSnapshot?.hooks?.length ?? 0)
    + (sessionResourceSnapshot?.plugins?.length ?? 0);

  return {
    currentGroup,
    validProjects,
    providers,
    gatewayStatus,
    nativeLoadingProviders,
    nativeSessionErrors,
    selectedProvider,
    sessionSearch,
    gatewaySessionLimit,
    nativeSessionLimit,
    unavailableSessionLimit,
    showUnavailableHistory,
    expandedWorkspaces,
    collapsedWorkspaces,
    workspace,
    state,
    loading,
    connecting,
    sending,
    connected,
    selectingKey,
    error,
    onDismissError,
    showActivity,
    input,
    permissionMode,
    showScrollToBottom,
    loadingOlderMessages,
    hasOlderMessages,
    selectedCapabilities,
    noGatewayProvider,
    normalizedSessionSearch,
    filteredGatewaySessions,
    recentSessions,
    resumableNativeSessions,
    visibleNativeSessions,
    unavailableSessionCount,
    unavailableWorkspaceGroups,
    visibleUnavailableWorkspaceGroups,
    hiddenWorkspaceCount,
    showHiddenWorkspaces,
    onHideWorkspace,
    onUnhideWorkspace,
    onToggleShowHiddenWorkspaces,
    onRegisterWorkspace: registerWorkspace,
    registeringWorkspace,
    workspaceConversations,
    connectionLabel,
    canCompose,
    workspaceIsUsable,
    composerPlaceholder,
    sessionResourceSnapshot,
    sessionResourceGroup,
    resourceCount,
    onNewSession: newSession,
    onSelectSession: selectSession,
    onSelectNativeSession: selectNativeSession,
    onRemoveSession: requestRemoveSession,
    pendingRemoveSession,
    onConfirmRemoveSession: () => void confirmRemoveSession(),
    onCancelRemoveSession: cancelRemoveSession,
    onSend: send,
    onCancel: cancel,
    onRespondApproval: respondApproval,
    onConnect: connect,
    onRetryNativeSessions: retryNativeSessions,
    onSearchChange: setSessionSearch,
    onGatewayLimitChange: setGatewaySessionLimit,
    onNativeLimitChange: setNativeSessionLimit,
    onUnavailableLimitChange: setUnavailableSessionLimit,
    onToggleExpandedWorkspace,
    onToggleCollapsedWorkspace,
    onShowUnavailableHistoryChange: setShowUnavailableHistory,
    onWorkspaceChange: setWorkspace,
    onProviderChange: setSelectedProvider,
    onPermissionModeChange: setPermissionMode,
    onShowActivityChange: setShowActivity,
    onSetCurrentGroup: setCurrentGroup,
    onInputChange: setInput,
    focusComposer,
    setScrollRef,
    setComposerRef,
    onScroll,
    scrollToLatest,
  };
}
