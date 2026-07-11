import { lazy, Suspense, useState } from 'react';
import { NavLink, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Box, Settings, Activity, Menu, X, Anchor, Zap, GitBranch, TrendingUp, Rocket, Terminal, FileText, Cpu } from 'lucide-react';
import ProjectSwitcher from './components/ProjectSwitcher';
import ManifestDrawer from './components/ManifestDrawer';
import SystemPanel from './components/SystemPanel';
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

const navItems = [
  { path: '/launch', label: 'Launch', icon: Rocket },
  { path: '/skills', label: 'Skills', icon: Box },
  { path: '/prompts', label: 'Prompts', icon: GitBranch },
  { path: '/hooks', label: 'Hooks', icon: Anchor },
  { path: '/plugins', label: 'Plugins', icon: Zap },
  { path: '/config', label: 'Configuration', icon: Settings },
  { path: '/dashboard', label: 'Dashboard', icon: Activity },
  { path: '/logs', label: 'Logs', icon: Terminal },
  { path: '/analytics', label: 'Analytics', icon: TrendingUp },
  { path: '/sessions', label: 'Sessions', icon: FileText },
  { path: '/system', label: 'System', icon: Cpu },
] as const;

const PAGE_LABELS: Record<string, string> = {
  '/launch': 'Launch',
  '/skills': 'Skills',
  '/prompts': 'Prompts',
  '/hooks': 'Hooks',
  '/plugins': 'Plugins',
  '/config': 'Configuration',
  '/dashboard': 'Dashboard',
  '/logs': 'Logs',
  '/analytics': 'Analytics',
  '/sessions': 'Sessions',
  '/system': 'System',
};

function App() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const { pathname } = useLocation();
  const pageLabel = PAGE_LABELS[pathname] ?? '';

  return (
    <div className="flex h-screen bg-transparent text-foreground overflow-hidden font-sans p-4 gap-4">
      {/* Sidebar */}
      <aside
        className={`${
          isSidebarOpen ? 'w-64' : 'w-24'
        } glass-card transition-all duration-500 flex flex-col overflow-hidden`}
      >
        <div className="p-8 flex items-center justify-between border-b border-slate-100">
          {isSidebarOpen && <span className="font-black text-2xl tracking-tighter text-primary uppercase">CodeAgent</span>}
          <button
            onClick={() => setIsSidebarOpen(!isSidebarOpen)}
            className={`p-2 hover:bg-slate-50 rounded-xl transition-all text-slate-600 border border-transparent hover:border-slate-100 ${!isSidebarOpen && 'mx-auto'}`}
          >
            {isSidebarOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>

        <nav className="flex-1 p-4 space-y-1 mt-6">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                `w-full flex items-center gap-4 p-4 rounded-2xl transition-all ${
                  isActive
                    ? 'bg-primary/10 text-primary font-semibold'
                    : 'hover:bg-slate-50 text-slate-500 hover:text-slate-900'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <item.icon size={22} className={isActive ? 'opacity-100' : 'opacity-70'} />
                  {isSidebarOpen && <span className="font-medium tracking-wide text-sm">{item.label}</span>}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="p-6 border-t border-slate-100 text-[10px] font-medium text-slate-400 text-center uppercase tracking-widest bg-slate-50/50">
          {isSidebarOpen ? '© 2026 CodeAgent SYSTEM v1.0' : 'v1.0'}
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-hidden relative flex flex-col gap-4 pb-8">
        <header className="flex items-center justify-between">
          <h2 className="text-xl font-bold text-slate-800">{pageLabel}</h2>
          <ProjectSwitcher />
        </header>
        <div className="flex-1 min-h-0 overflow-y-auto pr-2 custom-scrollbar">
          <Suspense fallback={<div className="p-8 text-sm text-slate-400">Loading…</div>}>
            <Routes>
              <Route path="/" element={<Navigate to="/launch" replace />} />
              <Route path="/launch" element={<LaunchPad />} />
              <Route path="/skills" element={<SkillGallery />} />
              <Route path="/prompts" element={<PromptsGallery />} />
              <Route path="/hooks" element={<HooksGallery />} />
              <Route path="/plugins" element={<PluginGallery />} />
              <Route path="/config" element={<ConfigHub />} />
              <Route path="/dashboard" element={<TaskDashboard />} />
              <Route path="/logs" element={<LogViewer />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/sessions" element={<SessionsPage />} />
              <Route path="/system" element={<SystemPage />} />
            </Routes>
          </Suspense>
        </div>
      </main>

      <ManifestDrawer />
      <SystemPanel />
    </div>
  );
}

export default App;
