import { Filter, FolderGit2, Search, X } from 'lucide-react';
import { useProject } from '../context/ProjectContext';
import { ALL_PROJECTS, type ActivityFilters } from '../hooks/useActivityFilters';

/** Last path segment, for a label that fits the 14rem sidebar. */
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

/**
 * The filter sidebar shared by Activity's History and Events tabs. Both tabs
 * previously carried their own near-identical copy, which drifted (one derived
 * the engine list from data, the other hardcoded it) and dropped everything
 * you had typed the moment you switched tabs.
 */
export default function ActivityFilterPanel({
  filters,
  engineOptions,
  searchPlaceholder,
  showEventTypes = false,
}: ActivityFilterPanelProps) {
  const { validProjects, selectedWorkspace } = useProject();

  // The switcher's workspace always belongs in the list even if it isn't a
  // registered project, otherwise the active filter has no visible option.
  const projectPaths = Array.from(
    new Set([selectedWorkspace, ...validProjects.map(p => p.path)].filter(Boolean)),
  );

  const activeProjectValue = filters.followsWorkspace
    ? selectedWorkspace
    : filters.project || ALL_PROJECTS;

  return (
    <aside
      data-testid="activity-filters"
      className="animate-slide-left stagger-1 w-full xl:w-56 shrink-0 glass-card p-4 space-y-4"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
          <Filter className="w-4 h-4" /> Filters
        </div>
        {filters.isFiltered && (
          <button
            onClick={filters.clearAll}
            className="flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium text-slate-400 transition-colors hover:bg-slate-50 hover:text-slate-600"
          >
            <X className="w-3 h-3" /> Clear
          </button>
        )}
      </div>

      <div>
        <label className="text-xs text-slate-400 font-medium block mb-1" htmlFor="activity-search">
          Search
        </label>
        <div className="relative">
          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2 top-1/2 -translate-y-1/2" />
          <input
            id="activity-search"
            type="text"
            value={filters.search}
            onChange={e => filters.setSearch(e.target.value)}
            placeholder={searchPlaceholder}
            className="w-full pl-7 pr-2 py-1.5 text-xs border border-slate-200 rounded-lg bg-white focus:outline-none focus:border-primary"
          />
        </div>
      </div>

      <div>
        <label className="text-xs text-slate-400 font-medium block mb-1" htmlFor="activity-project">
          Project
        </label>
        <div className="relative">
          <FolderGit2 className="w-3.5 h-3.5 text-slate-400 absolute left-2 top-1/2 -translate-y-1/2 pointer-events-none" />
          <select
            id="activity-project"
            value={activeProjectValue}
            onChange={e => filters.setProject(e.target.value)}
            className="w-full appearance-none pl-7 pr-2 py-1.5 text-xs border border-slate-200 rounded-lg bg-white focus:outline-none focus:border-primary"
          >
            <option value={ALL_PROJECTS}>All projects</option>
            {projectPaths.map(path => (
              <option key={path} value={path} title={path}>
                {projectLabel(path)}
              </option>
            ))}
          </select>
        </div>
        {filters.followsWorkspace && selectedWorkspace && (
          <p className="mt-1 text-[10px] leading-4 text-slate-400">
            Following the workspace switcher.
          </p>
        )}
      </div>

      <div>
        <span className="text-xs text-slate-400 font-medium block mb-1">Date Range</span>
        <div className="grid grid-cols-1 gap-2">
          <input
            type="date"
            aria-label="Date range start"
            value={filters.dateStart}
            onChange={e => filters.setDateStart(e.target.value)}
            className="w-full px-2 py-1.5 text-xs border border-slate-200 rounded-lg bg-white focus:outline-none focus:border-primary"
          />
          <input
            type="date"
            aria-label="Date range end"
            value={filters.dateEnd}
            onChange={e => filters.setDateEnd(e.target.value)}
            className="w-full px-2 py-1.5 text-xs border border-slate-200 rounded-lg bg-white focus:outline-none focus:border-primary"
          />
        </div>
      </div>

      {showEventTypes && (
        <div>
          <span className="text-xs text-slate-400 font-medium block mb-1">Event Type</span>
          <div className="space-y-1">
            {[
              { value: 'message', label: 'Message' },
              { value: 'tool_call', label: 'Tool Call' },
            ].map(({ value, label }) => (
              <button
                key={value}
                aria-pressed={filters.types.includes(value)}
                onClick={() => filters.toggleType(value)}
                className={`w-full text-left px-2 py-1 rounded-md text-xs transition-colors ${
                  filters.types.includes(value)
                    ? 'bg-slate-100 text-slate-800 font-medium'
                    : 'text-slate-500 hover:bg-slate-50'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      )}

      <div>
        <span className="text-xs text-slate-400 font-medium block mb-1">Engine</span>
        <div className="space-y-1">
          {engineOptions.map(engine => (
            <button
              key={engine}
              aria-pressed={filters.engines.includes(engine)}
              onClick={() => filters.toggleEngine(engine)}
              className={`w-full text-left px-2 py-1 rounded-md text-xs transition-colors ${
                filters.engines.includes(engine)
                  ? 'bg-slate-100 text-slate-800 font-medium'
                  : 'text-slate-500 hover:bg-slate-50'
              }`}
            >
              {engine}
            </button>
          ))}
          {engineOptions.length === 0 && (
            <p className="px-2 text-xs text-slate-400">No engines recorded yet</p>
          )}
        </div>
      </div>
    </aside>
  );
}
