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
  { id: 'claude',    name: 'Claude',    description: 'Anthropic · Claude Code CLI',       accent: 'bg-orange-100 text-orange-600', dot: 'bg-orange-500' },
  { id: 'opencode',  name: 'OpenCode',  descriptionKey: 'launch.opencodeDescription',     accent: 'bg-violet-100 text-violet-600', dot: 'bg-violet-500' },
  { id: 'codex',     name: 'Codex',     description: 'OpenAI · Codex CLI',                accent: 'bg-emerald-100 text-emerald-600', dot: 'bg-emerald-500' },
  { id: 'codebuddy', name: 'CodeBuddy', description: 'Tencent · CodeBuddy Code CLI',      accent: 'bg-sky-100 text-sky-600', dot: 'bg-sky-500' },
  { id: 'freebuff',  name: 'Freebuff',  description: 'Freebuff · free AI coding agent CLI', accent: 'bg-fuchsia-100 text-fuchsia-700', dot: 'bg-fuchsia-500' },
  { id: 'shell',     nameKey: 'launch.shellName', descriptionKey: 'launch.shellDescription', accent: 'bg-slate-200 text-slate-600', dot: 'bg-slate-400' },
];

export const SHELL_ENGINE_ID = 'shell';
export const FREEBUFF_ENGINE_ID = 'freebuff';

/** 主网格：四个可由 ca_launcher 注入启动的引擎。刻意保持四个——任何列宽都
    能整除成整齐的行，奇数个卡片会在常用宽度留下 4+1 的破洞。 */
export const INJECTED_ENGINES = ENGINES.filter(
  engine => engine.id !== SHELL_ENGINE_ID && engine.id !== FREEBUFF_ENGINE_ID,
);

/** 直连终端：freebuff（免费版 CLI 无注入通道，ca 只能裸拉它的 TUI）与纯
    shell。两者都放在主网格下方并排，避免让上方变成奇数张卡片。 */
export const DIRECT_TERMINALS = ENGINES.filter(
  engine => engine.id === SHELL_ENGINE_ID || engine.id === FREEBUFF_ENGINE_ID,
);

export const SHELL_ENGINE = DIRECT_TERMINALS.find(
  engine => engine.id === SHELL_ENGINE_ID,
)!;

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
