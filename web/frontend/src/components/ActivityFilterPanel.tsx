import { FolderGit2, Search, X } from 'lucide-react';
import { useProject } from '../context/ProjectContext';
import { useT } from '../i18n/context';
import { ALL_PROJECTS, type ActivityFilters } from '../hooks/useActivityFilters';
import { findEngine } from './terminalEngines';

/** Last path segment, for a label that fits a select. */
function projectLabel(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).pop() || path;
}

interface ActivityFilterPanelProps {
  filters: ActivityFilters;
  /** Engine values to offer. Callers pass what their data actually contains. */
  engineOptions: string[];
  searchPlaceholder: string;
  /** Events has message/tool-call types; History has no equivalent axis. */
  showEventTypes?: boolean;
}

const CONTROL =
  'rounded-lg border border-border bg-card px-2.5 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none';

/**
 * History's filter bar: search, workspace, dates and one chip per engine, in a
 * single row that wraps. It used to be a 14rem sidebar that spent a third of
 * the page on a few controls. The state lives in the URL (useActivityFilters),
 * so switching tabs keeps what you typed.
 */
export default function ActivityFilterPanel({
  filters,
  engineOptions,
  searchPlaceholder,
  showEventTypes = false,
}: ActivityFilterPanelProps) {
  const { validProjects, selectedWorkspace } = useProject();
  const t = useT();

  // The switcher's workspace always belongs in the list even if it isn't a
  // registered project, otherwise the active filter has no visible option.
  const projectPaths = Array.from(
    new Set([selectedWorkspace, ...validProjects.map(p => p.path)].filter(Boolean)),
  );

  const activeProjectValue = filters.followsWorkspace
    ? selectedWorkspace
    : filters.project || ALL_PROJECTS;

  return (
    <div data-testid="activity-filters" className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <label className="sr-only" htmlFor="activity-search">{t('filters.searchLabel')}</label>
        <div className="relative min-w-[14rem] flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            id="activity-search"
            type="text"
            value={filters.search}
            onChange={e => filters.setSearch(e.target.value)}
            placeholder={searchPlaceholder}
            className={`${CONTROL} w-full pl-8`}
          />
        </div>

        <label className="sr-only" htmlFor="activity-project">{t('filters.workspace')}</label>
        <div className="relative">
          <FolderGit2 className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <select
            id="activity-project"
            value={activeProjectValue}
            onChange={e => filters.setProject(e.target.value)}
            className={`${CONTROL} appearance-none pl-8 pr-3`}
          >
            <option value={ALL_PROJECTS}>{t('filters.allWorkspaces')}</option>
            {projectPaths.map(path => (
              <option key={path} value={path} title={path}>
                {projectLabel(path)}
              </option>
            ))}
          </select>
        </div>

        <input
          type="date"
          aria-label={t('filters.dateStart')}
          value={filters.dateStart}
          onChange={e => filters.setDateStart(e.target.value)}
          className={CONTROL}
        />
        <span aria-hidden className="text-muted-foreground">–</span>
        <input
          type="date"
          aria-label={t('filters.dateEnd')}
          value={filters.dateEnd}
          onChange={e => filters.setDateEnd(e.target.value)}
          className={CONTROL}
        />

        {filters.isFiltered && (
          <button
            onClick={filters.clearAll}
            className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" /> {t('common.clear')}
          </button>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {engineOptions.map(engine => {
          const known = findEngine(engine);
          const pressed = filters.engines.includes(engine);
          return (
            <button
              key={engine}
              aria-pressed={pressed}
              onClick={() => filters.toggleEngine(engine)}
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm font-medium transition-colors ${
                pressed
                  ? 'border-foreground/30 bg-muted text-foreground'
                  : 'border-border text-muted-foreground hover:bg-muted/60 hover:text-foreground'
              }`}
            >
              <span className={`h-2 w-2 rounded-full ${known?.dot ?? 'bg-slate-400'}`} />
              {engine}
            </button>
          );
        })}
        {engineOptions.length === 0 && (
          <p className="text-sm text-muted-foreground">{t('filters.noEngines')}</p>
        )}
        {showEventTypes && (
          <>
            <span aria-hidden className="mx-1 h-4 w-px bg-border" />
            {[
              { value: 'message', labelKey: 'filters.eventMessage' as const },
              { value: 'tool_call', labelKey: 'filters.eventToolCall' as const },
            ].map(({ value, labelKey }) => (
              <button
                key={value}
                aria-pressed={filters.types.includes(value)}
                onClick={() => filters.toggleType(value)}
                className={`rounded-full border px-3 py-1 text-sm font-medium transition-colors ${
                  filters.types.includes(value)
                    ? 'border-foreground/30 bg-muted text-foreground'
                    : 'border-border text-muted-foreground hover:bg-muted/60 hover:text-foreground'
                }`}
              >
                {t(labelKey)}
              </button>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
