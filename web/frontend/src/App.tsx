import { lazy, Suspense, useEffect, useState } from 'react';
import { Navigate, NavLink, Route, Routes, useLocation } from 'react-router-dom';
import { Bot, Clock3, Home, History, Menu, Settings, X } from 'lucide-react';
import ManifestDrawer from './components/ManifestDrawer';
import ProjectSwitcher from './components/ProjectSwitcher';
import SectionLayout, { type SectionTab } from './components/SectionLayout';
import SystemPanel from './components/SystemPanel';

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
const ChatPage = lazy(() => import('./components/ChatPage'));
const CronPage = lazy(() => import('./components/CronPage'));
const McpPage = lazy(() => import('./components/McpPage'));

const primaryNav = [
  { to: '/home', matchPrefix: '/home', label: 'Home', icon: Home },
  { to: '/agent/web', matchPrefix: '/agent', label: 'Agent', icon: Bot },
  { to: '/automations/tasks', matchPrefix: '/automations', label: 'Automations', icon: Clock3 },
  { to: '/activity/history', matchPrefix: '/activity', label: 'Activity', icon: History },
  { to: '/settings/workspace', matchPrefix: '/settings', label: 'Settings', icon: Settings },
] as const;

const AGENT_TABS: SectionTab[] = [
  { to: '/agent/web', label: 'Web Agent' },
  { to: '/agent/terminal', label: 'Native Terminal' },
];

const AUTOMATION_TABS: SectionTab[] = [
  { to: '/automations/tasks', label: 'Tasks' },
  { to: '/automations/schedules', label: 'Schedules' },
];

const ACTIVITY_TABS: SectionTab[] = [
  { to: '/activity/history', label: 'History' },
  { to: '/activity/events', label: 'Events' },
  { to: '/activity/analytics', label: 'Analytics' },
  { to: '/activity/logs', label: 'Logs' },
];

const SETTINGS_TABS: SectionTab[] = [
  { to: '/settings/workspace', label: 'Workspace' },
  {
    to: '/settings/capabilities/skills',
    label: 'Capabilities',
    matchPrefix: '/settings/capabilities',
  },
  { to: '/settings/system', label: 'System' },
];

const CAPABILITY_TABS: SectionTab[] = [
  { to: '/settings/capabilities/skills', label: 'Skills' },
  { to: '/settings/capabilities/prompts', label: 'Prompts' },
  { to: '/settings/capabilities/hooks', label: 'Hooks' },
  { to: '/settings/capabilities/plugins', label: 'Plugins' },
  { to: '/settings/capabilities/mcp', label: 'MCP' },
];

const PAGE_LABELS: Record<string, string> = {
  '/home': 'Home',
  '/agent/web': 'Chat',
  '/agent/terminal': 'Launch',
  '/automations/tasks': 'Dashboard',
  '/automations/schedules': 'Cron',
  '/activity/history': 'Sessions',
  '/activity/events': 'Audit Trail',
  '/activity/analytics': 'Analytics',
  '/activity/logs': 'Logs',
  '/settings/workspace': 'Configuration',
  '/settings/capabilities/skills': 'Skills',
  '/settings/capabilities/prompts': 'Prompts',
  '/settings/capabilities/hooks': 'Hooks',
  '/settings/capabilities/plugins': 'Plugins',
  '/settings/capabilities/mcp': 'MCP Servers',
  '/settings/system': 'System',
};

function App() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const { pathname } = useLocation();
  const pageLabel = PAGE_LABELS[pathname] ?? 'CodeAgent';

  useEffect(() => {
    document.title = pageLabel === 'CodeAgent' ? pageLabel : `${pageLabel} - CodeAgent`;
  }, [pageLabel]);

  return (
    <div className="flex h-dvh min-h-0 flex-col overflow-hidden bg-transparent font-sans text-foreground">
      <div data-testid="app-shell" className="flex min-h-0 flex-1 gap-2 p-2 md:gap-4 md:p-4">
        <aside
          className={`${
            isSidebarOpen ? 'w-20 xl:w-64' : 'w-20 xl:w-24'
          } glass-card flex shrink-0 flex-col overflow-hidden transition-[width] duration-300`}
        >
          <div className="flex items-center justify-center border-b border-slate-100 p-4 xl:justify-between xl:p-8">
            {isSidebarOpen && (
              <span className="hidden text-2xl font-black uppercase tracking-tighter text-primary xl:inline">CodeAgent</span>
            )}
            <button
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              aria-label={isSidebarOpen ? 'Collapse navigation' : 'Expand navigation'}
              title={isSidebarOpen ? 'Collapse navigation' : 'Expand navigation'}
              className={`hidden rounded-xl border border-transparent p-2 text-slate-600 transition-colors hover:border-slate-100 hover:bg-slate-50 xl:block ${!isSidebarOpen && 'mx-auto'}`}
            >
              {isSidebarOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
            <span className="text-xl font-black text-primary xl:hidden" aria-label="CodeAgent">CA</span>
          </div>

          <nav aria-label="Primary navigation" className="custom-scrollbar mt-2 min-h-0 flex-1 space-y-2 overflow-y-auto p-2 xl:mt-4 xl:p-4">
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
                  className={`flex w-full items-center justify-center gap-4 rounded-2xl p-3 transition-colors xl:justify-start xl:p-4 ${
                    active
                      ? 'bg-primary/10 font-semibold text-primary'
                      : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900'
                  }`}
                >
                  <item.icon size={22} className={`shrink-0 ${active ? 'opacity-100' : 'opacity-70'}`} />
                  {isSidebarOpen && (
                    <span className="hidden text-sm font-medium tracking-wide xl:inline">{item.label}</span>
                  )}
                </NavLink>
              );
            })}
          </nav>

          <div className="border-t border-slate-100 bg-slate-50/50 p-3 text-center text-[10px] font-medium uppercase tracking-widest text-slate-400 xl:p-6 xl:text-xs">
            <span className="xl:hidden">v1.0</span>
            <span className="hidden xl:inline">{isSidebarOpen ? '© 2026 CodeAgent SYSTEM v1.0' : 'v1.0'}</span>
          </div>
        </aside>

        <main className="relative flex min-w-0 flex-1 flex-col gap-3 overflow-hidden md:gap-4">
          <header className="flex min-w-0 items-center justify-between gap-3">
            <h1 className="min-w-0 truncate text-lg font-bold text-slate-800 md:text-xl">{pageLabel}</h1>
            <ProjectSwitcher />
          </header>
          <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto pr-1 md:pr-2">
            <Suspense fallback={<div className="p-8 text-sm text-slate-400">Loading…</div>}>
              <Routes>
                <Route path="/" element={<Navigate to="/home" replace />} />
                <Route path="/home" element={<HomePage />} />

                <Route
                  path="/agent"
                  element={<SectionLayout label="Agent" description="Conversations and native provider terminals in one workspace." tabs={AGENT_TABS} />}
                >
                  <Route index element={<Navigate to="web" replace />} />
                  <Route path="web" element={<ChatPage />} />
                  <Route path="terminal" element={<LaunchPad />} />
                </Route>

                <Route
                  path="/automations"
                  element={<SectionLayout label="Automations" description="Run repeatable work and manage schedules." tabs={AUTOMATION_TABS} />}
                >
                  <Route index element={<Navigate to="tasks" replace />} />
                  <Route path="tasks" element={<TaskDashboard />} />
                  <Route path="schedules" element={<CronPage />} />
                </Route>

                <Route
                  path="/activity"
                  element={<SectionLayout label="Activity" description="Conversation history, agent events, usage, and logs." tabs={ACTIVITY_TABS} />}
                >
                  <Route index element={<Navigate to="history" replace />} />
                  <Route path="history" element={<SessionsPage />} />
                  <Route path="events" element={<AuditTrail />} />
                  <Route path="analytics" element={<Analytics />} />
                  <Route path="logs" element={<LogViewer />} />
                </Route>

                <Route
                  path="/settings"
                  element={<SectionLayout label="Settings" description="Workspace configuration, capabilities, and system health." tabs={SETTINGS_TABS} />}
                >
                  <Route index element={<Navigate to="workspace" replace />} />
                  <Route path="workspace" element={<ConfigHub />} />
                  <Route
                    path="capabilities"
                    element={<SectionLayout label="Capabilities" description="Resources configured for the selected project group." tabs={CAPABILITY_TABS} />}
                  >
                    <Route index element={<Navigate to="skills" replace />} />
                    <Route path="skills" element={<SkillGallery />} />
                    <Route path="prompts" element={<PromptsGallery />} />
                    <Route path="hooks" element={<HooksGallery />} />
                    <Route path="plugins" element={<PluginGallery />} />
                    <Route path="mcp" element={<McpPage />} />
                  </Route>
                  <Route path="system" element={<SystemPage />} />
                </Route>

                <Route path="/launch" element={<Navigate to="/agent/terminal" replace />} />
                <Route path="/chat" element={<Navigate to="/agent/web" replace />} />
                <Route path="/dashboard" element={<Navigate to="/automations/tasks" replace />} />
                <Route path="/cron" element={<Navigate to="/automations/schedules" replace />} />
                <Route path="/logs" element={<Navigate to="/activity/logs" replace />} />
                <Route path="/analytics" element={<Navigate to="/activity/analytics" replace />} />
                <Route path="/sessions" element={<Navigate to="/activity/history" replace />} />
                <Route path="/audit" element={<Navigate to="/activity/events" replace />} />
                <Route path="/skills" element={<Navigate to="/settings/capabilities/skills" replace />} />
                <Route path="/prompts" element={<Navigate to="/settings/capabilities/prompts" replace />} />
                <Route path="/hooks" element={<Navigate to="/settings/capabilities/hooks" replace />} />
                <Route path="/plugins" element={<Navigate to="/settings/capabilities/plugins" replace />} />
                <Route path="/mcp" element={<Navigate to="/settings/capabilities/mcp" replace />} />
                <Route path="/config" element={<Navigate to="/settings/workspace" replace />} />
                <Route path="/system" element={<Navigate to="/settings/system" replace />} />
                <Route path="*" element={<Navigate to="/home" replace />} />
              </Routes>
            </Suspense>
          </div>
        </main>

        <ManifestDrawer />
      </div>
      <SystemPanel />
    </div>
  );
}

export default App;
