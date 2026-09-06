import type { TranslationKey } from '../i18n/locales/en';

export interface Engine {
  id: string;
  name?: string;
  /** 非品牌名称（如纯终端）走 i18n。 */
  nameKey?: TranslationKey;
  /** Brand blurb that stays as-is (product names), or a key when it is prose. */
  description?: string;
  descriptionKey?: TranslationKey;
  /** Tints the engine's icon tile — the card itself stays neutral so five
      cards read as one row of choices instead of five competing buttons.
      The same tint labels the engine on a session card. */
  accent: string;
  /** Solid tone of the same hue, for the places a tinted block is too heavy:
      a 10px list row, or the collapsed sidebar rail. */
  dot: string;
}

// Engine names and their vendor blurbs are brands, so they are not translated;
// only OpenCode's descriptive line is prose, and it carries a key instead.
export const ENGINES: Engine[] = [
  { id: 'claude',    name: 'Claude',    description: 'Anthropic · Claude Code CLI',      accent: 'bg-orange-100 text-orange-600', dot: 'bg-orange-500' },
  { id: 'opencode',  name: 'OpenCode',  descriptionKey: 'launch.opencodeDescription',    accent: 'bg-violet-100 text-violet-600', dot: 'bg-violet-500' },
  { id: 'codex',     name: 'Codex',     description: 'OpenAI · Codex CLI',               accent: 'bg-emerald-100 text-emerald-600', dot: 'bg-emerald-500' },
  { id: 'codebuddy', name: 'CodeBuddy', description: 'Tencent · CodeBuddy Code CLI',     accent: 'bg-sky-100 text-sky-600', dot: 'bg-sky-500' },
  { id: 'antigravity', name: 'Antigravity', description: 'Google · Antigravity CLI', accent: 'bg-indigo-100 text-indigo-700', dot: 'bg-indigo-500' },
  { id: 'shell',     nameKey: 'launch.shellName', descriptionKey: 'launch.shellDescription', accent: 'bg-slate-200 text-slate-600', dot: 'bg-slate-400' },
];

/** The plain shell starts no agent at all, so it is offered apart from the
    four that do — and it is what makes the list an odd five, which no column
    count divides evenly. */
export const SHELL_ENGINE_ID = 'shell';

export const AGENT_ENGINES = ENGINES.filter(engine => engine.id !== SHELL_ENGINE_ID);
export const SHELL_ENGINE = ENGINES.find(engine => engine.id === SHELL_ENGINE_ID)!;

// Sessions come back tagged with whatever engine wrote them, including ones
// this build no longer offers a card for, so both lookups fall back rather
// than assuming the id is in the list.
export function findEngine(id: string): Engine | undefined {
  return ENGINES.find(engine => engine.id === id);
}

export function engineAccent(id: string): string {
  return findEngine(id)?.accent ?? 'bg-slate-100 text-slate-600';
}

export function engineDot(id: string): string {
  return findEngine(id)?.dot ?? 'bg-slate-300';
}
