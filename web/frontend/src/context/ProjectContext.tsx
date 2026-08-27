import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import request from '../utils/request';

// The workspace the user last worked in. Persisted so Agent, Tasks,
// Schedules and Local Terminal all open on the same project instead of each
// page independently defaulting to "the first registered path", and so a
// reload doesn't throw the choice away.
const WORKSPACE_STORAGE_KEY = 'codeagent.selectedWorkspace';

function readStoredWorkspace(): string {
  try {
    return window.localStorage.getItem(WORKSPACE_STORAGE_KEY) || '';
  } catch {
    return '';
  }
}

function writeStoredWorkspace(path: string): void {
  try {
    if (path) window.localStorage.setItem(WORKSPACE_STORAGE_KEY, path);
    else window.localStorage.removeItem(WORKSPACE_STORAGE_KEY);
  } catch {
    // Private-mode / blocked storage: selection still works for this session.
  }
}

interface ProxyConfig {
  host: string;
  port: number;
}

export interface Config {
  default_mode?: string;
  language?: string;
  proxy?: ProxyConfig[];
  paths?: Record<string, string>;
  project_registry?: Project[];
  groups?: Record<string, GroupDefinition>;
  [key: string]: unknown;
}

export interface Project {
  path: string;
  group: string;
  available?: boolean;
}

export interface GroupDefinition {
  skills: string[];
  prompts: string[];
  hooks: string[];
  plugins: string[];
}

interface ProjectContextType {
  currentGroup: string;
  setCurrentGroup: (group: string) => void;
  config: Config | null;
  projects: Project[];
  /** Registered projects that have a path and are reachable on disk. */
  validProjects: Project[];
  /** Workspace shared by Agent / Tasks / Schedules / Terminal. */
  selectedWorkspace: string;
  /** Selects the workspace and follows it with the project's resource group. */
  setSelectedWorkspace: (path: string) => void;
  groups: Record<string, GroupDefinition>;
  refreshConfig: () => Promise<void>;
  updateConfig: (newConfig: Config) => Promise<void>;
  availableGroups: string[];
  error: string | null;
}

const ProjectContext = createContext<ProjectContextType | undefined>(undefined);

export const ProjectProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [currentGroup, setCurrentGroup] = useState('codeagent');
  const [config, setConfig] = useState<Config | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [groups, setGroups] = useState<Record<string, GroupDefinition>>({});
  // Derived from config, never seeded with a fixed list: hardcoding names here
  // meant a group the user had deleted still showed in the switcher, and a
  // fresh install advertised four presets that did not exist yet.
  const [availableGroups, setAvailableGroups] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedWorkspace, setSelectedWorkspaceState] = useState<string>(readStoredWorkspace);
  const currentGroupRef = useRef(currentGroup);
  useEffect(() => {
    currentGroupRef.current = currentGroup;
  }, [currentGroup]);
  // The restored workspace has a group, but nothing adopted it: currentGroup
  // starts at a literal and only moves when the user *changes* workspace, so
  // a reload left the header chip naming whichever group that literal happens
  // to be. Adopt it once, on the first load that can answer -- after that the
  // group is the user's to set (header switcher, Config Hub, palette) and
  // must not be overwritten behind them.
  const groupHydratedRef = useRef(false);
  const selectedWorkspaceRef = useRef(selectedWorkspace);
  useEffect(() => {
    selectedWorkspaceRef.current = selectedWorkspace;
  }, [selectedWorkspace]);

  /**
   * Setting the group is always a decision -- the user's, or a workspace
   * change following its rule. Either way the one-time adoption above must
   * not fire later and overwrite it.
   */
  const selectGroup = useCallback((group: string) => {
    groupHydratedRef.current = true;
    setCurrentGroup(group);
  }, []);

  const refreshConfig = useCallback(async () => {
    try {
      setError(null);
      const [configData, projectsData, groupsData] = await Promise.all([
        request<Config>('/api/config'),
        request<Project[]>('/api/projects'),
        request<Record<string, GroupDefinition>>('/api/groups'),
      ]);

      setConfig(configData || {});

      const projectsArr = Array.isArray(projectsData) ? projectsData : [];
      setProjects(projectsArr);

      const groupsObj = groupsData && typeof groupsData === 'object' ? groupsData : {};
      setGroups(groupsObj);

      // Groups that actually exist: the ones defined in config, plus any a
      // registry rule points at (a rule naming a group with no definition yet
      // is still a group the user can be working under).
      const groupSet = new Set<string>(Object.keys(groupsObj));
      projectsArr.forEach((p: Project) => {
        if (p && p.group) groupSet.add(p.group);
      });

      const groupList = Array.from(groupSet).sort();
      setAvailableGroups(groupList);

      if (!groupHydratedRef.current) {
        const restored = projectsArr.find(
          project => project.path === selectedWorkspaceRef.current,
        );
        if (restored?.group) {
          groupHydratedRef.current = true;
          setCurrentGroup(restored.group);
        } else if (projectsArr.length > 0) {
          // Nothing to adopt from, but the answer is now known to be "none";
          // don't keep asking on every later refresh.
          groupHydratedRef.current = true;
        }
      }

      // Only re-point the selection when it no longer resolves. Falling back to
      // the first real group rather than a hardcoded "codeagent", which is not
      // guaranteed to exist.
      if (groupList.length > 0 && !groupSet.has(currentGroupRef.current)) {
        setCurrentGroup(groupList[0]);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load configuration';
      setError(msg);
      console.error('Failed to refresh project context:', err);
      setConfig({});
    }
    // Stable identity (no currentGroup dependency) -- refreshConfig must not
    // change identity on every group switch, or the mount-only effect below
    // (deps: [refreshConfig]) would re-fetch /api/config on every
    // setCurrentGroup call and could silently revert a just-made selection
    // if the freshly-fetched group list hasn't caught up yet.
  }, []);

  const updateConfig = useCallback(async (newConfig: Config) => {
    try {
      setError(null);
      await request('/api/config', {
        method: 'POST',
        body: JSON.stringify(newConfig),
      });
      setConfig(newConfig);
      await refreshConfig();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to update config';
      setError(msg);
      console.error('Failed to update config:', err);
    }
  }, [refreshConfig]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refreshConfig();
  }, [refreshConfig]);

  const validProjects = useMemo(
    () => projects.filter(project => project.path.trim() && project.available !== false),
    [projects],
  );

  // Read through a ref so the setter keeps a stable identity -- consumers
  // pass it straight to onChange handlers and effect deps.
  const projectsRef = useRef<Project[]>(projects);
  useEffect(() => {
    projectsRef.current = projects;
  }, [projects]);

  const setSelectedWorkspace = useCallback((path: string) => {
    setSelectedWorkspaceState(path);
    writeStoredWorkspace(path);
    // The resource group is a property of the workspace, so following it
    // here means no page has to remember to keep the two in sync (and the
    // Group chip in the header never disagrees with the open project).
    const project = projectsRef.current.find(item => item.path === path);
    if (project?.group) selectGroup(project.group);
    // selectGroup is stable (useCallback with no deps), so this keeps the
    // stable identity the mount-only effects below rely on.
  }, [selectGroup]);

  // Heal a selection that no longer resolves (project removed, path gone
  // missing, or nothing chosen yet) by falling back to the first usable one.
  useEffect(() => {
    if (validProjects.length === 0) return;
    if (validProjects.some(project => project.path === selectedWorkspace)) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSelectedWorkspace(validProjects[0].path);
  }, [selectedWorkspace, setSelectedWorkspace, validProjects]);

  const value = useMemo<ProjectContextType>(() => ({
    currentGroup,
    setCurrentGroup: selectGroup,
    config,
    projects,
    validProjects,
    selectedWorkspace,
    setSelectedWorkspace,
    groups,
    refreshConfig,
    updateConfig,
    availableGroups,
    error,
  }), [
    currentGroup,
    selectGroup,
    config,
    projects,
    validProjects,
    selectedWorkspace,
    setSelectedWorkspace,
    groups,
    refreshConfig,
    updateConfig,
    availableGroups,
    error,
  ]);

  return (
    <ProjectContext.Provider value={value}>
      {children}
    </ProjectContext.Provider>
  );
};

// eslint-disable-next-line react-refresh/only-export-components
export const useProject = () => {
  const context = useContext(ProjectContext);
  if (!context) throw new Error('useProject must be used within ProjectProvider');
  return context;
};
