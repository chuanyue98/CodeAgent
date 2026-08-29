import { lazy, Suspense, useEffect, useState, type ReactNode } from 'react';
import { Navigate, NavLink, Route, Routes, useLocation } from 'react-router';
import { Menu, X, AlertCircle } from 'lucide-react';
import CommandPalette from './components/CommandPalette';
import SectionLayout from './components/SectionLayout';
import SystemPanel from './components/SystemPanel';
import WorkspaceSwitcher from './components/WorkspaceSwitcher';
import ErrorBoundary from './components/shared/ErrorBoundary';
import { useProject } from './context/ProjectContext';
import { useT } from './i18n/context';
import {
  ACTIVITY_FILTER_PARAMS,
  ACTIVITY_TABS,
  AGENT_TABS,
  AUTOMATION_TABS,
  PAGE_LABEL_KEYS,
  primaryNav,
  SETTINGS_TABS,
} from './navigation';

const HomePage = lazy(() => import('./pages/HomePage'));
const SystemPage = lazy(() => import('./pages/SystemPage'));
const ConfigHub = lazy(() => import('./components/ConfigHub'));
const TaskDashboard = lazy(() => import('./components/TaskDashboard'));
const ResourceHub = lazy(() => import('./components/ResourceHub'));
const Analytics = lazy(() => import('./components/Analytics'));
const LaunchPad = lazy(() => import('./components/LaunchPad'));
const InstancesPage = lazy(() => import('./components/InstancesPage'));const LogViewer = lazy(() => import('./components/LogViewer'));
const SessionsPage = lazy(() => import('./components/SessionsPage'));
const CronPage = lazy(() => import('./components/CronPage'));
const McpPage = lazy(() => import('./components/McpPage'));

const routeFallback = (
  <div className="flex h-96 items-center justify-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" /></div>
);

/**
 * Gives each lazy-loaded page its own error + suspense boundary, so a
 * render error (or a slow chunk load) in one page can't blank the whole
 * app shell (nav/sidebar/other pages stay interactive).
 */
function page(element: ReactNode) {
  return (
    <ErrorBoundary>
      <Suspense fallback={routeFallback}>{element}</Suspense>
    </ErrorBoundary>
  );
}

/**
 * Redirect that carries the query string over. A bare `<Navigate to="/x">`
 * drops it, which would silently strip Activity's filters and the params that
 * open one session's detail from an old bookmark.
 */
function KeepQuery({ to }: { to: string }) {
  const { search } = useLocation();
  return <Navigate to={`${to}${search}`} replace />;
}

function App() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const { pathname } = useLocation();
  const { error: ctxError } = useProject();
  const t = useT();
  const pageLabelKey = PAGE_LABEL_KEYS[pathname];
  const pageLabel = pageLabelKey ? t(pageLabelKey) : 'CodeAgent';
  // The heading names the section, not the leaf: the leaf is already the
  // selected chip in the tab row directly below it, and printing the same
  // word twice, one above the other, spent the page's most prominent line on
  // nothing. The document title keeps the leaf -- a browser tab has no tab
  // row to read it off.
  const section = primaryNav.find(
    item => pathname === item.matchPrefix || pathname.startsWith(`${item.matchPrefix}/`),
  );

  useEffect(() => {
    document.title = pageLabel === 'CodeAgent' ? pageLabel : `${pageLabel} - CodeAgent`;
  }, [pageLabel]);

  return (
    <div className="flex h-dvh min-h-0 flex-col overflow-hidden bg-transparent font-sans text-foreground">
      <div data-testid="app-shell" className="flex min-h-0 flex-1 gap-2 p-2 md:gap-4 md:p-4">
        <aside
          className={`animate-fade-in stagger-1 ${
            isSidebarOpen ? 'w-20 xl:w-64' : 'w-20 xl:w-24'
          } glass-card flex shrink-0 flex-col overflow-hidden transition-[width] duration-300`}
        >
          <div className="flex items-center justify-center border-b border-slate-100 p-4 lg:justify-between lg:p-8">
            {isSidebarOpen && (
              <span className="hidden text-2xl font-black uppercase tracking-tighter text-primary lg:inline">CodeAgent</span>
            )}
            <button
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              aria-label={isSidebarOpen ? t('nav.collapse') : t('nav.expand')}
              title={isSidebarOpen ? t('nav.collapse') : t('nav.expand')}
              className={`hidden rounded-xl border border-transparent p-2 text-slate-600 transition-colors hover:border-slate-100 hover:bg-slate-50 lg:block ${!isSidebarOpen && 'mx-auto'}`}
            >
              {isSidebarOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
            <span className="text-xl font-black text-primary lg:hidden" aria-label="CodeAgent">CA</span>
          </div>

          <nav aria-label={t('nav.primary')} className="custom-scrollbar mt-2 min-h-0 flex-1 space-y-2 overflow-y-auto p-2 lg:mt-4 lg:p-4">
            {primaryNav.map(item => {
              const active = pathname === item.matchPrefix
                || pathname.startsWith(`${item.matchPrefix}/`);
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  aria-label={t(item.labelKey)}
                  aria-current={active ? 'page' : undefined}
                  title={t(item.labelKey)}
                  className={`flex w-full items-center justify-center gap-4 rounded-2xl p-3 transition-colors lg:justify-start lg:p-4 ${
                    active
                      ? 'bg-primary/10 font-semibold text-primary'
                      : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900'
                  }`}
                >
                  <item.icon size={22} className={`shrink-0 ${active ? 'opacity-100' : 'opacity-70'}`} />
                  {isSidebarOpen && (
                    <span className="hidden text-sm font-medium tracking-wide lg:inline">{t(item.labelKey)}</span>
                  )}
                </NavLink>
              );
            })}
          </nav>

          {/* Kept to one short line: the old uppercase "© 2026 CODEAGENT
              SYSTEM V1.0" wrapped onto two rows and read louder than the nav. */}
          <div className="border-t border-slate-100 bg-slate-50/50 p-3 text-center text-[10px] font-medium tracking-wide text-slate-400 lg:p-4">
            v1.0
          </div>
        </aside>

        <main className="relative flex min-w-0 flex-1 flex-col gap-3 overflow-hidden md:gap-4">
          <header className="animate-fade-in stagger-2 relative z-50 flex min-w-0 items-center justify-between gap-3">
            <div className="min-w-0">
              <h1 className="truncate text-lg font-bold text-slate-800 md:text-xl">
                {section ? t(section.labelKey) : pageLabel}
              </h1>
              {section && (
                <p
                  title={t(section.descriptionKey)}
                  className="hidden truncate text-xs text-slate-400 sm:block"
                >
                  {t(section.descriptionKey)}
                </p>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <CommandPalette />
              <SystemPanel />
              <WorkspaceSwitcher />
            </div>
          </header>
          {ctxError && (
            <div className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-2 text-sm font-medium text-red-600" role="alert">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{t('app.configError', { message: ctxError })}</span>
            </div>
          )}
          <div className="animate-fade-in stagger-3 custom-scrollbar min-h-0 flex-1 overflow-y-auto pr-1 md:pr-2">
            <Routes>
              <Route path="/" element={<Navigate to="/home" replace />} />
              <Route path="/home" element={page(<HomePage />)} />

              <Route
                path="/agent"
                element={<SectionLayout labelKey="nav.agent" tabs={AGENT_TABS} />}
              >
                <Route index element={<Navigate to="terminal" replace />} />
                <Route path="terminal" element={page(<LaunchPad />)} />
                <Route path="instances" element={page(<InstancesPage />)} />
              </Route>

              <Route
                path="/automations"
                element={<SectionLayout labelKey="nav.automations" tabs={AUTOMATION_TABS} />}
              >
                <Route index element={<Navigate to="tasks" replace />} />
                <Route path="tasks" element={page(<TaskDashboard />)} />
                <Route path="schedules" element={page(<CronPage />)} />
                <Route path="logs" element={page(<LogViewer />)} />
              </Route>

              <Route
                path="/activity"
                element={<SectionLayout labelKey="nav.activity" tabs={ACTIVITY_TABS} preserveParams={ACTIVITY_FILTER_PARAMS} />}
              >
                <Route index element={<Navigate to="sessions" replace />} />
                <Route path="sessions" element={page(<SessionsPage />)} />
                <Route path="usage" element={page(<Analytics />)} />
              </Route>

              <Route
                path="/settings"
                element={<SectionLayout labelKey="nav.settings" tabs={SETTINGS_TABS} />}
              >
                <Route index element={<Navigate to="workspace" replace />} />
                <Route path="workspace" element={page(<ConfigHub />)} />
                <Route path="resources" element={page(<ResourceHub />)} />
                <Route path="mcp" element={page(<McpPage />)} />
                <Route path="system" element={page(<SystemPage />)} />
              </Route>

              <Route path="/launch" element={<Navigate to="/agent/terminal" replace />} />
              {/* Two generations of chat surface have now been retired -- the
                  engine-direct Chat page, then the Web Agent that replaced it.
                  Old links land on the terminal, which is the surface that
                  outlived both. */}
              <Route path="/chat" element={<Navigate to="/agent/terminal" replace />} />
              <Route path="/agent/legacy" element={<Navigate to="/agent/terminal" replace />} />
              <Route path="/agent/web" element={<Navigate to="/agent/terminal" replace />} />
              <Route path="/dashboard" element={<Navigate to="/automations/tasks" replace />} />
              <Route path="/cron" element={<Navigate to="/automations/schedules" replace />} />
              <Route path="/logs" element={<Navigate to="/automations/logs" replace />} />
              {/* Logs moved out of Activity into Automations, where the tasks
                  that write them live. Keeps existing links working. */}
              <Route path="/activity/logs" element={<Navigate to="/automations/logs" replace />} />
              {/* Activity's tabs were renamed History/Events/Analytics ->
                  Sessions/Timeline/Usage. These carry the query string so a
                  saved filtered view or a session deep link still resolves. */}
              <Route path="/activity/history" element={<KeepQuery to="/activity/sessions" />} />
              {/* Timeline was removed. Its links carry the same
                  session/sessionEngine/sessionProject params Sessions reads,
                  so an old bookmark still opens the session it pointed at. */}
              <Route path="/activity/timeline" element={<KeepQuery to="/activity/sessions" />} />
              <Route path="/activity/events" element={<KeepQuery to="/activity/sessions" />} />
              <Route path="/activity/analytics" element={<KeepQuery to="/activity/usage" />} />
              <Route path="/analytics" element={<KeepQuery to="/activity/usage" />} />
              <Route path="/sessions" element={<KeepQuery to="/activity/sessions" />} />
              <Route path="/audit" element={<KeepQuery to="/activity/sessions" />} />
              <Route path="/skills" element={<Navigate to="/settings/resources?kind=skills" replace />} />
              <Route path="/prompts" element={<Navigate to="/settings/resources?kind=prompts" replace />} />
              <Route path="/hooks" element={<Navigate to="/settings/resources?kind=hooks" replace />} />
              <Route path="/plugins" element={<Navigate to="/settings/resources?kind=plugins" replace />} />
              <Route path="/settings/skills" element={<Navigate to="/settings/resources?kind=skills" replace />} />
              <Route path="/settings/prompts" element={<Navigate to="/settings/resources?kind=prompts" replace />} />
              <Route path="/settings/hooks" element={<Navigate to="/settings/resources?kind=hooks" replace />} />
              <Route path="/settings/plugins" element={<Navigate to="/settings/resources?kind=plugins" replace />} />
              <Route path="/mcp" element={<Navigate to="/settings/mcp" replace />} />
              {/* Settings' capability pages were flattened from
                  /settings/capabilities/<kind> to /settings/<kind>. */}
              <Route path="/settings/capabilities" element={<Navigate to="/settings/resources" replace />} />
              <Route path="/settings/capabilities/skills" element={<Navigate to="/settings/resources?kind=skills" replace />} />
              <Route path="/settings/capabilities/prompts" element={<Navigate to="/settings/resources?kind=prompts" replace />} />
              <Route path="/settings/capabilities/hooks" element={<Navigate to="/settings/resources?kind=hooks" replace />} />
              <Route path="/settings/capabilities/plugins" element={<Navigate to="/settings/resources?kind=plugins" replace />} />
              <Route path="/settings/capabilities/mcp" element={<KeepQuery to="/settings/mcp" />} />
              <Route path="/config" element={<Navigate to="/settings/workspace" replace />} />
              <Route path="/system" element={<Navigate to="/settings/system" replace />} />
              <Route path="*" element={<Navigate to="/home" replace />} />
            </Routes>
          </div>
        </main>

      </div>
    </div>
  );
}

export default App;
