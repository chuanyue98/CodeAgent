import { Bot, Clock3, Home, History, Settings, type LucideIcon } from 'lucide-react';
import type { SectionTab } from './components/SectionLayout';

export interface PrimaryNavItem {
  to: string;
  matchPrefix: string;
  label: string;
  icon: LucideIcon;
}

export const primaryNav: PrimaryNavItem[] = [
  { to: '/home', matchPrefix: '/home', label: 'Home', icon: Home },
  { to: '/agent/web', matchPrefix: '/agent', label: 'Agent', icon: Bot },
  { to: '/automations/tasks', matchPrefix: '/automations', label: 'Automations', icon: Clock3 },
  { to: '/activity/history', matchPrefix: '/activity', label: 'Activity', icon: History },
  { to: '/settings/workspace', matchPrefix: '/settings', label: 'Settings', icon: Settings },
];

export const AGENT_TABS: SectionTab[] = [
  { to: '/agent/web', label: 'Web Agent' },
  { to: '/agent/terminal', label: 'Native Terminal' },
];

export const AUTOMATION_TABS: SectionTab[] = [
  { to: '/automations/tasks', label: 'Tasks' },
  { to: '/automations/schedules', label: 'Schedules' },
];

export const ACTIVITY_TABS: SectionTab[] = [
  { to: '/activity/history', label: 'History' },
  { to: '/activity/events', label: 'Events' },
  { to: '/activity/analytics', label: 'Analytics' },
  { to: '/activity/logs', label: 'Logs' },
];

export const SETTINGS_TABS: SectionTab[] = [
  { to: '/settings/workspace', label: 'Workspace' },
  {
    to: '/settings/capabilities/skills',
    label: 'Capabilities',
    matchPrefix: '/settings/capabilities',
  },
  { to: '/settings/system', label: 'System' },
];

export const CAPABILITY_TABS: SectionTab[] = [
  { to: '/settings/capabilities/skills', label: 'Skills' },
  { to: '/settings/capabilities/prompts', label: 'Prompts' },
  { to: '/settings/capabilities/hooks', label: 'Hooks' },
  { to: '/settings/capabilities/plugins', label: 'Plugins' },
  { to: '/settings/capabilities/mcp', label: 'MCP' },
];

// Flat map of every leaf route to its display label. Also doubles as the
// destination list for the command palette, so keep it exhaustive.
export const PAGE_LABELS: Record<string, string> = {
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
