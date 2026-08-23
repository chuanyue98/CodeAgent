import { useCallback, useMemo, useState, type ReactNode } from 'react';
import { LanguageContext } from './context';
import {
  DEFAULT_LANGUAGE,
  interpolate,
  resolveInitialLanguage,
  type Language,
} from './language';
import { en, type TranslationKey } from './locales/en';
import { zh } from './locales/zh';

const DICTIONARIES: Record<Language, Record<TranslationKey, string>> = { en, zh };

/**
 * Remembers the last resolved language so a reload paints in it immediately
 * instead of flashing the default while /api/config is in flight. It is a
 * cache, not the setting — config.json stays authoritative (see LanguageSync).
 */
const CACHE_KEY = 'ca.language';

function readCache(): string | null {
  try {
    return localStorage.getItem(CACHE_KEY);
  } catch {
    // Private windows and blocked site data throw on access; a missing cache
    // just means we fall back to the browser locale for this first paint.
    return null;
  }
}

function writeCache(language: Language): void {
  try {
    localStorage.setItem(CACHE_KEY, language);
  } catch {
    // Non-fatal: without the cache the next reload re-resolves from config.
  }
}

export function LanguageProvider({
  children,
  initialLanguage,
}: {
  children: ReactNode;
  /** Pins the language instead of resolving it — used by tests. */
  initialLanguage?: Language;
}) {
  const [language, setLanguageState] = useState<Language>(
    () =>
      initialLanguage ??
      resolveInitialLanguage(readCache(), typeof navigator === 'undefined' ? [] : navigator.languages),
  );

  const setLanguage = useCallback((next: Language) => {
    setLanguageState(next);
    writeCache(next);
  }, []);

  const value = useMemo(() => {
    const dictionary = DICTIONARIES[language] ?? DICTIONARIES[DEFAULT_LANGUAGE];
    return {
      language,
      setLanguage,
      t: (key: TranslationKey, vars?: Record<string, string | number>) =>
        interpolate(dictionary[key] ?? en[key] ?? key, vars),
    };
  }, [language, setLanguage]);

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}
