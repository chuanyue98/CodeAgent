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
