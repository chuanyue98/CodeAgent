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
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white/80 px-3 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-4">
        <p className="text-xs text-slate-500">{description}</p>
        <nav aria-label={`${label} sections`} className="flex max-w-full gap-1 overflow-x-auto rounded-xl bg-slate-100/80 p-1 custom-scrollbar">
          {tabs.map(tab => {
            const active = tab.matchPrefix
              ? pathname === tab.matchPrefix || pathname.startsWith(`${tab.matchPrefix}/`)
              : pathname === tab.to;
            return (
              <NavLink
                key={tab.to}
                to={tab.to}
                aria-current={active ? 'page' : undefined}
                className={`shrink-0 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                  active
                    ? 'bg-white text-primary shadow-sm'
                    : 'text-slate-500 hover:bg-white/70 hover:text-slate-800'
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
