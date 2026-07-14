import { NavLink, Outlet, useLocation } from 'react-router-dom';

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
      <div className="border-b border-slate-200 px-1 pb-2">
        <span className="sr-only">{description}</span>
        <nav aria-label={`${label} sections`} className="custom-scrollbar flex max-w-full gap-1 overflow-x-auto">
          {tabs.map(tab => {
            const active = tab.matchPrefix
              ? pathname === tab.matchPrefix || pathname.startsWith(`${tab.matchPrefix}/`)
              : pathname === tab.to;
            return (
              <NavLink
                key={tab.to}
                to={tab.to}
                aria-current={active ? 'page' : undefined}
                className={`shrink-0 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
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
      </div>

      <div className="min-h-0 flex-1">
        <Outlet />
      </div>
    </div>
  );
}
