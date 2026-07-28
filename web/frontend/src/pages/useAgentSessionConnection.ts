import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import type { RefObject } from 'react';
import {
  agentEventsUrl,
  fetchAgentHistory,
  importAgentSession,
  resumeAgentSession,
  sendAgentCommand,
} from '../api/agent';
import { agentSessionReducer, initialAgentSessionState } from '../state/agentSessionReducer';
import { SESSION_PAGE_SIZE } from '../utils/agentWorkspaceHelpers';
import type { AgentEvent, AgentSession, ApprovalDecision, NativeAgentSession, PermissionMode } from '../types/agent';

export interface UseAgentSessionConnectionArgs {
  workspace: string;
  setWorkspace: (value: string) => void;
  selectedProvider: string;
  setSelectedProvider: (value: string) => void;
  permissionMode: PermissionMode;
  setPermissionMode: (value: PermissionMode) => void;
  validProjects: { path: string; group: string; available?: boolean }[];
  setCurrentGroup: (group: string) => void;
  removeNativeSession: (provider: string, sessionId: string) => void;
  addSession: (session: AgentSession) => void;
  setNativeSessionLimit: (value: number) => void;
  setUnavailableSessionLimit: (value: number) => void;
  setShowUnavailableHistory: (value: boolean) => void;
  setError: (message: string | null) => void;
  scrollRef: RefObject<HTMLDivElement | null>;
  composerRef: RefObject<HTMLTextAreaElement | null>;
  historyCursorRef: RefObject<number | null>;
  hasOlderHistoryRef: RefObject<boolean>;
  loadingOlderHistoryRef: RefObject<boolean>;
  loadOlderHistoryRef: RefObject<() => void>;
}

/**
 * Owns the active session's reducer state, the WebSocket connection
 * lifecycle, and history paging. Kept as one hook -- its refs
 * (stateRef/socketRef/historyCursorRef/...) are too tightly coupled across
 * connect/selectSession/loadOlderHistory to split further without just
 * multiplying cross-file ref-passing.
 */
export default function useAgentSessionConnection({
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
}: UseAgentSessionConnectionArgs) {
  const [state, dispatch] = useReducer(agentSessionReducer, initialAgentSessionState);
  const stateRef = useRef(state);
  const socketRef = useRef<WebSocket | null>(null);
  const selectionRequestRef = useRef(0);
  const intentionalClose = useRef(false);
  const [connecting, setConnecting] = useState(false);
  const [connected, setConnected] = useState(false);
  const [selectingKey, setSelectingKey] = useState<string | null>(null);
  const [loadingOlderMessages, setLoadingOlderMessages] = useState(false);
  const [hasOlderMessages, setHasOlderMessages] = useState(false);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(() => () => {
    intentionalClose.current = true;
    socketRef.current?.close();
  }, []);

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
  }, [setError]);

  const loadInitialHistory = useCallback(async (session: AgentSession, selectionId: number) => {
    const page = await fetchAgentHistory(session.id);
    if (selectionId !== selectionRequestRef.current) return null;
    dispatch({ type: 'reset', session });
    dispatch({ type: 'history.replace', events: page.events });
    historyCursorRef.current = page.oldestSequence;
    hasOlderHistoryRef.current = page.hasMore;
    setHasOlderMessages(page.hasMore);
    return page.latestSequence;
  }, [historyCursorRef, hasOlderHistoryRef]);

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
  }, [historyCursorRef, hasOlderHistoryRef, loadingOlderHistoryRef, scrollRef, setError]);

  useEffect(() => {
    loadOlderHistoryRef.current = () => { void loadOlderHistory(); };
  }, [loadOlderHistoryRef, loadOlderHistory]);

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
  }, [
    state.activeTurnId, workspace, selectedProvider, permissionMode, validProjects,
    setCurrentGroup, setWorkspace, setSelectedProvider, setPermissionMode,
    setNativeSessionLimit, setUnavailableSessionLimit, setShowUnavailableHistory,
    connect, loadInitialHistory, setError,
  ]);

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
      addSession(imported);
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
  }, [
    state.activeTurnId, workspace, selectedProvider, permissionMode, validProjects,
    setCurrentGroup, setWorkspace, setSelectedProvider, setPermissionMode,
    setNativeSessionLimit, setUnavailableSessionLimit, setShowUnavailableHistory,
    connect, loadInitialHistory, removeNativeSession, addSession, setError,
  ]);

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
    composerRef.current?.focus();
  }, [composerRef, historyCursorRef, hasOlderHistoryRef, setError]);

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
  }, [state.session, state.activeTurnId, setError]);

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
  }, [state.session, setError]);

  return {
    state,
    stateRef,
    socketRef,
    connecting,
    connected,
    selectingKey,
    hasOlderMessages,
    loadingOlderMessages,
    connect,
    selectSession,
    selectNativeSession,
    newSession,
    cancel,
    respondApproval,
  };
}
