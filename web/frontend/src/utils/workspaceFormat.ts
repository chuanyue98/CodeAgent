import { formatDistanceToNow } from 'date-fns';
import { enUS, zhCN } from 'date-fns/locale';
import type { Language } from '../i18n/language';

// date-fns carries its own translations; map ours onto them so "3 hours ago"
// follows the UI language instead of being permanently zh-CN.
const DATE_LOCALES = { en: enUS, zh: zhCN };

/** The trailing directory of a workspace path, for labelling it in a list. */
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

export function formatWorkspaceLabel(path: string, group?: string): string {
  if (!path) return '';
  const trimmed = path.replace(/[/\\]+$/, '');
  const basename = trimmed.split(/[/\\]/).pop() || path;
  if (group && group !== 'common') {
    return `${basename} (${group})`;
  }
  return basename;
}

export function formatRelativeCountdown(targetTimestampSec: number, language: string = 'en'): string {
  if (!targetTimestampSec || targetTimestampSec <= 0) return '';
  const diffSec = Math.floor(targetTimestampSec - Date.now() / 1000);
  if (diffSec <= 0) return '';
  const isZh = language.toLowerCase().startsWith('zh');
  if (diffSec < 60) return isZh ? '即将执行' : '< 1m';
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return isZh ? `${diffMin}分钟后` : `in ${diffMin}m`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return isZh ? `${diffHr}小时后` : `in ${diffHr}h`;
  const diffDay = Math.floor(diffHr / 24);
  return isZh ? `${diffDay}天后` : `in ${diffDay}d`;
}

