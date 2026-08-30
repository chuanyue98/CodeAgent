import { NavLink, Outlet, useLocation } from 'react-router';
import { useT } from '../i18n/context';
import type { TranslationKey } from '../i18n/locales/en';
import { ACTIVE_CHIP } from './shared/activeChip';

export interface SectionTab {
  to: string;
  labelKey: TranslationKey;
  matchPrefix?: string;
}

interface SectionLayoutProps {
  labelKey: TranslationKey;
  tabs: SectionTab[];
  /**
   * Query params to carry from the current URL onto each tab link, so state
   * shared by a section's tabs (Activity's filters) survives switching
   * between them instead of resetting.
   */
  preserveParams?: string[];
}

export default function SectionLayout({
  labelKey,
  tabs,
  preserveParams,
}: SectionLayoutProps) {
  const { pathname, search } = useLocation();
  const t = useT();

  const carried = (() => {
    if (!preserveParams?.length) return '';
    const current = new URLSearchParams(search);
    const next = new URLSearchParams();
    for (const key of preserveParams) {
      const value = current.get(key);
      if (value) next.set(key, value);
    }
    const query = next.toString();
    return query ? `?${query}` : '';
  })();

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      {/* The section's one-line description lives in the app header, under the
          title. Parked out here at the far right of a wide row it sat a screen
          away from the words it explained, in the lightest grey on the page. */}
      <div className="animate-fade-rise stagger-1 border-b border-slate-200 px-1 pb-2">
        <nav aria-label={t('section.nav', { label: t(labelKey) })} className="custom-scrollbar flex max-w-full gap-1 overflow-x-auto">
          {tabs.map(tab => {
            const active = tab.matchPrefix
              ? pathname === tab.matchPrefix || pathname.startsWith(`${tab.matchPrefix}/`)
              : pathname === tab.to;
            return (
              <NavLink
                key={tab.to}
                to={`${tab.to}${carried}`}
                aria-current={active ? 'page' : undefined}
                className={`animate-fade-rise shrink-0 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                  active
                    ? ACTIVE_CHIP
                    : 'text-slate-500 hover:bg-slate-100 hover:text-slate-800'
                }`}
              >
                {t(tab.labelKey)}
              </NavLink>
            );
          })}
        </nav>
      </div>

      {/* key on pathname so each route transition re-triggers the entrance
          animation — gives a clear "you arrived somewhere new" beat. */}
      <div key={pathname} className="animate-fade-rise stagger-3 min-h-0 flex-1">
        <Outlet />
      </div>
    </div>
  );
}
