import { TerminalProvider } from "./context/TerminalContext";
import GlobalTerminalDrawer from "./components/GlobalTerminalDrawer";
import { lazy, Suspense, useEffect, type ReactNode } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router';
import SectionLayout from './components/SectionLayout';
import AppRail from './components/shell/AppRail';
import ErrorBoundary from './components/shared/ErrorBoundary';
import ErrorBar from './components/shared/ErrorBar';
import { useProject } from './context/ProjectContext';
import { useT } from './i18n/context';
import {
  ACTIVITY_FILTER_PARAMS,
  ACTIVITY_TABS,
  AGENT_TABS,
  AUTOMATION_TABS,
  EXTENSION_TABS,
  PAGE_LABEL_KEYS,
  SETTINGS_TABS,
} from './navigation';

const HomePage = lazy(() => import('./pages/HomePage'));
const ConfigHub = lazy(() => import('./components/ConfigHub'));
const TaskDashboard = lazy(() => import('./components/TaskDashboard'));
const ResourceHub = lazy(() => import('./components/ResourceHub'));
const Analytics = lazy(() => import('./components/Analytics'));
const LaunchPad = lazy(() => import('./components/LaunchPad'));
const InstancesPage = lazy(() => import('./components/InstancesPage'));
const DelegationsPage = lazy(() => import('./components/DelegationsPage'));
const LogViewer = lazy(() => import('./components/LogViewer'));
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
  return (
    <TerminalProvider>
      <AppShell />
    </TerminalProvider>
  );
}

function AppShell() {
  const { pathname } = useLocation();
  const { error: ctxError } = useProject();
  const t = useT();
  const pageLabelKey = PAGE_LABEL_KEYS[pathname];
  const pageLabel = pageLabelKey ? t(pageLabelKey) : 'CodeAgent';

  useEffect(() => {
    document.title = pageLabel === 'CodeAgent' ? pageLabel : `${pageLabel} - CodeAgent`;
  }, [pageLabel]);

  return (
    <div data-testid="app-shell" className="flex h-dvh min-h-0 flex-col overflow-hidden bg-background font-sans text-foreground md:flex-row">
      <AppRail />

      <main className="relative flex min-h-0 min-w-0 flex-1 flex-col">
        {ctxError && (
          <div className="px-4 pt-3 md:px-8">
            <ErrorBar message={t('app.configError', { message: ctxError })} />
          </div>
        )}
        <div className="min-h-0 flex-1 overflow-y-auto">
          <Routes>
            <Route path="/" element={<Navigate to="/home" replace />} />
            <Route path="/home" element={page(<HomePage />)} />

            <Route
              path="/agent"
              element={<SectionLayout labelKey="nav.agent" tabs={AGENT_TABS} bleedPaths={['/agent/terminal']} />}
            >
              <Route index element={<Navigate to="terminal" replace />} />
              <Route path="terminal" element={page(<LaunchPad />)} />
              <Route path="instances" element={page(<InstancesPage />)} />
              <Route path="delegations" element={page(<DelegationsPage />)} />
            </Route>

            <Route
              path="/activity"
              element={<SectionLayout labelKey="nav.activity" tabs={ACTIVITY_TABS} preserveParams={ACTIVITY_FILTER_PARAMS} />}
            >
              <Route index element={<Navigate to="sessions" replace />} />
              <Route path="sessions" element={page(<SessionsPage />)} />
              <Route path="usage" element={page(<Analytics />)} />
            </Route>

            {/* Logs live under Automations: they are the run logs of the tasks
                on the Tasks tab, keyed by task id, and read best next to the
                task that produced them. */}
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
              path="/extensions"
              element={<SectionLayout labelKey="nav.extensions" tabs={EXTENSION_TABS} />}
            >
              <Route index element={<Navigate to="resources" replace />} />
              <Route path="resources" element={page(<ResourceHub />)} />
              <Route path="mcp" element={page(<McpPage />)} />
            </Route>

            <Route
              path="/settings"
              element={<SectionLayout labelKey="nav.settings" tabs={SETTINGS_TABS} />}
            >
              <Route index element={<Navigate to="workspace" replace />} />
              <Route path="workspace" element={page(<ConfigHub />)} />
            </Route>

            {/* Older bookmarks. Query strings are carried where a page reads
                them (History's filters, Resources' ?kind= / ?group=). */}
            <Route path="/settings/resources" element={<KeepQuery to="/extensions/resources" />} />
            <Route path="/settings/mcp" element={<KeepQuery to="/extensions/mcp" />} />
            <Route path="/launch" element={<Navigate to="/agent/terminal" replace />} />
            <Route path="/chat" element={<Navigate to="/agent/terminal" replace />} />
            <Route path="/agent/legacy" element={<Navigate to="/agent/terminal" replace />} />
            <Route path="/agent/web" element={<Navigate to="/agent/terminal" replace />} />
            <Route path="/dashboard" element={<Navigate to="/automations/tasks" replace />} />
            <Route path="/cron" element={<Navigate to="/automations/schedules" replace />} />
            <Route path="/logs" element={<Navigate to="/automations/logs" replace />} />
            <Route path="/activity/logs" element={<Navigate to="/automations/logs" replace />} />
            <Route path="/activity/history" element={<KeepQuery to="/activity/sessions" />} />
            <Route path="/activity/timeline" element={<KeepQuery to="/activity/sessions" />} />
            <Route path="/activity/events" element={<KeepQuery to="/activity/sessions" />} />
            <Route path="/activity/analytics" element={<KeepQuery to="/activity/usage" />} />
            <Route path="/analytics" element={<KeepQuery to="/activity/usage" />} />
            <Route path="/sessions" element={<KeepQuery to="/activity/sessions" />} />
            <Route path="/audit" element={<KeepQuery to="/activity/sessions" />} />
            {(['skills', 'prompts', 'hooks', 'plugins'] as const).flatMap(kind => [
              <Route key={`/${kind}`} path={`/${kind}`} element={<Navigate to={`/extensions/resources?kind=${kind}`} replace />} />,
              <Route key={`/settings/${kind}`} path={`/settings/${kind}`} element={<Navigate to={`/extensions/resources?kind=${kind}`} replace />} />,
              <Route key={`/settings/capabilities/${kind}`} path={`/settings/capabilities/${kind}`} element={<Navigate to={`/extensions/resources?kind=${kind}`} replace />} />,
            ])}
            <Route path="/mcp" element={<Navigate to="/extensions/mcp" replace />} />
            <Route path="/settings/capabilities" element={<Navigate to="/extensions/resources" replace />} />
            <Route path="/settings/capabilities/mcp" element={<KeepQuery to="/extensions/mcp" />} />
            <Route path="/config" element={<Navigate to="/settings/workspace" replace />} />
            {/* System health is a section of the Settings page now. */}
            <Route path="/system" element={<Navigate to="/settings/workspace?tab=system" replace />} />
            <Route path="/settings/system" element={<Navigate to="/settings/workspace?tab=system" replace />} />
            <Route path="*" element={<Navigate to="/home" replace />} />
          </Routes>
        </div>
      </main>

      <GlobalTerminalDrawer />
    </div>
  );
}

export default App;
