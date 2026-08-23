import { Bot, Clock3, Home, History, Settings, type LucideIcon } from 'lucide-react';
import type { SectionTab } from './components/SectionLayout';

export interface PrimaryNavItem {
  to: string;
  matchPrefix: string;
  label: string;
  icon: LucideIcon;
}

export const primaryNav: PrimaryNavItem[] = [
  { to: '/home', matchPrefix: '/home', label: '首页', icon: Home },
  { to: '/agent/web', matchPrefix: '/agent', label: 'Agent', icon: Bot },
  { to: '/automations/tasks', matchPrefix: '/automations', label: '自动化', icon: Clock3 },
  { to: '/activity/sessions', matchPrefix: '/activity', label: '动态', icon: History },
  { to: '/settings/workspace', matchPrefix: '/settings', label: '设置', icon: Settings },
];

export const AGENT_TABS: SectionTab[] = [
  { to: '/agent/web', label: 'Web Agent' },
  { to: '/agent/terminal', label: '本地终端' },
];

// Logs lives here, not under Activity: these are the run logs of the tasks
// on the Tasks tab, keyed by task id, and share no data or concepts with
// Activity's session history. Reading one only makes sense next to the task
// that produced it.
export const AUTOMATION_TABS: SectionTab[] = [
  { to: '/automations/tasks', label: '任务' },
  { to: '/automations/schedules', label: '定时任务' },
  { to: '/automations/logs', label: '日志' },
];

// Three nouns that don't overlap: Sessions is a list of objects, Timeline is
// a list of events, Usage is numbers. History/Events/Analytics all translated
// to roughly "records" and gave no hint which one answered which question.
export const ACTIVITY_TABS: SectionTab[] = [
  { to: '/activity/sessions', label: '会话' },
  { to: '/activity/timeline', label: '时间线' },
  { to: '/activity/usage', label: '用量' },
];

// Query params holding Activity's filter state (see useActivityFilters).
// SectionLayout carries these across the Activity tabs so narrowing the view
// on History and switching to Events keeps what you selected. Deep-link
// params that identify one session are deliberately absent — those point at a
// single row and shouldn't leak into a sibling tab's filters.
export const ACTIVITY_FILTER_PARAMS = ['q', 'from', 'to', 'engines', 'types', 'project'];

// One flat row of Settings tabs. Capabilities used to be a nested second
// SectionLayout (two stacked tab rows) whose only job was grouping the five
// capability pages; folding them into this row costs no width and removes the
// only three-level navigation in the app.
export const SETTINGS_TABS: SectionTab[] = [
  { to: '/settings/workspace', label: '工作区' },
  { to: '/settings/skills', label: '技能' },
  { to: '/settings/prompts', label: '提示词' },
  { to: '/settings/hooks', label: '钩子' },
  { to: '/settings/plugins', label: '插件' },
  { to: '/settings/mcp', label: 'MCP' },
  { to: '/settings/system', label: '系统' },
];

// Flat map of every leaf route to its display label. Also doubles as the
// destination list for the command palette, so keep it exhaustive.
export const PAGE_LABELS: Record<string, string> = {
  '/home': '首页',
  '/agent/web': 'Web Agent',
  '/agent/terminal': '本地终端',
  '/automations/tasks': '任务',
  '/automations/schedules': '定时任务',
  '/automations/logs': '日志',
  '/activity/sessions': '会话',
  '/activity/timeline': '时间线',
  '/activity/usage': '用量',
  '/settings/workspace': '工作区',
  '/settings/skills': '技能',
  '/settings/prompts': '提示词',
  '/settings/hooks': '钩子',
  '/settings/plugins': '插件',
  '/settings/mcp': 'MCP',
  '/settings/system': '系统',
};
