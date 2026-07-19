import request from '../utils/request';
import type {
  AgentCommand,
  AgentEvent,
  AgentGatewayStatus,
  AgentSession,
  NativeAgentSession,
  PermissionMode,
  ProviderCapabilities,
} from '../types/agent';

export function fetchAgentGatewayStatus(): Promise<AgentGatewayStatus> {
  return request('/api/agent/status');
}

export function fetchAgentProviders(): Promise<ProviderCapabilities[]> {
  return request('/api/agent/providers');
}

export function fetchAgentSessions(limit = 500): Promise<AgentSession[]> {
  return request(`/api/agent/sessions?limit=${limit}`);
}

export async function fetchNativeAgentSessions(
  provider: string,
  limit = 500,
): Promise<NativeAgentSession[]> {
  const query = new URLSearchParams({ engine: provider, limit: String(limit) });
  const result = await request<{ sessions: NativeAgentSession[] }>(`/api/history?${query}`);
  return result.sessions;
}

export function importAgentSession(payload: {
  provider: string;
  providerSessionId: string;
  projectId: string;
  permissionMode: PermissionMode;
  title?: string;
  model?: string;
}): Promise<AgentSession> {
  return request('/api/agent/sessions/import', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function createAgentSession(payload: {
  provider: string;
  projectId: string;
  model?: string;
  permissionMode: PermissionMode;
  title?: string;
}): Promise<AgentSession> {
  return request('/api/agent/sessions', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function resumeAgentSession(sessionId: string): Promise<AgentSession> {
  return request(`/api/agent/sessions/${encodeURIComponent(sessionId)}/resume`, {
    method: 'POST',
  });
}

export type AgentHistoryPage = {
  events: AgentEvent[];
  oldestSequence: number | null;
  latestSequence: number;
  hasMore: boolean;
};

export function fetchAgentHistory(
  sessionId: string,
  beforeSequence?: number,
  limit = 100,
): Promise<AgentHistoryPage> {
  const query = new URLSearchParams({ limit: String(limit) });
  if (beforeSequence) query.set('beforeSequence', String(beforeSequence));
  return request(`/api/agent/sessions/${encodeURIComponent(sessionId)}/history?${query}`);
}

export function deleteAgentSession(sessionId: string): Promise<void> {
  return request(`/api/agent/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  });
}

export function agentEventsUrl(sessionId: string, afterSequence = 0): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const query = new URLSearchParams({ afterSequence: String(afterSequence) });
  return `${protocol}//${window.location.host}/api/agent/sessions/${encodeURIComponent(sessionId)}/events?${query}`;
}

export function sendAgentCommand(socket: WebSocket, command: AgentCommand): void {
  if (socket.readyState !== WebSocket.OPEN) {
    throw new Error('Agent connection is not ready');
  }
  socket.send(JSON.stringify(command));
}
