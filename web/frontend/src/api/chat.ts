import { useState, useEffect, useRef } from 'react';

export interface ChatEngine {
  id: string;
  name: string;
  description: string;
  supportsResume: boolean;
}

export interface ChatTurnStatus {
  task_id: string;
  engine: string;
  pid: number | null;
  status: 'running' | 'completed' | 'failed' | 'stopped' | string;
  log_path: string;
  start_time: number;
  session_id: string | null;
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

export async function fetchChatEngines(): Promise<ChatEngine[]> {
  const res = await fetch('/api/engines');
  if (!res.ok) throw new Error('Failed to fetch engines');
  return res.json();
}

export async function fetchResumableSessions(engine: string, limit = 50): Promise<SessionSummary[]> {
  const res = await fetch(`/api/history?engine=${encodeURIComponent(engine)}&limit=${limit}`);
  if (!res.ok) throw new Error('Failed to fetch sessions');
  const data = await res.json();
  return data.sessions;
}

export async function startChatTurn(params: {
  engine: string;
  message: string;
  session_id?: string | null;
  group?: string;
}): Promise<ChatTurnStatus> {
  const res = await fetch('/api/chat/turns', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || 'Failed to start chat turn');
  }
  return res.json();
}

export async function fetchChatTurn(turnId: string): Promise<ChatTurnStatus> {
  const res = await fetch(`/api/chat/turns/${encodeURIComponent(turnId)}`);
  if (!res.ok) throw new Error('Failed to fetch chat turn');
  return res.json();
}

export interface ChatStreamEvent {
  raw: Record<string, unknown>;
}

export function useChatTurnStream(turnId: string | null) {
  const [events, setEvents] = useState<Record<string, unknown>[]>([]);
  const [done, setDone] = useState<{ status: string; session_id: string | null } | null>(null);
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

    const url = `/api/chat/turns/${encodeURIComponent(turnId)}/stream`;
    const eventSource = new EventSource(url);
    sourceRef.current = eventSource;

    eventSource.onerror = () => {
      setError('Connection lost');
    };

    eventSource.addEventListener('message', (event: MessageEvent) => {
      try {
        const parsed = JSON.parse(event.data);
        if (parsed.error) {
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
        setDone({ status: 'completed', session_id: null });
      }
      eventSource.close();
    });

    return () => {
      eventSource.close();
    };
  }, [turnId]);

  return { events, done, error };
}
