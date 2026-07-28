import { useCallback, useRef, useState } from 'react';
import type { RefObject } from 'react';
import { createAgentSession, sendAgentCommand } from '../api/agent';
import type { AgentSession, PermissionMode } from '../types/agent';
import type { AgentSessionState } from '../state/agentSessionReducer';

export interface UseAgentMessageSendArgs {
  workspace: string;
  selectedProvider: string;
  permissionMode: PermissionMode;
  state: AgentSessionState;
  stateRef: RefObject<AgentSessionState>;
  connecting: boolean;
  connect: (session: AgentSession, afterSequence?: number, reset?: boolean) => Promise<WebSocket>;
  socketRef: RefObject<WebSocket | null>;
  addSession: (session: AgentSession) => void;
  composerRef: RefObject<HTMLTextAreaElement | null>;
  setError: (message: string | null) => void;
}

/** Owns the composer's input state and the send-a-turn flow. */
export default function useAgentMessageSend({
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
}: UseAgentMessageSendArgs) {
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const sendingRef = useRef(false);

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
        addSession(session);
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
  }, [input, state.activeTurnId, state.session, connecting, workspace, selectedProvider, permissionMode, connect, socketRef, stateRef, addSession, composerRef, setError]);

  return { input, setInput, sending, send };
}
