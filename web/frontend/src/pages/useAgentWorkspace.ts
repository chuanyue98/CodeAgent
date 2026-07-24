import { useCallback, useEffect, useRef, useState, useReducer } from 'react';
import { useProject } from '../context/ProjectContext';
import {
  createAgentSession,
  deleteAgentSession,
  fetchAgentGatewayStatus,
  fetchAgentProviders,
  fetchAgentHistory,
  fetchAgentSessions,
  importAgentSession,
  resumeAgentSession,
  sendAgentCommand,
  agentEventsUrl,
} from '../api/agent';
import { agentSessionReducer } from '../state/agentSessionReducer';
import { SESSION_PAGE_SIZE } from '../utils/agentWorkspaceHelpers';
import type { ConversationListItem } from '../utils/agentWorkspaceHelpers';
import type { AgentEvent, AgentGatewayStatus, AgentSession, NativeAgentSession, ProviderCapabilities, ApprovalDecision, PermissionMode } from '../types/agent';
import { initialAgentSessionState } from '../state/agentSessionReducer';
import useNativeAgentSessions from './useNativeAgentSessions';
import useAgentWorkspaceSessions from './useAgentWorkspaceSessions';

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
  state: ReturnType<typeof agentSessionReducer>;
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
  unavailableNativeSessions: NativeAgentSession[];
  visibleNativeSessions: NativeAgentSession[];
  visibleUnavailableSessions: NativeAgentSession[];
  workspaceConversations: { path: string; label: string; conversations: ConversationListItem[] }[];
  connectionLabel: string;
  canCompose: boolean;
  composerPlaceholder: string;
  sessionResourceSnapshot: { skills?: string[]; prompts?: string[]; hooks?: string[]; plugins?: string[] } | undefined;
  sessionResourceGroup: string;
  resourceCount: number;
  onNewSession: () => void;
  onSelectSession: (session: AgentSession) => void;
  onSelectNativeSession: (native: NativeAgentSession) => void;
  onRegisterAndResumeNativeSession: (native: NativeAgentSession) => void;
  onRemoveSession: (session: AgentSession) => void;
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

export default function useAgentWorkspace(): UseAgentWorkspaceReturn {
  const { projects, currentGroup, setCurrentGroup, config, updateConfig } = useProject();
  const [providers, setProviders] = useState<ProviderCapabilities[]>([]);
  const [gatewayStatus, setGatewayStatus] = useState<AgentGatewayStatus>({
    enabled: true,
    legacyFallback: false,
    providers: {},
  });
  const [sessions, setSessions] = useState<AgentSession[]>([]);
  const [selectedProvider, setSelectedProvider] = useState('');
  const [sessionSearch, setSessionSearch] = useState('');
  const [gatewaySessionLimit, setGatewaySessionLimit] = useState(SESSION_PAGE_SIZE);
  const [nativeSessionLimit, setNativeSessionLimit] = useState(SESSION_PAGE_SIZE);
  const [unavailableSessionLimit, setUnavailableSessionLimit] = useState(SESSION_PAGE_SIZE);
  const [showUnavailableHistory, setShowUnavailableHistory] = useState(false);
  const [expandedWorkspaces, setExpandedWorkspaces] = useState<Set<string>>(new Set());
  const [collapsedWorkspaces, setCollapsedWorkspaces] = useState<Set<string>>(new Set());
  const [workspace, setWorkspace] = useState('');
  const [permissionMode, setPermissionMode] = useState<PermissionMode>('workspace-write');
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [sending, setSending] = useState(false);
  const [connected, setConnected] = useState(false);
  const [selectingKey, setSelectingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showActivity, setShowActivity] = useState(false);
  const [input, setInput] = useState('');
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const [state, dispatch] = useReducer(agentSessionReducer, initialAgentSessionState);
  const stateRef = useRef(state);
  const socketRef = useRef<WebSocket | null>(null);
  const selectionRequestRef = useRef(0);
  const intentionalClose = useRef(false);
  const sendingRef = useRef(false);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const historyCursorRef = useRef<number | null>(null);
  const hasOlderHistoryRef = useRef(false);
  const loadingOlderHistoryRef = useRef(false);
  const loadOlderHistoryRef = useRef<() => void>(() => {});
  const [loadingOlderMessages, setLoadingOlderMessages] = useState(false);
  const [hasOlderMessages, setHasOlderMessages] = useState(false);
  const {
    nativeSessionsByProvider,
    nativeLoadingProviders,
    nativeSessionErrors,
    loadNativeSessions,
    removeNativeSession,
  } = useNativeAgentSessions(providers, selectedProvider);

  const focusComposer = useCallback(() => {
    composerRef.current?.focus();
  }, []);

  const setScrollRef = useCallback((element: HTMLDivElement | null) => {
    scrollRef.current = element;
  }, []);

  const setComposerRef = useCallback((element: HTMLTextAreaElement | null) => {
    composerRef.current = element;
  }, []);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const status = await fetchAgentGatewayStatus();
      const [providerList, sessionList] = status.enabled
        ? await Promise.all([fetchAgentProviders(), fetchAgentSessions()])
        : [[], []];
      setGatewayStatus(status);
      setProviders(providerList);
      setSessions(sessionList);
      setSelectedProvider(previous =>
        previous || providerList.find(provider => provider.available)?.providerId || '',
      );
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to load Agent Gateway');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
  }, [refresh]);

  const {
    validProjects,
    normalizedSessionSearch,
    filteredGatewaySessions,
    recentSessions,
    resumableNativeSessions,
    unavailableNativeSessions,
    visibleNativeSessions,
    visibleUnavailableSessions,
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

  useEffect(() => {
    if (!state.session && !validProjects.some(project => project.path === workspace)) {
      const [project] = validProjects;
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setWorkspace(project?.path || '');
      if (project) setCurrentGroup(project.group);
    }
  }, [setCurrentGroup, state.session, validProjects, workspace]);

  useEffect(() => () => {
    intentionalClose.current = true;
    socketRef.current?.close();
  }, []);

  const scrollToLatest = useCallback((behavior: ScrollBehavior = 'smooth') => {
    const element = scrollRef.current;
    if (!element) return;
    element.scrollTo({ top: element.scrollHeight, behavior });
    setShowScrollToBottom(false);
  }, []);

  const onScroll = useCallback((event: React.UIEvent<HTMLDivElement>) => {
    const element = event.currentTarget;
    const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
    setShowScrollToBottom(distanceFromBottom > 120);
    if (element.scrollTop < 120 && hasOlderHistoryRef.current && !loadingOlderHistoryRef.current) {
      loadOlderHistoryRef.current();
    }
  }, [setShowScrollToBottom]);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
    if (distanceFromBottom < 120) scrollToLatest();
  }, [scrollToLatest, state.messages]);

  const connect = useCallback((session: AgentSession, afterSequence = 0, reset = true) => {
    intentionalClose.current = true;
    if (socketRef.current) {
      // Clear every handler, not just onclose -- a frame the old socket
      // already has in flight can still fire onmessage/onerror after
      // close() returns, and those would otherwise dispatch into the
      // reducer state for whichever session is now current.
      socketRef.current.onopen = null;
      socketRef.current.onmessage = null;
      socketRef.current.onerror = null;
      socketRef.current.onclose = null;
      socketRef.current.close();
    }
    intentionalClose.current = false;
    if (reset) dispatch({ type: 'reset', session });
    setConnecting(true);
    setConnected(false);
    setError(null);

    return new Promise<WebSocket>((resolve, reject) => {
      const socket = new WebSocket(agentEventsUrl(session.id, afterSequence));
      socketRef.current = socket;
      const timer = window.setTimeout(() => {
        if (socket.readyState !== WebSocket.OPEN) {
          socket.close();
          reject(new Error('Agent connection timed out'));
        }
      }, 10_000);
      socket.onopen = () => {
        window.clearTimeout(timer);
        setConnecting(false);
        setConnected(true);
        resolve(socket);
      };
      socket.onmessage = event => {
        try {
          const message = JSON.parse(event.data) as AgentEvent | { type: 'ack' } | { type: 'error'; message: string };
          if (message.type === 'ack') return;
          if (message.type === 'error' && !('sequence' in message)) {
            setError(message.message);
            return;
          }
          dispatch({ type: 'event', event: message as AgentEvent });
        } catch {
          setError('Received an invalid Gateway event');
        }
      };
      socket.onerror = () => {
        setError('Agent connection failed');
        // A no-op if onopen already resolved -- only settles the promise
        // for a connection that failed before ever opening, instead of
        // leaving callers (e.g. selectSession's spinner) blocked on this
        // promise until the 10s timeout below fires with a stale message.
        reject(new Error('Agent connection failed'));
      };
      socket.onclose = () => {
        setConnecting(false);
        setConnected(false);
        if (!intentionalClose.current) {
          setError('Agent connection closed. Reconnect to continue from the last event.');
        }
        reject(new Error('Agent connection closed'));
      };
    });
  }, []);

  const loadInitialHistory = useCallback(async (session: AgentSession, selectionId: number) => {
    const page = await fetchAgentHistory(session.id);
    if (selectionId !== selectionRequestRef.current) return null;
    dispatch({ type: 'reset', session });
    dispatch({ type: 'history.replace', events: page.events });
    historyCursorRef.current = page.oldestSequence;
    hasOlderHistoryRef.current = page.hasMore;
    setHasOlderMessages(page.hasMore);
    return page.latestSequence;
  }, []);

  const loadOlderHistory = useCallback(async () => {
    const session = stateRef.current.session;
    const beforeSequence = historyCursorRef.current;
    if (!session || !beforeSequence || !hasOlderHistoryRef.current || loadingOlderHistoryRef.current) return;
    loadingOlderHistoryRef.current = true;
    setLoadingOlderMessages(true);
    try {
      const page = await fetchAgentHistory(session.id, beforeSequence);
      if (stateRef.current.session?.id !== session.id) return;
      const element = scrollRef.current;
      const previousHeight = element?.scrollHeight ?? 0;
      dispatch({ type: 'history.prepend', events: page.events });
      historyCursorRef.current = page.oldestSequence;
      hasOlderHistoryRef.current = page.hasMore;
      setHasOlderMessages(page.hasMore);
      // Prepending changes scrollHeight. Keep the oldest message that was
      // already visible at the same viewport position instead of jumping the
      // reader further up the conversation.
      requestAnimationFrame(() => {
        if (element) element.scrollTop += element.scrollHeight - previousHeight;
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to load earlier messages');
    } finally {
      loadingOlderHistoryRef.current = false;
      setLoadingOlderMessages(false);
    }
  }, []);

  useEffect(() => {
    loadOlderHistoryRef.current = () => { void loadOlderHistory(); };
  }, [loadOlderHistory]);

  const selectSession = useCallback(async (session: AgentSession) => {
    if (state.activeTurnId) return;
    const selectionId = ++selectionRequestRef.current;
    const previousSelection = { workspace, provider: selectedProvider, permissionMode };
    setSelectingKey(session.id);
    try {
      const resumed = await resumeAgentSession(session.id);
      if (selectionId !== selectionRequestRef.current) return;
      setWorkspace(resumed.projectId);
      setSelectedProvider(resumed.provider);
      setNativeSessionLimit(SESSION_PAGE_SIZE);
      setUnavailableSessionLimit(SESSION_PAGE_SIZE);
      setShowUnavailableHistory(false);
      setPermissionMode(resumed.permissionMode);
      const project = validProjects.find(item => item.path === resumed.projectId);
      if (project) setCurrentGroup(project.group);
      const latestSequence = await loadInitialHistory(resumed, selectionId);
      if (latestSequence === null || selectionId !== selectionRequestRef.current) return;
      await connect(resumed, latestSequence, false);
    } catch (caught) {
      if (selectionId === selectionRequestRef.current) {
        setWorkspace(previousSelection.workspace);
        setSelectedProvider(previousSelection.provider);
        setPermissionMode(previousSelection.permissionMode);
        setError(caught instanceof Error ? caught.message : 'Failed to resume session');
      }
    } finally {
      if (selectionId === selectionRequestRef.current) setSelectingKey(null);
    }
  }, [state.activeTurnId, workspace, selectedProvider, permissionMode, validProjects, setCurrentGroup, connect, loadInitialHistory]);

  const resumeNativeSessionUnchecked = useCallback(async (native: NativeAgentSession) => {
    const selectionId = ++selectionRequestRef.current;
    const previousSelection = { workspace, provider: selectedProvider, permissionMode };
    setSelectingKey(`${native.engine}:${native.session_id}`);
    try {
      const imported = await importAgentSession({
        provider: native.engine,
        providerSessionId: native.session_id,
        projectId: native.project_path,
        permissionMode,
        title: native.title,
        model: native.model || undefined,
      });
      if (selectionId !== selectionRequestRef.current) return;
      setSessions(previous => [
        imported,
        ...previous.filter(session => session.id !== imported.id),
      ]);
      removeNativeSession(native.engine, native.session_id);
      setWorkspace(imported.projectId);
      setSelectedProvider(imported.provider);
      setNativeSessionLimit(SESSION_PAGE_SIZE);
      setUnavailableSessionLimit(SESSION_PAGE_SIZE);
      setShowUnavailableHistory(false);
      setPermissionMode(imported.permissionMode);
      const project = validProjects.find(item => item.path === imported.projectId);
      if (project) setCurrentGroup(project.group);
      const latestSequence = await loadInitialHistory(imported, selectionId);
      if (latestSequence === null || selectionId !== selectionRequestRef.current) return;
      await connect(imported, latestSequence, false);
    } catch (caught) {
      if (selectionId === selectionRequestRef.current) {
        setWorkspace(previousSelection.workspace);
        setSelectedProvider(previousSelection.provider);
        setPermissionMode(previousSelection.permissionMode);
        setError(
          caught instanceof Error
            ? caught.message
            : 'Failed to import provider session',
        );
      }
    } finally {
      if (selectionId === selectionRequestRef.current) setSelectingKey(null);
    }
  }, [workspace, selectedProvider, permissionMode, validProjects, setCurrentGroup, connect, loadInitialHistory, removeNativeSession]);

  const selectNativeSession = useCallback(async (native: NativeAgentSession) => {
    if (state.activeTurnId) return;
    const registered = validProjects.some(project => project.path === native.project_path);
    if (!registered) {
      setError(`Register this workspace before resuming: ${native.project_path}`);
      return;
    }
    await resumeNativeSessionUnchecked(native);
  }, [state.activeTurnId, validProjects, resumeNativeSessionUnchecked]);

  const registerAndResumeNativeSession = useCallback(async (native: NativeAgentSession) => {
    if (state.activeTurnId) return;
    setSelectingKey(`${native.engine}:${native.session_id}`);
    try {
      await updateConfig({
        ...(config || {}),
        project_registry: [
          ...(config?.project_registry || []),
          { path: native.project_path, group: currentGroup || 'common' },
        ],
      });
    } catch (caught) {
      setSelectingKey(null);
      setError(caught instanceof Error ? caught.message : 'Failed to register workspace');
      return;
    }
    await resumeNativeSessionUnchecked(native);
  }, [state.activeTurnId, config, currentGroup, updateConfig, resumeNativeSessionUnchecked]);

  const newSession = useCallback(() => {
    selectionRequestRef.current += 1;
    intentionalClose.current = true;
    if (socketRef.current) {
      socketRef.current.onopen = null;
      socketRef.current.onmessage = null;
      socketRef.current.onerror = null;
      socketRef.current.onclose = null;
      socketRef.current.close();
    }
    socketRef.current = null;
    setConnected(false);
    setError(null);
    dispatch({ type: 'reset' });
    historyCursorRef.current = null;
    hasOlderHistoryRef.current = false;
    setHasOlderMessages(false);
    focusComposer();
  }, [focusComposer]);

  const removeSession = useCallback(async (session: AgentSession) => {
    if (state.activeTurnId) return;
    if (!window.confirm('Remove this local conversation? Its provider history will remain available.')) return;
    try {
      await deleteAgentSession(session.id);
      setSessions(previous => previous.filter(item => item.id !== session.id));
      if (state.session?.id === session.id) newSession();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to remove conversation');
    }
  }, [state.activeTurnId, state.session, newSession]);

  const send = useCallback(async () => {
    const text = input.trim();
    // sendingRef guards the gap createAgentSession() awaits through, before
    // connect() ever sets `connecting` -- without it, a fast double-Enter
    // on a brand-new conversation races two createAgentSession calls and
    // ends up with two backend sessions for one message.
    if (!text || state.activeTurnId || connecting || sendingRef.current) return;
    if (!workspace || !selectedProvider) {
      setError('Select a registered workspace and an available provider');
      return;
    }
    sendingRef.current = true;
    setSending(true);
    setInput('');
    if (composerRef.current) composerRef.current.style.height = 'auto';
    try {
      let session = state.session;
      let socket = socketRef.current;
      if (!session) {
        session = await createAgentSession({
          provider: selectedProvider,
          projectId: workspace,
          permissionMode,
          title: text.slice(0, 80),
        });
        setSessions(previous => [session as AgentSession, ...previous]);
        socket = await connect(session, 0, true);
      } else if (!socket || socket.readyState !== WebSocket.OPEN) {
        socket = await connect(session, stateRef.current.lastSequence, false);
      }
      sendAgentCommand(socket, {
        type: 'turn.start',
        requestId: crypto.randomUUID(),
        sessionId: session.id,
        input: [{ type: 'text', text }],
      });
    } catch (caught) {
      setInput(text);
      setError(caught instanceof Error ? caught.message : 'Failed to start turn');
    } finally {
      sendingRef.current = false;
      setSending(false);
    }
  }, [input, state.activeTurnId, state.session, connecting, workspace, selectedProvider, permissionMode, connect]);

  const cancel = useCallback(() => {
    const socket = socketRef.current;
    if (!socket || !state.session || !state.activeTurnId) return;
    try {
      sendAgentCommand(socket, {
        type: 'turn.cancel',
        requestId: crypto.randomUUID(),
        sessionId: state.session.id,
        turnId: state.activeTurnId,
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to cancel turn');
    }
  }, [state.session, state.activeTurnId]);

  const respondApproval = useCallback((approvalId: string, decision: ApprovalDecision) => {
    const socket = socketRef.current;
    if (!socket || !state.session) return;
    try {
      sendAgentCommand(socket, {
        type: 'approval.respond',
        requestId: crypto.randomUUID(),
        sessionId: state.session.id,
        approvalId,
        decision,
      });
      dispatch({ type: 'approval.resolved', approvalId });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to respond to approval');
    }
  }, [state.session]);

  const retryNativeSessions = useCallback(() => {
    if (selectedProvider) loadNativeSessions(selectedProvider, true);
  }, [loadNativeSessions, selectedProvider]);

  const onDismissError = useCallback(() => setError(null), []);

  const onToggleExpandedWorkspace = useCallback((path: string) => {
    setExpandedWorkspaces(previous => {
      const next = new Set(previous);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }, []);

  const onToggleCollapsedWorkspace = useCallback((path: string) => {
    setCollapsedWorkspaces(previous => {
      const next = new Set(previous);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }, []);

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
  const canCompose = Boolean(workspace && selectedProvider && selectedCapabilities?.available && !noGatewayProvider);
  const composerPlaceholder = !workspace
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
    unavailableNativeSessions,
    visibleNativeSessions,
    visibleUnavailableSessions,
    workspaceConversations,
    connectionLabel,
    canCompose,
    composerPlaceholder,
    sessionResourceSnapshot,
    sessionResourceGroup,
    resourceCount,
    onNewSession: newSession,
    onSelectSession: selectSession,
    onSelectNativeSession: selectNativeSession,
    onRegisterAndResumeNativeSession: registerAndResumeNativeSession,
    onRemoveSession: removeSession,
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
