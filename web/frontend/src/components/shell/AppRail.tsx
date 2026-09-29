import { useState } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router';
import { Monitor, Moon, Plus, Sun } from 'lucide-react';
import CommandPalette from '../CommandPalette';
import NotificationBell from '../NotificationBell';
import SystemPanel from '../SystemPanel';
import WorkspaceSwitcher from '../WorkspaceSwitcher';
import { findEngine } from '../terminalEngines';
import { useMediaQuery } from '../../hooks/useMediaQuery';
import { useSystemMetrics } from '../../context/SystemMetricsContext';
import { useTerminal } from '../../context/TerminalContext';
import { useT } from '../../i18n/context';
import { primaryNav } from '../../navigation';
import { applyTheme, readTheme, type ThemeChoice } from '../../utils/theme';
import { workspaceLabel } from '../../utils/workspaceFormat';

const NEXT_THEME: Record<ThemeChoice, ThemeChoice> = { system: 'light', light: 'dark', dark: 'system' };

function isActive(pathname: string, prefix: string) {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

function Meter({ label, value }: { label: string; value: number | undefined }) {
  return (
    <span className="flex items-center gap-1.5" title={`${label} ${value === undefined ? '—' : `${value.toFixed(0)}%`}`}>
      <span>{label}</span>
      <span className="block h-1 w-7 overflow-hidden rounded-full bg-muted">
        <span
          className={`block h-full ${value !== undefined && value > 85 ? 'bg-destructive' : 'bg-muted-foreground'}`}
          style={{ width: `${Math.min(100, Math.max(0, value ?? 0))}%` }}
        />
      </span>
    </span>
  );
}

/**
 * The left rail: the workspace you are in, a way to jump anywhere, the five
 * places to go, and the sessions that are open right now. Status (machine
 * load, notifications, theme) sits at the bottom where it stays out of the
 * way of the work above it.
 */
export default function AppRail() {
  const t = useT();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { tabs, activeTabId, setActiveTabId, rateLimitedTabIds } = useTerminal();
  const { metrics } = useSystemMetrics();
  // One layout is mounted, not both with CSS hiding one: the command palette
  // listens for Ctrl+K on mount, so two copies would open two dialogs.
  const desktop = useMediaQuery('(min-width: 768px)');
  const [theme, setTheme] = useState<ThemeChoice>(() => readTheme());

  const cycleTheme = () => {
    const next = NEXT_THEME[theme];
    applyTheme(next);
    setTheme(next);
  };
  const ThemeIcon = theme === 'light' ? Sun : theme === 'dark' ? Moon : Monitor;
  const themeName = t(theme === 'light' ? 'rail.themeLight' : theme === 'dark' ? 'rail.themeDark' : 'rail.themeSystem');

  const openSession = (id: string | null) => {
    setActiveTabId(id);
    navigate('/agent/terminal');
  };

  return (
    <>
      {/* Phone: a slim top bar, with the destinations along the bottom. */}
      {!desktop && (
        <div className="flex items-center gap-2 border-b border-border bg-card px-3 py-2">
          <div className="min-w-0 flex-1"><WorkspaceSwitcher variant="rail" /></div>
          <CommandPalette variant="icon" />
        </div>
      )}

      {desktop && (
      <aside className="flex w-[252px] shrink-0 flex-col gap-1 border-r border-border bg-card px-2.5 py-3">
        <WorkspaceSwitcher variant="rail" />
        <div className="mb-2 mt-1"><CommandPalette variant="rail" /></div>

        <nav aria-label={t('nav.primary')} className="flex flex-col gap-0.5">
          {primaryNav.map(item => {
            const active = isActive(pathname, item.matchPrefix);
            const badge = item.matchPrefix === '/agent' && tabs.length > 0 ? tabs.length : null;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                aria-current={active ? 'page' : undefined}
                className={`flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm font-medium transition-colors ${
                  active ? 'bg-muted text-foreground' : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground'
                }`}
              >
                <item.icon size={17} className="shrink-0" />
                <span className="flex-1 truncate">{t(item.labelKey)}</span>
                {badge !== null && <span className="font-mono text-[11px] text-muted-foreground">{badge}</span>}
              </NavLink>
            );
          })}
        </nav>

        <div className="mb-1.5 mt-4 flex items-center justify-between px-2.5">
          <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{t('rail.running')}</h2>
          <button
            type="button"
            onClick={() => openSession(null)}
            aria-label={t('rail.newSession')}
            title={t('rail.newSession')}
            className="flex h-5 w-5 items-center justify-center rounded text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <Plus size={14} />
          </button>
        </div>
        <div className="custom-scrollbar flex min-h-0 flex-1 flex-col gap-px overflow-y-auto">
          {tabs.length === 0 && <p className="px-2.5 text-xs text-muted-foreground">{t('rail.noRunning')}</p>}
          {tabs.map(tab => {
            const engine = findEngine(tab.engine);
            const name = engine?.nameKey ? t(engine.nameKey) : (engine?.name ?? tab.engine);
            const current = pathname.startsWith('/agent/terminal') && tab.id === activeTabId;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => openSession(tab.id)}
                title={tab.cwd}
                aria-current={current ? 'true' : undefined}
                className={`grid grid-cols-[8px_minmax(0,1fr)] items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-left text-sm transition-colors ${
                  current ? 'bg-muted' : 'hover:bg-muted/60'
                }`}
              >
                <span className={`h-2 w-2 rounded-full ${rateLimitedTabIds.has(tab.id) ? 'bg-warn' : (engine?.dot ?? 'bg-slate-400')}`} />
                <span className="min-w-0">
                  <span className="block truncate font-medium">{name}</span>
                  <span className="block truncate font-mono text-[11px] text-muted-foreground">{workspaceLabel(tab.cwd)}</span>
                </span>
              </button>
            );
          })}
        </div>

        <div className="mt-2 flex items-center gap-2 border-t border-border px-1 pt-2.5 font-mono text-[11px] text-muted-foreground">
          <Meter label="CPU" value={metrics?.cpuPercent} />
          <Meter label="MEM" value={metrics?.memoryPercent} />
          <span className="flex-1" />
          <NotificationBell />
          <SystemPanel />
          <button
            type="button"
            onClick={cycleTheme}
            aria-label={t('rail.theme', { mode: themeName })}
            title={t('rail.theme', { mode: themeName })}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <ThemeIcon size={16} />
          </button>
        </div>
      </aside>
      )}

      {!desktop && (
      <nav
        aria-label={t('nav.primary')}
        className="order-last flex border-t border-border bg-card pb-[env(safe-area-inset-bottom,0px)]"
      >
        {primaryNav.map(item => {
          const active = isActive(pathname, item.matchPrefix);
          return (
            <NavLink
              key={item.to}
              to={item.to}
              aria-current={active ? 'page' : undefined}
              className={`flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] font-medium ${
                active ? 'text-foreground' : 'text-muted-foreground'
              }`}
            >
              <item.icon size={18} />
              <span className="max-w-full truncate">{t(item.labelKey)}</span>
            </NavLink>
          );
        })}
      </nav>
      )}
    </>
  );
}
