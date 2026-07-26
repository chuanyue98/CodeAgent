import { NavLink, Outlet, useLocation } from 'react-router';

export interface SectionTab {
  to: string;
  label: string;
  matchPrefix?: string;
}

interface SectionLayoutProps {
  label: string;
  description: string;
  tabs: SectionTab[];
}

export default function SectionLayout({ label, description, tabs }: SectionLayoutProps) {
  const { pathname } = useLocation();

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      {/* The description used to be sr-only, so the one line explaining what
          a section is for was readable by screen readers and nobody else.
          Shown from lg up, where there is room beside the tabs. */}
      <div className="animate-fade-rise stagger-1 flex flex-wrap items-center justify-between gap-x-4 border-b border-slate-200 px-1 pb-2">
        <span className="sr-only">{description}</span>
        <nav aria-label={`${label} sections`} className="custom-scrollbar flex max-w-full gap-1 overflow-x-auto">
          {tabs.map((tab, i) => {
            const active = tab.matchPrefix
              ? pathname === tab.matchPrefix || pathname.startsWith(`${tab.matchPrefix}/`)
              : pathname === tab.to;
            // Stagger the tab chips so they cascade in alongside the bar.
            const stagger = `stagger-${Math.min(i + 2, 7)}`;
            return (
              <NavLink
                key={tab.to}
                to={tab.to}
                aria-current={active ? 'page' : undefined}
                className={`animate-fade-rise ${stagger} shrink-0 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                  active
                    ? 'bg-primary/10 text-primary'
                    : 'text-slate-500 hover:bg-slate-100 hover:text-slate-800'
                }`}
              >
                {tab.label}
              </NavLink>
            );
          })}
        </nav>
        <p aria-hidden className="hidden truncate text-xs text-slate-400 lg:block">{description}</p>
      </div>

      {/* key on pathname so each route transition re-triggers the entrance
          animation — gives a clear "you arrived somewhere new" beat. */}
      <div key={pathname} className="animate-fade-rise stagger-3 min-h-0 flex-1">
        <Outlet />
      </div>
    </div>
  );
}
