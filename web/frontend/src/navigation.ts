import { Bot, Clock3, Home, History, Settings, type LucideIcon } from 'lucide-react';
import type { SectionTab } from './components/SectionLayout';
import type { TranslationKey } from './i18n/locales/en';

export interface PrimaryNavItem {
  to: string;
  matchPrefix: string;
  labelKey: TranslationKey;
  icon: LucideIcon;
}

// Routes carry translation keys, not labels: this module is imported by
// non-component code (the command palette's item list, the document title)
// where there is no hook to call, and a label baked in here would freeze the
// nav in whichever language happened to be active at import time.
export const primaryNav: PrimaryNavItem[] = [
  { to: '/home', matchPrefix: '/home', labelKey: 'nav.home', icon: Home },
  { to: '/agent/web', matchPrefix: '/agent', labelKey: 'nav.agent', icon: Bot },
  { to: '/automations/tasks', matchPrefix: '/automations', labelKey: 'nav.automations', icon: Clock3 },
  { to: '/activity/sessions', matchPrefix: '/activity', labelKey: 'nav.activity', icon: History },
  { to: '/settings/workspace', matchPrefix: '/settings', labelKey: 'nav.settings', icon: Settings },
];

export const AGENT_TABS: SectionTab[] = [
  { to: '/agent/web', labelKey: 'tab.agent.web' },
  { to: '/agent/terminal', labelKey: 'tab.agent.terminal' },
];

// Logs lives here, not under Activity: these are the run logs of the tasks
// on the Tasks tab, keyed by task id, and share no data or concepts with
// Activity's session history. Reading one only makes sense next to the task
// that produced it.
export const AUTOMATION_TABS: SectionTab[] = [
  { to: '/automations/tasks', labelKey: 'tab.automations.tasks' },
  { to: '/automations/schedules', labelKey: 'tab.automations.schedules' },
  { to: '/automations/logs', labelKey: 'tab.automations.logs' },
];

// Three nouns that don't overlap: Sessions is a list of objects, Timeline is
// a list of events, Usage is numbers. History/Events/Analytics all translated
// to roughly "records" and gave no hint which one answered which question.
export const ACTIVITY_TABS: SectionTab[] = [
  { to: '/activity/sessions', labelKey: 'tab.activity.sessions' },
  { to: '/activity/timeline', labelKey: 'tab.activity.timeline' },
  { to: '/activity/usage', labelKey: 'tab.activity.usage' },
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
  { to: '/settings/workspace', labelKey: 'tab.settings.workspace' },
  { to: '/settings/skills', labelKey: 'tab.settings.skills' },
  { to: '/settings/prompts', labelKey: 'tab.settings.prompts' },
  { to: '/settings/hooks', labelKey: 'tab.settings.hooks' },
  { to: '/settings/plugins', labelKey: 'tab.settings.plugins' },
  { to: '/settings/mcp', labelKey: 'tab.settings.mcp' },
  { to: '/settings/system', labelKey: 'tab.settings.system' },
];

// Flat map of every leaf route to its label key. Also doubles as the
// destination list for the command palette, so keep it exhaustive.
export const PAGE_LABEL_KEYS: Record<string, TranslationKey> = {
  '/home': 'nav.home',
  '/agent/web': 'tab.agent.web',
  '/agent/terminal': 'tab.agent.terminal',
  '/automations/tasks': 'tab.automations.tasks',
  '/automations/schedules': 'tab.automations.schedules',
  '/automations/logs': 'tab.automations.logs',
  '/activity/sessions': 'tab.activity.sessions',
  '/activity/timeline': 'tab.activity.timeline',
  '/activity/usage': 'tab.activity.usage',
  '/settings/workspace': 'tab.settings.workspace',
  '/settings/skills': 'tab.settings.skills',
  '/settings/prompts': 'tab.settings.prompts',
  '/settings/hooks': 'tab.settings.hooks',
  '/settings/plugins': 'tab.settings.plugins',
  '/settings/mcp': 'tab.settings.mcp',
  '/settings/system': 'tab.settings.system',
};
