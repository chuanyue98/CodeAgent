import { lazy, Suspense, useEffect, useState, type ReactNode } from 'react';
import { Navigate, NavLink, Route, Routes, useLocation } from 'react-router';
import { Menu, X, AlertCircle } from 'lucide-react';
import CommandPalette from './components/CommandPalette';
import ProjectSwitcher from './components/ProjectSwitcher';
import SectionLayout from './components/SectionLayout';
import SystemPanel from './components/SystemPanel';
import WorkspaceSwitcher from './components/WorkspaceSwitcher';
import ErrorBoundary from './components/shared/ErrorBoundary';
import { useProject } from './context/ProjectContext';
import {
  ACTIVITY_FILTER_PARAMS,
  ACTIVITY_TABS,
  AGENT_TABS,
  AUTOMATION_TABS,
  PAGE_LABELS,
  primaryNav,
  SETTINGS_TABS,
} from './navigation';

const HomePage = lazy(() => import('./pages/HomePage'));
const SystemPage = lazy(() => import('./pages/SystemPage'));
const SkillGallery = lazy(() => import('./components/SkillGallery'));
const ConfigHub = lazy(() => import('./components/ConfigHub'));
const TaskDashboard = lazy(() => import('./components/TaskDashboard'));
const HooksGallery = lazy(() => import('./components/HooksGallery'));
const PluginGallery = lazy(() => import('./components/PluginGallery'));
const PromptsGallery = lazy(() => import('./components/PromptsGallery'));
const Analytics = lazy(() => import('./components/Analytics'));
const LaunchPad = lazy(() => import('./components/LaunchPad'));
const LogViewer = lazy(() => import('./components/LogViewer'));
const SessionsPage = lazy(() => import('./components/SessionsPage'));
const AuditTrail = lazy(() => import('./components/AuditTrail'));
const AgentWorkspace = lazy(() => import('./pages/AgentWorkspace'));
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
  const pageLabel = PAGE_LABELS[pathname] ?? 'CodeAgent';

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
              aria-label={isSidebarOpen ? '折叠导航' : '展开导航'}
              title={isSidebarOpen ? '折叠导航' : '展开导航'}
              className={`hidden rounded-xl border border-transparent p-2 text-slate-600 transition-colors hover:border-slate-100 hover:bg-slate-50 lg:block ${!isSidebarOpen && 'mx-auto'}`}
            >
              {isSidebarOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
            <span className="text-xl font-black text-primary lg:hidden" aria-label="CodeAgent">CA</span>
          </div>

          <nav aria-label="主导航" className="custom-scrollbar mt-2 min-h-0 flex-1 space-y-2 overflow-y-auto p-2 lg:mt-4 lg:p-4">
            {primaryNav.map(item => {
              const active = pathname === item.matchPrefix
                || pathname.startsWith(`${item.matchPrefix}/`);
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  aria-label={item.label}
                  aria-current={active ? 'page' : undefined}
                  title={item.label}
                  className={`flex w-full items-center justify-center gap-4 rounded-2xl p-3 transition-colors lg:justify-start lg:p-4 ${
                    active
                      ? 'bg-primary/10 font-semibold text-primary'
                      : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900'
                  }`}
                >
                  <item.icon size={22} className={`shrink-0 ${active ? 'opacity-100' : 'opacity-70'}`} />
                  {isSidebarOpen && (
                    <span className="hidden text-sm font-medium tracking-wide lg:inline">{item.label}</span>
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
            <h1 className="min-w-0 truncate text-lg font-bold text-slate-800 md:text-xl">{pageLabel}</h1>
            <div className="flex shrink-0 items-center gap-2">
              <CommandPalette />
              <SystemPanel />
              <WorkspaceSwitcher />
              <ProjectSwitcher />
            </div>
          </header>
          {ctxError && (
            <div className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-2 text-sm font-medium text-red-600" role="alert">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>配置错误：{ctxError}</span>
            </div>
          )}
          <div className="animate-fade-in stagger-3 custom-scrollbar min-h-0 flex-1 overflow-y-auto pr-1 md:pr-2">
            <Routes>
              <Route path="/" element={<Navigate to="/home" replace />} />
              <Route path="/home" element={page(<HomePage />)} />

              <Route
                path="/agent"
                element={<SectionLayout label="Agent" description="会话与本地引擎终端，同在一个工作区。" tabs={AGENT_TABS} />}
              >
                <Route index element={<Navigate to="web" replace />} />
                <Route path="web" element={page(<AgentWorkspace />)} />
                <Route path="terminal" element={page(<LaunchPad />)} />
              </Route>

              <Route
                path="/automations"
                element={<SectionLayout label="自动化" description="运行可复用的任务、管理定时计划、查看运行日志。" tabs={AUTOMATION_TABS} />}
              >
                <Route index element={<Navigate to="tasks" replace />} />
                <Route path="tasks" element={page(<TaskDashboard />)} />
                <Route path="schedules" element={page(<CronPage />)} />
                <Route path="logs" element={page(<LogViewer />)} />
              </Route>

              <Route
                path="/activity"
                element={<SectionLayout label="动态" description="过往会话、事件时间线与用量。" tabs={ACTIVITY_TABS} preserveParams={ACTIVITY_FILTER_PARAMS} />}
              >
                <Route index element={<Navigate to="sessions" replace />} />
                <Route path="sessions" element={page(<SessionsPage />)} />
                <Route path="timeline" element={page(<AuditTrail />)} />
                <Route path="usage" element={page(<Analytics />)} />
              </Route>

              <Route
                path="/settings"
                element={<SectionLayout label="设置" description="工作区配置、能力资源与系统健康。" tabs={SETTINGS_TABS} />}
              >
                <Route index element={<Navigate to="workspace" replace />} />
                <Route path="workspace" element={page(<ConfigHub />)} />
                <Route path="skills" element={page(<SkillGallery />)} />
                <Route path="prompts" element={page(<PromptsGallery />)} />
                <Route path="hooks" element={page(<HooksGallery />)} />
                <Route path="plugins" element={page(<PluginGallery />)} />
                <Route path="mcp" element={page(<McpPage />)} />
                <Route path="system" element={page(<SystemPage />)} />
              </Route>

              <Route path="/launch" element={<Navigate to="/agent/terminal" replace />} />
              <Route path="/chat" element={<Navigate to="/agent/web" replace />} />
              {/* The legacy engine-direct Chat page was removed: Web Agent is
                  the only chat surface now. Old links land on it. */}
              <Route path="/agent/legacy" element={<Navigate to="/agent/web" replace />} />
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
              <Route path="/activity/events" element={<KeepQuery to="/activity/timeline" />} />
              <Route path="/activity/analytics" element={<KeepQuery to="/activity/usage" />} />
              <Route path="/analytics" element={<KeepQuery to="/activity/usage" />} />
              <Route path="/sessions" element={<KeepQuery to="/activity/sessions" />} />
              <Route path="/audit" element={<KeepQuery to="/activity/timeline" />} />
              <Route path="/skills" element={<Navigate to="/settings/skills" replace />} />
              <Route path="/prompts" element={<Navigate to="/settings/prompts" replace />} />
              <Route path="/hooks" element={<Navigate to="/settings/hooks" replace />} />
              <Route path="/plugins" element={<Navigate to="/settings/plugins" replace />} />
              <Route path="/mcp" element={<Navigate to="/settings/mcp" replace />} />
              {/* Settings' capability pages were flattened from
                  /settings/capabilities/<kind> to /settings/<kind>. */}
              <Route path="/settings/capabilities" element={<Navigate to="/settings/skills" replace />} />
              <Route path="/settings/capabilities/skills" element={<KeepQuery to="/settings/skills" />} />
              <Route path="/settings/capabilities/prompts" element={<KeepQuery to="/settings/prompts" />} />
              <Route path="/settings/capabilities/hooks" element={<KeepQuery to="/settings/hooks" />} />
              <Route path="/settings/capabilities/plugins" element={<KeepQuery to="/settings/plugins" />} />
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
