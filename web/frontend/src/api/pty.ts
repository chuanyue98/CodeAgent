import request from '../utils/request';
import { withToken } from '../utils/token';

export interface PtyCapability {
  available: boolean;
  reason: string | null;
}

export function fetchPtyStatus(): Promise<PtyCapability> {
  return request('/api/pty/status');
}

export function ptyWebSocketUrl(engine: string, cwd: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const query = new URLSearchParams({ engine, cwd });
  return withToken(`${protocol}//${window.location.host}/api/pty/ws?${query}`);
}
