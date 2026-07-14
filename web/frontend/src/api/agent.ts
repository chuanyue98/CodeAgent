import request from '../utils/request';
import type {
  AgentCommand,
  AgentSession,
  PermissionMode,
  ProviderCapabilities,
} from '../types/agent';

export function fetchAgentProviders(): Promise<ProviderCapabilities[]> {
  return request('/api/agent/providers');
}

export function fetchAgentSessions(limit = 100): Promise<AgentSession[]> {
  return request(`/api/agent/sessions?limit=${limit}`);
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
