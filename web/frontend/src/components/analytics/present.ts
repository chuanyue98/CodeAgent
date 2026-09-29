import { format } from 'date-fns';
import type { Translate } from '../../i18n/context';

// ── Engine palette ───────────────────────────────────────────────────────────
const ENGINE_COLORS: Record<string, string> = {
  claude: '#e08a68',
  codex: '#3fc796',
  opencode: '#a78bfa',
  codebuddy: '#55a8ff',
  antigravity: '#f172b3',
};
const ENGINE_BADGE: Record<string, string> = {
  claude: 'bg-engine-claude/15 text-engine-claude',
  codex: 'bg-engine-codex/15 text-engine-codex',
  opencode: 'bg-engine-opencode/15 text-engine-opencode',
  codebuddy: 'bg-engine-codebuddy/15 text-engine-codebuddy',
  antigravity: 'bg-engine-antigravity/15 text-engine-antigravity',
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
