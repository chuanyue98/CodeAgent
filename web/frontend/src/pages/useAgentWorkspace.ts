import { useCallback, useEffect, useMemo, useRef, useState, useReducer } from 'react';
import { useProject } from '../context/ProjectContext';
import {
  createAgentSession,
  deleteAgentSession,
  fetchAgentProviders,
  fetchAgentHistory,
  fetchAgentSessions,
  fetchNativeAgentSessions,
  importAgentSession,
  resumeAgentSession,
  sendAgentCommand,
  agentEventsUrl,
} from '../api/agent';
import { agentSessionReducer } from '../state/agentSessionReducer';
import type { ConversationListItem } from '../utils/agentWorkspaceHelpers';
import {
  deduplicateNativeSessions,
  SESSION_PAGE_SIZE,
  workspaceLabel,
} from '../utils/agentWorkspaceHelpers';
import type { AgentEvent, AgentSession, NativeAgentSession, ProviderCapabilities, ApprovalDecision, PermissionMode } from '../types/agent';
import { initialAgentSessionState } from '../state/agentSessionReducer';

export type UseAgentWorkspaceReturn = {
  projects: { path: string; group: string; available?: boolean }[];
  currentGroup: string;
  validProjects: { path: string; group: string; available?: boolean }[];
  validProjectPaths: Set<string>;
  providers: ProviderCapabilities[];
  sessions: AgentSession[];
  nativeSessionsByProvider: Record<string, NativeAgentSession[]>;
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
  connected: boolean;
  selectingKey: string | null;
  error: string | null;
  onDismissError: () => void;
  showActivity: boolean;
  legacyMode: boolean;
  input: string;
  permissionMode: PermissionMode;
  showScrollToBottom: boolean;
  loadingOlderMessages: boolean;
  hasOlderMessages: boolean;
  selectedCapabilities: ProviderCapabilities | undefined;
  availableProviders: ProviderCapabilities[];
  noGatewayProvider: boolean;
  nativeSessionsLoading: boolean;
  nativeSessionsError: string | null;
  allNativeSessions: NativeAgentSession[];
  normalizedSessionSearch: string;
  filteredGatewaySessions: AgentSession[];
  recentSessions: AgentSession[];
  mappedProviderSessions: Set<string>;
  filteredNativeSessions: NativeAgentSession[];
  resumableNativeSessions: NativeAgentSession[];
  unavailableNativeSessions: NativeAgentSession[];
  visibleNativeSessions: NativeAgentSession[];
  visibleUnavailableSessions: NativeAgentSession[];
  workspaceConversations: { path: string; label: string; conversations: ConversationListItem[] }[];
  unavailableHistoryExpanded: boolean;
  connectionLabel: string;
  canCompose: boolean;
  composerPlaceholder: string;
  sessionResourceSnapshot: { skills?: string[]; prompts?: string[]; hooks?: string[]; plugins?: string[] } | undefined;
  sessionResourceGroup: string;
  resourceCount: number;
  onNewSession: () => void;
  onSelectSession: (session: AgentSession) => void;
  onSelectNativeSession: (native: NativeAgentSession) => void;
  onRemoveSession: (session: AgentSession) => void;
  onSend: () => void;
  onCancel: () => void;
  onRespondApproval: (approvalId: string, decision: ApprovalDecision) => void;
  onConnect: (session: AgentSession, afterSequence?: number, reset?: boolean) => Promise<WebSocket>;
  onRefresh: () => Promise<void>;
  onLoadNativeSessions: (provider: string, force?: boolean) => void;
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
  onSetLegacyMode: () => void;
  onSetCurrentGroup: (group: string) => void;
  onInputChange: (value: string) => void;
  focusComposer: () => void;
  setScrollRef: (element: HTMLDivElement | null) => void;
  setComposerRef: (element: HTMLTextAreaElement | null) => void;
  onScroll: (event: React.UIEvent<HTMLDivElement>) => void;
  scrollToLatest: (behavior?: ScrollBehavior) => void;
};

export default function useAgentWorkspace(): UseAgentWorkspaceReturn {
  const { projects, currentGroup, setCurrentGroup } = useProject();
  const [providers, setProviders] = useState<ProviderCapabilities[]>([]);
  const [sessions, setSessions] = useState<AgentSession[]>([]);
  const [nativeSessionsByProvider, setNativeSessionsByProvider] = useState<Record<string, NativeAgentSession[]>>({});
  const [nativeLoadingProviders, setNativeLoadingProviders] = useState<Set<string>>(new Set());
  const [nativeSessionErrors, setNativeSessionErrors] = useState<Record<string, string>>({});
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
  const [connected, setConnected] = useState(false);
  const [selectingKey, setSelectingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showActivity, setShowActivity] = useState(false);
  const [legacyMode, setLegacyMode] = useState(false);
  const [input, setInput] = useState('');
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const [state, dispatch] = useReducer(agentSessionReducer, initialAgentSessionState);
  const stateRef = useRef(state);
  const socketRef = useRef<WebSocket | null>(null);
  const nativeSessionsCacheRef = useRef<Map<string, NativeAgentSession[]>>(new Map());
  const nativeSessionsRequestRef = useRef<Map<string, Promise<NativeAgentSession[]>>>(new Map());
  const selectionRequestRef = useRef(0);
  const intentionalClose = useRef(false);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const historyCursorRef = useRef<number | null>(null);
  const hasOlderHistoryRef = useRef(false);
  const loadingOlderHistoryRef = useRef(false);
  const loadOlderHistoryRef = useRef<() => void>(() => {});
  const [loadingOlderMessages, setLoadingOlderMessages] = useState(false);
  const [hasOlderMessages, setHasOlderMessages] = useState(false);

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
      const [providerList, sessionList] = await Promise.all([
        fetchAgentProviders(),
        fetchAgentSessions(),
      ]);
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

  const loadNativeSessions = useCallback(async (provider: string, force = false) => {
    if (!provider) return;
    if (force) nativeSessionsCacheRef.current.delete(provider);
    const cached = nativeSessionsCacheRef.current.get(provider);
    if (cached) {
      setNativeSessionsByProvider(previous => ({ ...previous, [provider]: cached }));
      return;
    }
    setNativeLoadingProviders(previous => new Set(previous).add(provider));
    setNativeSessionErrors(previous => {
      const next = { ...previous };
      delete next[provider];
      return next;
    });
    let request = nativeSessionsRequestRef.current.get(provider);
    if (!request) {
      request = fetchNativeAgentSessions(provider)
        .then(result => {
          nativeSessionsCacheRef.current.set(provider, result);
          return result;
        })
        .finally(() => nativeSessionsRequestRef.current.delete(provider));
      nativeSessionsRequestRef.current.set(provider, request);
    }
    try {
      const result = await request;
      setNativeSessionsByProvider(previous => ({ ...previous, [provider]: result }));
    } catch {
      setNativeSessionErrors(previous => ({
        ...previous,
        [provider]: 'Provider history could not be loaded.',
      }));
    } finally {
      setNativeLoadingProviders(previous => {
        const next = new Set(previous);
        next.delete(provider);
        return next;
      });
    }
  }, []);

  useEffect(() => {
    if (selectedProvider) void loadNativeSessions(selectedProvider);
  }, [loadNativeSessions, selectedProvider]);

  useEffect(() => {
    providers.filter(provider => provider.available).forEach(provider => {
      void loadNativeSessions(provider.providerId);
    });
  }, [loadNativeSessions, providers]);

  const validProjects = useMemo(
    () => projects.filter(project => project.path.trim() && project.available !== false),
    [projects],
  );
  const validProjectPaths = useMemo(
    () => new Set(validProjects.map(project => project.path)),
    [validProjects],
  );

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
      socket.onopen = () => {
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
      };
      socket.onclose = () => {
        setConnecting(false);
        setConnected(false);
        if (!intentionalClose.current) {
          setError('Agent connection closed. Reconnect to continue from the last event.');
        }
      };
      const timer = window.setTimeout(() => {
        if (socket.readyState !== WebSocket.OPEN) {
          socket.close();
          reject(new Error('Agent connection timed out'));
        }
      }, 10_000);
      socket.addEventListener('open', () => window.clearTimeout(timer), { once: true });
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

  const selectNativeSession = useCallback(async (native: NativeAgentSession) => {
    if (state.activeTurnId) return;
    const registered = validProjects.some(project => project.path === native.project_path);
    if (!registered) {
      setError(`Register this workspace before resuming: ${native.project_path}`);
      return;
    }
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
      setNativeSessionsByProvider(previous => {
        const providerSessions = previous[native.engine] || [];
        const next = providerSessions.filter(
          session =>
            !(session.engine === native.engine && session.session_id === native.session_id),
        );
        nativeSessionsCacheRef.current.set(native.engine, next);
        return { ...previous, [native.engine]: next };
      });
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
  }, [state.activeTurnId, workspace, selectedProvider, permissionMode, validProjects, setCurrentGroup, connect, loadInitialHistory]);

  const newSession = useCallback(() => {
    selectionRequestRef.current += 1;
    intentionalClose.current = true;
    socketRef.current?.close();
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
    if (!text || state.activeTurnId || connecting) return;
    if (!workspace || !selectedProvider) {
      setError('Select a registered workspace and an available provider');
      return;
    }
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
  const noGatewayProvider = !loading && availableProviders.length === 0;
  const nativeSessionsLoading = nativeLoadingProviders.has(selectedProvider);
  const nativeSessionsError = nativeSessionErrors[selectedProvider] || null;
  const allNativeSessions = deduplicateNativeSessions(
    Object.values(nativeSessionsByProvider).flat(),
  );
  const normalizedSessionSearch = sessionSearch.trim().toLocaleLowerCase();
  const filteredGatewaySessions = useMemo(
    () => sessions.filter(session => !normalizedSessionSearch || [
      session.title,
      session.provider,
      session.cwd,
      session.model,
      session.status,
    ].some(value => value?.toLocaleLowerCase().includes(normalizedSessionSearch))),
    [normalizedSessionSearch, sessions],
  );
  const recentSessions = useMemo(
    () => filteredGatewaySessions.slice(0, gatewaySessionLimit),
    [filteredGatewaySessions, gatewaySessionLimit],
  );
  const mappedProviderSessions = useMemo(
    () => new Set(sessions.map(session => `${session.provider}:${session.providerSessionId}`)),
    [sessions],
  );
  const filteredNativeSessions = useMemo(
    () => allNativeSessions
      .filter(session => !mappedProviderSessions.has(`${session.engine}:${session.session_id}`))
      .filter(session => !normalizedSessionSearch || [
        session.title,
        session.engine,
        session.project_path,
        session.model,
      ].some(value => value?.toLocaleLowerCase().includes(normalizedSessionSearch))),
    [allNativeSessions, mappedProviderSessions, normalizedSessionSearch],
  );
  const resumableNativeSessions = useMemo(
    () => filteredNativeSessions.filter(session => validProjectPaths.has(session.project_path)),
    [filteredNativeSessions, validProjectPaths],
  );
  const unavailableNativeSessions = useMemo(
    () => filteredNativeSessions.filter(session => !validProjectPaths.has(session.project_path)),
    [filteredNativeSessions, validProjectPaths],
  );
  const visibleNativeSessions = useMemo(
    () => resumableNativeSessions.slice(0, nativeSessionLimit),
    [resumableNativeSessions, nativeSessionLimit],
  );
  const visibleUnavailableSessions = useMemo(
    () => unavailableNativeSessions.slice(0, unavailableSessionLimit),
    [unavailableNativeSessions, unavailableSessionLimit],
  );
  const workspaceConversations = useMemo(() => {
    const byWorkspace = new Map<string, ConversationListItem[]>(
      validProjects.map(project => [project.path, []]),
    );
    recentSessions.forEach(session => {
      const items = byWorkspace.get(session.projectId);
      if (!items) return;
      items.push({
        source: 'gateway',
        key: session.id,
        projectPath: session.projectId,
        updatedAt: session.updatedAt,
        session,
      });
    });
    visibleNativeSessions.forEach(session => {
      const items = byWorkspace.get(session.project_path);
      if (!items) return;
      items.push({
        source: 'native',
        key: `${session.engine}:${session.session_id}`,
        projectPath: session.project_path,
        updatedAt: session.ended_at || session.started_at,
        session,
      });
    });
    return validProjects
      .map(project => ({
        path: project.path,
        label: workspaceLabel(project.path),
        conversations: (byWorkspace.get(project.path) || []).sort(
          (left, right) => right.updatedAt.localeCompare(left.updatedAt),
        ),
      }))
      .filter(group => group.conversations.length > 0 || !normalizedSessionSearch)
      .sort((left, right) => {
        if (left.path === workspace) return -1;
        if (right.path === workspace) return 1;
        return left.label.localeCompare(right.label);
      });
  }, [normalizedSessionSearch, recentSessions, validProjects, visibleNativeSessions, workspace]);
  const unavailableHistoryExpanded = showUnavailableHistory || Boolean(normalizedSessionSearch);
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
    projects,
    currentGroup,
    validProjects,
    validProjectPaths,
    providers,
    sessions,
    nativeSessionsByProvider,
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
    connected,
    selectingKey,
    error,
    onDismissError,
    showActivity,
    legacyMode,
    input,
    permissionMode,
    showScrollToBottom,
    loadingOlderMessages,
    hasOlderMessages,
    selectedCapabilities,
    availableProviders,
    noGatewayProvider,
    nativeSessionsLoading,
    nativeSessionsError,
    allNativeSessions,
    normalizedSessionSearch,
    filteredGatewaySessions,
    recentSessions,
    mappedProviderSessions,
    filteredNativeSessions,
    resumableNativeSessions,
    unavailableNativeSessions,
    visibleNativeSessions,
    visibleUnavailableSessions,
    workspaceConversations,
    unavailableHistoryExpanded,
    connectionLabel,
    canCompose,
    composerPlaceholder,
    sessionResourceSnapshot,
    sessionResourceGroup,
    resourceCount,
    onNewSession: newSession,
    onSelectSession: selectSession,
    onSelectNativeSession: selectNativeSession,
    onRemoveSession: removeSession,
    onSend: send,
    onCancel: cancel,
    onRespondApproval: respondApproval,
    onConnect: connect,
    onRefresh: refresh,
    onLoadNativeSessions: loadNativeSessions,
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
    onSetLegacyMode: () => setLegacyMode(true),
    onSetCurrentGroup: setCurrentGroup,
    onInputChange: setInput,
    focusComposer,
    setScrollRef,
    setComposerRef,
    onScroll,
    scrollToLatest,
  };
}
