import { useEffect, useRef, useState } from 'react';
import { Languages, ChevronDown } from 'lucide-react';
import { useProject } from '../context/ProjectContext';
import { useLanguage } from '../i18n/context';
import { SUPPORTED_LANGUAGES, type Language } from '../i18n/language';

const LABEL_KEYS = { en: 'language.en', zh: 'language.zh' } as const;

/**
 * Header control for the UI language.
 *
 * Writing the choice to config.json rather than to browser storage is
 * deliberate: `language` is the same field core/i18n.py reads, so switching
 * here also switches what `ca` prints in the terminal. The local state moves
 * first so the UI repaints immediately, and the write is best-effort — a
 * failed save leaves the session translated and surfaces through the shared
 * config error banner.
 */
export default function LanguageSwitcher() {
  const { language, setLanguage, t } = useLanguage();
  const { config, updateConfig } = useProject();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const choose = (next: Language) => {
    setOpen(false);
    if (next === language) return;
    setLanguage(next);
    void updateConfig({ ...(config ?? {}), language: next });
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        data-testid="language-switcher"
        onClick={() => setOpen(prev => !prev)}
        onKeyDown={event => {
          if (event.key === 'Escape') setOpen(false);
        }}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={t('language.switch')}
        title={t('language.switch')}
        className="flex items-center gap-1.5 rounded-xl border border-slate-100 bg-white/50 px-3 py-2 text-slate-500 shadow-sm backdrop-blur-md transition-colors hover:bg-white hover:text-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
      >
        <Languages size={16} className="shrink-0" />
        <span className="hidden text-xs font-semibold uppercase sm:inline">{language}</span>
        <ChevronDown size={14} className={`text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute right-0 z-50 mt-2 w-40 overflow-hidden rounded-xl border border-slate-100 bg-white shadow-xl">
          <div className="px-4 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
            {t('language.label')}
          </div>
          <div role="listbox" aria-label={t('language.label')} className="p-2 pt-1">
            {SUPPORTED_LANGUAGES.map(code => (
              <button
                key={code}
                type="button"
                role="option"
                aria-selected={code === language}
                onClick={() => choose(code)}
                className={`flex w-full items-center justify-between rounded-lg px-2 py-2 text-left text-xs font-medium transition-colors ${
                  code === language ? 'bg-primary/10 text-primary' : 'text-slate-600 hover:bg-slate-50'
                }`}
              >
                {t(LABEL_KEYS[code])}
                <span className="text-[10px] uppercase text-slate-400">{code}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
