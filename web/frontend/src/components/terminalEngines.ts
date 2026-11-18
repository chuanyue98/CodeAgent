import type { TranslationKey } from '../i18n/locales/en';
import { ENGINE_LABELS } from '../utils/engines';

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
  { id: 'claude',      name: ENGINE_LABELS.claude,      description: 'Anthropic · Claude Code CLI',  accent: 'bg-engine-claude/15 text-engine-claude',           dot: 'bg-engine-claude' },
  { id: 'opencode',    name: ENGINE_LABELS.opencode,    descriptionKey: 'launch.opencodeDescription', accent: 'bg-engine-opencode/15 text-engine-opencode',       dot: 'bg-engine-opencode' },
  { id: 'codex',       name: ENGINE_LABELS.codex,       description: 'OpenAI · Codex CLI',           accent: 'bg-engine-codex/15 text-engine-codex',             dot: 'bg-engine-codex' },
  { id: 'codebuddy',   name: ENGINE_LABELS.codebuddy,   description: 'Tencent · CodeBuddy Code CLI', accent: 'bg-engine-codebuddy/15 text-engine-codebuddy',     dot: 'bg-engine-codebuddy' },
  { id: 'antigravity', name: ENGINE_LABELS.antigravity, description: 'Google · Antigravity CLI',     accent: 'bg-engine-antigravity/15 text-engine-antigravity', dot: 'bg-engine-antigravity' },
  { id: 'shell',       nameKey: 'launch.shellName',     descriptionKey: 'launch.shellDescription',  accent: 'bg-slate-200 text-slate-600',                      dot: 'bg-slate-400' },
];

/** The plain shell starts no agent at all, so it is offered apart from the
    four that do — and it is what makes the list an odd five, which no column
    count divides evenly. */
const SHELL_ENGINE_ID = 'shell';

export const AGENT_ENGINES = ENGINES.filter(engine => engine.id !== SHELL_ENGINE_ID);
export const SHELL_ENGINE = ENGINES.find(engine => engine.id === SHELL_ENGINE_ID)!;

// Sessions come back tagged with whatever engine wrote them, including ones
// this build no longer offers a card for, so both lookups fall back rather
// than assuming the id is in the list.
export function findEngine(id: string): Engine | undefined {
  return ENGINES.find(engine => engine.id === id);
}
