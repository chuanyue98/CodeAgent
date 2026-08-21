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
  { to: '/activity/sessions', matchPrefix: '/activity', label: 'Activity', icon: History },
  { to: '/settings/workspace', matchPrefix: '/settings', label: 'Settings', icon: Settings },
];

export const AGENT_TABS: SectionTab[] = [
  { to: '/agent/web', label: 'Web Agent' },
  { to: '/agent/terminal', label: 'Local Terminal' },
];

// Logs lives here, not under Activity: these are the run logs of the tasks
// on the Tasks tab, keyed by task id, and share no data or concepts with
// Activity's session history. Reading one only makes sense next to the task
// that produced it.
export const AUTOMATION_TABS: SectionTab[] = [
  { to: '/automations/tasks', label: 'Tasks' },
  { to: '/automations/schedules', label: 'Schedules' },
  { to: '/automations/logs', label: 'Logs' },
];

// Three nouns that don't overlap: Sessions is a list of objects, Timeline is
// a list of events, Usage is numbers. History/Events/Analytics all translated
// to roughly "records" and gave no hint which one answered which question.
export const ACTIVITY_TABS: SectionTab[] = [
  { to: '/activity/sessions', label: 'Sessions' },
  { to: '/activity/timeline', label: 'Timeline' },
  { to: '/activity/usage', label: 'Usage' },
];

// Query params holding Activity's filter state (see useActivityFilters).
// SectionLayout carries these across the Activity tabs so narrowing the view
// on History and switching to Events keeps what you selected. Deep-link
// params that identify one session are deliberately absent — those point at a
// single row and shouldn't leak into a sibling tab's filters.
export const ACTIVITY_FILTER_PARAMS = ['q', 'from', 'to', 'engines', 'types', 'project'];

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
  '/agent/web': 'Web Agent',
  '/agent/terminal': 'Local Terminal',
  '/automations/tasks': 'Tasks',
  '/automations/schedules': 'Schedules',
  '/automations/logs': 'Logs',
  '/activity/sessions': 'Sessions',
  '/activity/timeline': 'Timeline',
  '/activity/usage': 'Usage',
  '/settings/workspace': 'Workspace',
  '/settings/capabilities/skills': 'Skills',
  '/settings/capabilities/prompts': 'Prompts',
  '/settings/capabilities/hooks': 'Hooks',
  '/settings/capabilities/plugins': 'Plugins',
  '/settings/capabilities/mcp': 'MCP',
  '/settings/system': 'System',
};
