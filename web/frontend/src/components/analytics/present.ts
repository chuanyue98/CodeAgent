import { format } from 'date-fns';
import type { Translate } from '../../i18n/context';
import { parseLocalDay, toLocalDayString } from '../../utils/dateRange';

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
  const local = parseLocalDay(s);
  if (local) return format(local, 'MMM dd');
  try {
    const parsed = new Date(s);
    if (!Number.isNaN(parsed.getTime())) return format(parsed, 'MMM dd');
  } catch {
    // fallback below
  }
  return s.slice(5);
}

export function formatMonth(s: string) {
  const local = parseLocalDay(`${s}-01`);
  if (local) return format(local, 'MMM yyyy');
  try {
    const parsed = new Date(`${s}-01T00:00:00`);
    if (!Number.isNaN(parsed.getTime())) return format(parsed, 'MMM yyyy');
  } catch {
    // fallback below
  }
  return s;
}

/** Takes `t` rather than calling a hook: this is a pure helper, not a component. */
export function timeAgo(iso: string, t: Translate) {
  if (!iso) return '—';
  const parsed = new Date(iso);
  const ts = parsed.getTime();
  if (Number.isNaN(ts)) return '—';
  const days = Math.floor((Date.now() - ts) / 86400000);
  if (days === 0) return t('time.today');
  if (days === 1) return t('time.yesterday');
  if (days < 30) return t('time.daysAgo', { days });
  return toLocalDayString(parsed);
}
