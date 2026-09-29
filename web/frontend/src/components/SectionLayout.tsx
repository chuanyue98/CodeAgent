import { NavLink, Outlet, useLocation } from 'react-router';
import { useT } from '../i18n/context';
import { primaryNav } from '../navigation';
import type { TranslationKey } from '../i18n/locales/en';

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
   * shared by a section's tabs (History's filters) survives switching
   * between them instead of resetting.
   */
  preserveParams?: string[];
  /**
   * Routes that fill the whole stage and draw their own top strip (the
   * terminal). They get no page header and no padding.
   */
  bleedPaths?: string[];
}

/**
 * A section's frame: its name and one-line purpose on the left, its views as a
 * segmented control on the right, the page below. One header per section
 * instead of a title row plus a tab row stacked under an app-level header.
 */
export default function SectionLayout({
  labelKey,
  tabs,
  preserveParams,
  bleedPaths,
}: SectionLayoutProps) {
  const { pathname, search } = useLocation();
  const t = useT();
  const bleed = bleedPaths?.includes(pathname) ?? false;
  const descriptionKey = primaryNav.find(item => item.labelKey === labelKey)?.descriptionKey;

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
    <div className="flex h-full min-h-0 flex-col">
      {!bleed && (
        <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3 px-4 pb-4 pt-5 md:px-8 md:pt-7">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold tracking-tight">{t(labelKey)}</h1>
            {descriptionKey && <p className="mt-1 text-sm text-muted-foreground">{t(descriptionKey)}</p>}
          </div>
          {tabs.length > 1 && (
          <nav
            aria-label={t('section.nav', { label: t(labelKey) })}
            className="custom-scrollbar flex max-w-full overflow-x-auto rounded-lg border border-border"
          >
            {tabs.map(tab => {
              const active = tab.matchPrefix
                ? pathname === tab.matchPrefix || pathname.startsWith(`${tab.matchPrefix}/`)
                : pathname === tab.to;
              return (
                <NavLink
                  key={tab.to}
                  to={`${tab.to}${carried}`}
                  aria-current={active ? 'page' : undefined}
                  className={`shrink-0 px-3.5 py-1.5 text-sm font-medium transition-colors ${
                    active ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {t(tab.labelKey)}
                </NavLink>
              );
            })}
          </nav>
          )}
        </header>
      )}
      <div key={pathname} className={`relative min-h-0 flex-1 ${bleed ? '' : 'overflow-y-auto px-4 pb-8 md:px-8'}`}>
        <Outlet />
      </div>
    </div>
  );
}
