import { createContext, useContext } from 'react';
import { DEFAULT_LANGUAGE, interpolate, type Language } from './language';
import { en, type TranslationKey } from './locales/en';

export type Translate = (key: TranslationKey, vars?: Record<string, string | number>) => string;

export interface LanguageContextValue {
  language: Language;
  /** Applies a language locally. Persisting it to config.json is the caller's job. */
  setLanguage: (language: Language) => void;
  t: Translate;
}

export const LanguageContext = createContext<LanguageContextValue | undefined>(undefined);

export function useLanguage(): LanguageContextValue {
  const context = useContext(LanguageContext);
  if (!context) throw new Error('useLanguage must be used within LanguageProvider');
  return context;
}

/**
 * Translates in the default language. Used when there is no provider above —
 * see useT.
 */
export const translateDefault: Translate = (key, vars) => interpolate(en[key] ?? key, vars);

export const FALLBACK_LANGUAGE: Language = DEFAULT_LANGUAGE;

/**
 * The hook nearly every component wants: just the translate function.
 *
 * Unlike useLanguage this does not throw without a provider, it falls back to
 * the default language. Two real cases need that: the app-wide ErrorBoundary
 * sits outside LanguageProvider (it has to, so it can catch the provider
 * failing), and a unit test rendering one component in isolation shouldn't
 * have to assemble the whole shell just to read a label.
 *
 * `t` is stable for a given language, so it is safe in a dependency array —
 * effects that build a translated string re-run when the language changes and
 * at no other time.
 */
export function useT(): Translate {
  return useContext(LanguageContext)?.t ?? translateDefault;
}

/**
 * The active language code, for the few places that need it directly (date
 * formatting). Tolerates a missing provider for the same reason useT does —
 * *reading* the language can sensibly default, whereas changing it (which is
 * what useLanguage exposes) cannot.
 */
export function useLanguageCode(): Language {
  return useContext(LanguageContext)?.language ?? FALLBACK_LANGUAGE;
}
