import { useEffect } from 'react';
import { useProject } from '../context/ProjectContext';
import { useLanguage } from './context';
import { normalizeLanguage } from './language';

/**
 * Applies config.json's `language` once /api/config has answered.
 *
 * The setting is shared with the CLI (core/i18n.py reads the same field), so
 * the config file — not the browser — is what decides. Until it loads, the
 * provider paints in the cached/browser language; this is the reconciliation.
 *
 * An absent or "auto" value is left alone rather than written back: the user
 * has expressed no preference, and silently persisting whatever the browser
 * happened to ask for would change what the CLI prints.
 */
export default function LanguageSync() {
  const { config } = useProject();
  const { language, setLanguage } = useLanguage();

  useEffect(() => {
    const configured = normalizeLanguage(config?.language);
    if (configured && configured !== language) {
      setLanguage(configured);
    }
  }, [config?.language, language, setLanguage]);

  return null;
}
