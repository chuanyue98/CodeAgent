import { formatDistanceToNow } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import type { AgentSession, NativeAgentSession } from '../types/agent';

export function requestId(): string {
  return crypto.randomUUID();
}

export const SESSION_PAGE_SIZE = 20;

export type ConversationListItem =
  | { source: 'gateway'; key: string; projectPath: string; updatedAt: string; session: AgentSession }
  | { source: 'native'; key: string; projectPath: string; updatedAt: string; session: NativeAgentSession };

export function workspaceLabel(path: string): string {
  const normalized = path.replace(/\\/g, '/').replace(/\/+$/, '');
  return normalized.split('/').filter(Boolean).at(-1) || path;
}

export function relativeTime(value: string | null | undefined): string {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : formatDistanceToNow(date, { addSuffix: true, locale: zhCN });
}

export function sessionStatusLabel(status: AgentSession['status']): string {
  switch (status) {
    case 'error': return '需要关注';
    case 'disconnected': return '重新连接';
    case 'busy': return '运行中';
    case 'starting': return '启动中';
    case 'closed': return '已关闭';
    default: return '就绪';
  }
}

export function deduplicateNativeSessions(
  sessions: NativeAgentSession[],
): NativeAgentSession[] {
  const byIdentity = new Map<string, NativeAgentSession>();
  sessions.forEach(session => {
    const identity = `${session.engine}:${session.session_id}`;
    const current = byIdentity.get(identity);
    const sessionTimestamp = session.ended_at || session.started_at;
    const currentTimestamp = current?.ended_at || current?.started_at || '';
    if (
      !current
      || session.message_count > current.message_count
      || (
        session.message_count === current.message_count
        && sessionTimestamp > currentTimestamp
      )
    ) {
      byIdentity.set(identity, session);
    }
  });
  return [...byIdentity.values()];
}
