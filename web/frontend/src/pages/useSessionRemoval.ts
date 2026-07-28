import { useCallback, useState } from 'react';
import { deleteAgentSession } from '../api/agent';
import type { AgentSession } from '../types/agent';

export interface UseSessionRemovalArgs {
  activeTurnId: string | null;
  currentSessionId: string | undefined;
  removeSession: (id: string) => void;
  newSession: () => void;
  setError: (message: string | null) => void;
}

/** Owns the "confirm and remove a conversation" flow. */
export default function useSessionRemoval({
  activeTurnId,
  currentSessionId,
  removeSession,
  newSession,
  setError,
}: UseSessionRemovalArgs) {
  const [pendingRemoveSession, setPendingRemoveSession] = useState<AgentSession | null>(null);

  const requestRemoveSession = useCallback((session: AgentSession) => {
    if (activeTurnId) return;
    setPendingRemoveSession(session);
  }, [activeTurnId]);

  const cancelRemoveSession = useCallback(() => setPendingRemoveSession(null), []);

  const confirmRemoveSession = useCallback(async () => {
    const session = pendingRemoveSession;
    if (!session) return;
    setPendingRemoveSession(null);
    try {
      await deleteAgentSession(session.id);
      removeSession(session.id);
      if (currentSessionId === session.id) newSession();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to remove conversation');
    }
  }, [pendingRemoveSession, currentSessionId, removeSession, newSession, setError]);

  return {
    pendingRemoveSession,
    requestRemoveSession,
    cancelRemoveSession,
    confirmRemoveSession,
  };
}
