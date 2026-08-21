import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router';
import { useProject } from '../context/ProjectContext';

/**
 * Filter state for Activity's History and Events tabs, stored in the URL.
 *
 * Keeping it in the query string rather than component state buys three
 * things the pages used to lack: the back button steps through filter
 * changes, a filtered view can be copied to someone else, and switching
 * between the two tabs carries the filters over (see ACTIVITY_FILTER_PARAMS
 * in navigation.ts, which SectionLayout forwards).
 */

/** Project filter value meaning "every project", as opposed to a path. */
export const ALL_PROJECTS = 'all';

export interface ActivityFilters {
  search: string;
  dateStart: string;
  dateEnd: string;
  engines: string[];
  types: string[];
  /**
   * Project path to narrow to, or '' for every project. Resolved from the
   * URL when pinned there, otherwise from the workspace switcher.
   */
  project: string;
  /** True while `project` is following the workspace switcher. */
  followsWorkspace: boolean;
  /**
   * False until the workspace is known. Pages must not fetch before this
   * flips, or they issue one request against "all projects" and a second one
   * the moment the config resolves.
   */
  ready: boolean;
  /** True when any filter differs from the default view. */
  isFiltered: boolean;

  setSearch: (value: string) => void;
  setDateStart: (value: string) => void;
  setDateEnd: (value: string) => void;
  toggleEngine: (engine: string) => void;
  toggleType: (type: string) => void;
  /** Pass a path to pin one project, ALL_PROJECTS for every project, or '' to follow the switcher. */
  setProject: (value: string) => void;
  clearAll: () => void;
}

function readList(params: URLSearchParams, key: string): string[] {
  const raw = params.get(key);
  if (!raw) return [];
  return raw.split(',').map(part => part.trim()).filter(Boolean);
}

export default function useActivityFilters(): ActivityFilters {
  const [searchParams, setSearchParams] = useSearchParams();
  const {
    selectedWorkspace,
    validProjects,
    config,
    error: projectError,
  } = useProject();

  // ProjectProvider auto-selects the first valid workspace in an effect that
  // runs after the config lands, so `config !== null` alone is one render too
  // early: a page fetching then would issue a request for "all projects" and
  // a second one the moment the workspace settled. This mirrors that effect's
  // own guard — it is settled once nothing is left to auto-select.
  const workspaceSettled =
    projectError !== null ||
    (config !== null &&
      (validProjects.length === 0 ||
        validProjects.some(project => project.path === selectedWorkspace)));

  const search = searchParams.get('q') ?? '';
  const dateStart = searchParams.get('from') ?? '';
  const dateEnd = searchParams.get('to') ?? '';
  const projectParam = searchParams.get('project') ?? '';

  const engines = useMemo(() => readList(searchParams, 'engines'), [searchParams]);
  const types = useMemo(() => readList(searchParams, 'types'), [searchParams]);

  // No `project` in the URL means "whatever the workspace switcher says", so
  // Activity follows the workspace like the rest of the app. An explicit
  // value pins the choice and survives switching workspaces.
  const followsWorkspace = projectParam === '';
  const project = followsWorkspace
    ? selectedWorkspace
    : projectParam === ALL_PROJECTS
      ? ''
      : projectParam;

  const update = useCallback(
    (key: string, value: string) => {
      setSearchParams(
        previous => {
          const next = new URLSearchParams(previous);
          if (value) next.set(key, value);
          else next.delete(key);
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const toggleInList = useCallback(
    (key: string, item: string) => {
      setSearchParams(
        previous => {
          const next = new URLSearchParams(previous);
          const current = readList(previous, key);
          const updated = current.includes(item)
            ? current.filter(entry => entry !== item)
            : [...current, item];
          if (updated.length > 0) next.set(key, updated.join(','));
          else next.delete(key);
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const clearAll = useCallback(() => {
    setSearchParams(
      previous => {
        const next = new URLSearchParams(previous);
        for (const key of ['q', 'from', 'to', 'engines', 'types', 'project']) {
          next.delete(key);
        }
        return next;
      },
      { replace: true },
    );
  }, [setSearchParams]);

  return {
    search,
    dateStart,
    dateEnd,
    engines,
    types,
    project,
    followsWorkspace,
    // A pinned project needs no workspace, so that case is ready immediately.
    ready: !followsWorkspace || workspaceSettled,
    isFiltered: Boolean(
      search || dateStart || dateEnd || engines.length || types.length || projectParam,
    ),
    setSearch: useCallback(value => update('q', value), [update]),
    setDateStart: useCallback(value => update('from', value), [update]),
    setDateEnd: useCallback(value => update('to', value), [update]),
    toggleEngine: useCallback(engine => toggleInList('engines', engine), [toggleInList]),
    toggleType: useCallback(type => toggleInList('types', type), [toggleInList]),
    setProject: useCallback(value => update('project', value), [update]),
    clearAll,
  };
}
