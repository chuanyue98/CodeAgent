/**
 * Language resolution, kept free of React so it can be unit-tested and reused
 * from non-component code.
 *
 * The order mirrors core/i18n.py's, minus the pieces that only exist in a
 * process (CA_LANG, the OS locale): config.json's `language` is the shared
 * setting, so switching it in the Web UI also changes what the CLI prints.
 * The browser locale only decides the very first visit, before anyone has
 * chosen anything.
 */

export const SUPPORTED_LANGUAGES = ['en', 'zh'] as const;

export type Language = (typeof SUPPORTED_LANGUAGES)[number];

export const DEFAULT_LANGUAGE: Language = 'en';

/** Mirrors core/i18n.py's `_AUTO_VALUES` — legacy "decide for me" markers. */
const AUTO_VALUES = new Set(['', 'auto', 'hybrid', 'system']);

/**
 * Maps a config value or a browser locale (`zh-CN`, `en-US`) onto a supported
 * code, or null when it means nothing to us.
 */
export function normalizeLanguage(value: string | null | undefined): Language | null {
  if (typeof value !== 'string') return null;
  const lowered = value.trim().toLowerCase();
  if (AUTO_VALUES.has(lowered)) return null;
  const base = lowered.split(/[-_]/)[0];
  return (SUPPORTED_LANGUAGES as readonly string[]).includes(base) ? (base as Language) : null;
}

/**
 * The language to paint with before /api/config has answered. Reads the cache
 * written by the last resolved config so a reload doesn't flash the wrong
 * language, and falls back to what the browser asks for.
 */
export function resolveInitialLanguage(
  cached: string | null,
  navigatorLanguages: readonly string[] = [],
): Language {
  const fromCache = normalizeLanguage(cached);
  if (fromCache) return fromCache;
  for (const candidate of navigatorLanguages) {
    const fromNavigator = normalizeLanguage(candidate);
    if (fromNavigator) return fromNavigator;
  }
  return DEFAULT_LANGUAGE;
}

/**
 * Substitutes `{name}` placeholders. A missing variable leaves the placeholder
 * in place rather than printing "undefined" — a visible `{count}` is easier to
 * spot and fix than a plausible-looking wrong sentence.
 */
export function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in vars ? String(vars[name]) : match,
  );
}
