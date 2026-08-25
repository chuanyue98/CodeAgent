import request from '../utils/request';
import { withToken } from '../utils/token';

export interface PtyCapability {
  available: boolean;
  reason: string | null;
}

export function fetchPtyStatus(): Promise<PtyCapability> {
  return request('/api/pty/status');
}

/**
 * @param sessionId Resume this existing session instead of starting a new one.
 *   The server hands it to the engine's own resume flag.
 */
export function ptyWebSocketUrl(
  engine: string,
  cwd: string,
  sessionId?: string,
): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const query = new URLSearchParams({ engine, cwd });
  if (sessionId) query.set('session_id', sessionId);
  return withToken(`${protocol}//${window.location.host}/api/pty/ws?${query}`);
}
