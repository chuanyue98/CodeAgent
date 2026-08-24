import { format } from 'date-fns';
import type { Translate } from '../../i18n/context';

// ── Engine palette ───────────────────────────────────────────────────────────
const ENGINE_COLORS: Record<string, string> = {
  claude: '#f97316',
  codex: '#10b981',
  opencode: '#8b5cf6',
  codebuddy: '#0ea5e9',
};
const ENGINE_BADGE: Record<string, string> = {
  claude: 'bg-orange-100 text-orange-700',
  codex: 'bg-emerald-100 text-emerald-700',
  opencode: 'bg-violet-100 text-violet-700',
  codebuddy: 'bg-sky-100 text-sky-700',
};

export function ec(t: string) { return ENGINE_COLORS[t] ?? '#94a3b8'; }
export function eb(t: string) { return ENGINE_BADGE[t] ?? 'bg-slate-100 text-slate-600'; }

// ── Tiny format helpers ──────────────────────────────────────────────────────
export function formatDate(s: string) {
  try { return format(new Date(s), 'MMM dd'); } catch { return s.slice(5); }
}
export function formatMonth(s: string) {
  try { return format(new Date(`${s}-01`), 'MMM yyyy'); } catch { return s; }
}
/** Takes `t` rather than calling a hook: this is a pure helper, not a component. */
export function timeAgo(iso: string, t: Translate) {
  if (!iso) return '—';
  const ms = Date.now() - new Date(iso).getTime();
  const days = Math.floor(ms / 86400000);
  if (days === 0) return t('time.today');
  if (days === 1) return t('time.yesterday');
  if (days < 30) return t('time.daysAgo', { days });
  return iso.slice(0, 10);
}
