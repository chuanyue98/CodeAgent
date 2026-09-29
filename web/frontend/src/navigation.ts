import { Activity, Clock3, History, Puzzle, Settings, SquareTerminal, type LucideIcon } from 'lucide-react';
import type { SectionTab } from './components/SectionLayout';
import type { TranslationKey } from './i18n/locales/en';

export interface PrimaryNavItem {
  to: string;
  matchPrefix: string;
  labelKey: TranslationKey;
  /** One line on what the section is for; the app header shows it under the
      title, where it sits next to the thing it describes. */
  descriptionKey: TranslationKey;
  icon: LucideIcon;
}

// Routes carry translation keys, not labels: this module is imported by
// non-component code (the command palette's item list, the document title)
// where there is no hook to call, and a label baked in here would freeze the
// nav in whichever language happened to be active at import time.
export const primaryNav: PrimaryNavItem[] = [
  { to: '/home', matchPrefix: '/home', labelKey: 'nav.home', descriptionKey: 'section.home.description', icon: Activity },
  { to: '/agent/terminal', matchPrefix: '/agent', labelKey: 'nav.agent', descriptionKey: 'section.agent.description', icon: SquareTerminal },
  { to: '/activity/sessions', matchPrefix: '/activity', labelKey: 'nav.activity', descriptionKey: 'section.activity.description', icon: History },
  { to: '/automations/tasks', matchPrefix: '/automations', labelKey: 'nav.automations', descriptionKey: 'section.automations.description', icon: Clock3 },
  { to: '/extensions/resources', matchPrefix: '/extensions', labelKey: 'nav.extensions', descriptionKey: 'section.extensions.description', icon: Puzzle },
  { to: '/settings/workspace', matchPrefix: '/settings', labelKey: 'nav.settings', descriptionKey: 'section.settings.description', icon: Settings },
];

// The terminal streams the engine's own TUI, so it has every feature the vendor
// ships — model pickers, slash commands, approvals — the moment they ship it.
// A chat rendered over the gateway's structured events could only ever cover
// what its four per-engine adapters implemented, which is why the Web Agent tab
// that sat here was retired. Its session list lives on as the terminal's own
// sidebar, reading engine-native history rather than the gateway's store.
export const AGENT_TABS: SectionTab[] = [
  { to: '/agent/terminal', labelKey: 'tab.agent.terminal' },
  { to: '/agent/instances', labelKey: 'tab.agent.instances' },
  { to: '/agent/delegations', labelKey: 'tab.agent.delegations' },
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

// Two views that answer different questions: Sessions is a list of objects,
// Usage is numbers. Timeline (a flat event feed) was removed -- its only
// distinct capability, searching content across sessions, searched a capped
// client-side window and so could not answer the question it existed for.
export const ACTIVITY_TABS: SectionTab[] = [
  { to: '/activity/sessions', labelKey: 'tab.activity.sessions' },
  { to: '/activity/usage', labelKey: 'tab.activity.usage' },
];

// Query params holding Activity's filter state (see useActivityFilters).
// SectionLayout carries these across the Activity tabs so narrowing the view
// on History and switching to Events keeps what you selected. Deep-link
// params that identify one session are deliberately absent — those point at a
// single row and shouldn't leak into a sibling tab's filters.
export const ACTIVITY_FILTER_PARAMS = ['q', 'from', 'to', 'engines', 'types', 'project'];

// Skills/Prompts/Hooks/Plugins are one Resources page, because they are one
// question -- "what is this group running?" -- that four tabs could only
// answer four times. MCP stays separate: it is scoped per engine, not per
// group, so it does not belong under the same group selector.
export const EXTENSION_TABS: SectionTab[] = [
  { to: '/extensions/resources', labelKey: 'tab.settings.resources' },
  { to: '/extensions/mcp', labelKey: 'tab.settings.mcp' },
];

export const SETTINGS_TABS: SectionTab[] = [
  { to: '/settings/workspace', labelKey: 'tab.settings.workspace' },
  { to: '/settings/system', labelKey: 'tab.settings.system' },
];

// Flat map of every leaf route to its label key. Also doubles as the
// destination list for the command palette, so keep it exhaustive.
export const PAGE_LABEL_KEYS: Record<string, TranslationKey> = {
  '/home': 'nav.home',
  '/agent/terminal': 'tab.agent.terminal',
  '/agent/instances': 'tab.agent.instances',
  '/agent/delegations': 'tab.agent.delegations',
  '/automations/tasks': 'tab.automations.tasks',
  '/automations/schedules': 'tab.automations.schedules',
  '/automations/logs': 'tab.automations.logs',
  '/activity/sessions': 'tab.activity.sessions',
  '/activity/usage': 'tab.activity.usage',
  '/settings/workspace': 'tab.settings.workspace',
  '/extensions/resources': 'tab.settings.resources',
  '/extensions/mcp': 'tab.settings.mcp',
  '/settings/system': 'tab.settings.system',
};
