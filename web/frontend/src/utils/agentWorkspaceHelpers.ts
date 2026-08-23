import { formatDistanceToNow } from 'date-fns';
import { enUS, zhCN } from 'date-fns/locale';
import type { Translate } from '../i18n/context';
import type { Language } from '../i18n/language';
import type { AgentSession, NativeAgentSession } from '../types/agent';

// date-fns carries its own translations; map ours onto them so "3 hours ago"
// follows the UI language instead of being permanently zh-CN.
const DATE_LOCALES = { en: enUS, zh: zhCN };

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

export function relativeTime(value: string | null | undefined, language: Language = 'en'): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return formatDistanceToNow(date, { addSuffix: true, locale: DATE_LOCALES[language] });
}

/** Pure helper, so the caller hands it `t` rather than it reaching for a hook. */
export function sessionStatusLabel(status: AgentSession['status'], t: Translate): string {
  switch (status) {
    case 'error': return t('agent.status.error');
    case 'disconnected': return t('agent.status.disconnected');
    case 'busy': return t('agent.status.busy');
    case 'starting': return t('agent.status.starting');
    case 'closed': return t('agent.status.closed');
    default: return t('agent.status.ready');
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
