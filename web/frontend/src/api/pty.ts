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
 * @param attachId Attach to a live browser terminal (by its /api/pty/sessions
 *   id) instead of starting a new one.
 */
export function ptyWebSocketUrl(
  engine: string,
  cwd: string,
  sessionId?: string,
  attachId?: string,
  options: PtyConnectOptions = {},
): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const query = new URLSearchParams({ engine, cwd });
  if (sessionId) query.set('session_id', sessionId);
  if (attachId) query.set('attach_id', attachId);
  if (options.tabKey) query.set('tab_key', options.tabKey);
  if (options.cols && options.rows) {
    query.set('cols', String(options.cols));
    query.set('rows', String(options.rows));
  }
  return withToken(`${protocol}//${window.location.host}/api/pty/ws?${query}`);
}

export interface PtyConnectOptions {
  /** The tab's own id: a reconnect of the same tab reattaches its engine. */
  tabKey?: string;
  /** The size the engine starts at. */
  cols?: number;
  rows?: number;
}

/**
 * Stops the engine behind a tab the user closed. Dropping the socket alone
 * only detaches it, and the engine would keep running in tmux.
 */
export function closePtyTerminal(
  engine: string,
  cwd: string,
  sessionId?: string,
  tabKey?: string,
): Promise<{ success: boolean }> {
  const query = new URLSearchParams({ engine, cwd });
  if (sessionId) query.set('session_id', sessionId);
  if (tabKey) query.set('tab_key', tabKey);
  return request(`/api/pty/close?${query}`, { method: 'POST' });
}
