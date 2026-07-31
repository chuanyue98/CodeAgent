import { useState, useEffect, useRef } from 'react';
import request from '../utils/request';
import { withToken } from '../utils/token';

export interface ChatEngine {
  id: string;
  name: string;
  description: string;
  supportsResume: boolean;
}

export interface ChatTurnStatus {
  taskId: string;
  engine: string;
  pid: number | null;
  status: 'running' | 'completed' | 'failed' | 'stopped' | string;
  logPath: string;
  startTime: number;
  sessionId: string | null;
}

export interface SessionSummary {
  session_id: string;
  engine: string;
  project_path: string;
  started_at: string;
  ended_at: string | null;
  message_count: number;
  title: string;
  model: string | null;
}

export interface ChatResourceSet {
  skills: string[];
  hooks: string[];
  plugins: string[];
}

export interface ChatCapabilities {
  mode: 'legacy_one_shot';
  engine: string;
  group: string;
  projectPath: string | null;
  configurationWarnings: string[];
  codeagentResourcesInjected: boolean;
  active: ChatResourceSet;
  configuredButInactive: ChatResourceSet;
  providerNative: {
    status: 'unknown';
    reason: string;
  };
  notice: string;
}

export async function fetchChatEngines(): Promise<ChatEngine[]> {
  return request('/api/engines');
}

export async function fetchResumableSessions(engine: string, limit = 50): Promise<SessionSummary[]> {
  const data = await request<{ sessions: SessionSummary[] }>(`/api/history?engine=${encodeURIComponent(engine)}&limit=${limit}`);
  return data.sessions;
}

export async function fetchChatCapabilities(params: {
  engine: string;
  group: string;
  projectPath?: string | null;
}): Promise<ChatCapabilities> {
  const query = new URLSearchParams({ engine: params.engine, group: params.group });
  if (params.projectPath) query.set('project_path', params.projectPath);
  return request(`/api/chat/capabilities?${query.toString()}`);
}

export async function startChatTurn(params: {
  engine: string;
  message: string;
  sessionId?: string | null;
  group?: string;
  projectPath: string;
}): Promise<ChatTurnStatus> {
  return request('/api/chat/turns', {
    method: 'POST',
    body: JSON.stringify({
      engine: params.engine,
      message: params.message,
      sessionId: params.sessionId,
      group: params.group,
      projectPath: params.projectPath,
    }),
  });
}

export async function cancelChatTurn(turnId: string): Promise<ChatTurnStatus> {
  return request(`/api/chat/turns/${encodeURIComponent(turnId)}/cancel`, {
    method: 'POST',
  });
}

export async function fetchChatTurn(turnId: string): Promise<ChatTurnStatus> {
  return request(`/api/chat/turns/${encodeURIComponent(turnId)}`);
}

export interface ChatStreamEvent {
  raw: Record<string, unknown>;
}

export function useChatTurnStream(turnId: string | null) {
  const [events, setEvents] = useState<Record<string, unknown>[]>([]);
  const [done, setDone] = useState<{ status: string; sessionId: string | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sourceRef = useRef<EventSource | null>(null);

  // Reset events/done/error the instant turnId changes, *during render*
  // (React's documented pattern for this) rather than in a useEffect —
  // an effect-based reset leaves a one-render window where the new turnId
  // is visible alongside the *previous* turn's stale events/done, which a
  // consumer's own effect (keyed on [events, turnId]) can observe and act
  // on before the reset effect below has run. Caught live: turn 2 of a
  // resumed chat briefly saw turn 1's leftover events and displayed turn
  // 1's answer instead of turn 2's.
  const [prevTurnId, setPrevTurnId] = useState(turnId);
  if (turnId !== prevTurnId) {
    setPrevTurnId(turnId);
    setEvents([]);
    setDone(null);
    setError(null);
  }

  useEffect(() => {
    if (!turnId) return;

    // EventSource cannot set headers, so the token rides the query string.
    const url = withToken(`/api/chat/turns/${encodeURIComponent(turnId)}/stream`);
    const eventSource = new EventSource(url);
    sourceRef.current = eventSource;

    eventSource.onerror = () => {
      setError('Connection lost');
    };

    eventSource.addEventListener('message', (event: MessageEvent) => {
      try {
        const parsed = JSON.parse(event.data);
        if (parsed && typeof parsed === 'object' && parsed.error) {
          setError(parsed.error);
          eventSource.close();
          return;
        }
        setEvents(prev => {
          const MAX_EVENTS = 5000;
          const next = [...prev, parsed];
          return next.length > MAX_EVENTS ? next.slice(next.length - MAX_EVENTS) : next;
        });
      } catch {
        // ignore parse errors
      }
    });

    eventSource.addEventListener('done', (event: MessageEvent) => {
      try {
        setDone(JSON.parse(event.data));
      } catch {
        setDone({ status: 'completed', sessionId: null });
      }
      eventSource.close();
    });

    return () => {
      eventSource.close();
    };
  }, [turnId]);

  return { events, done, error };
}
