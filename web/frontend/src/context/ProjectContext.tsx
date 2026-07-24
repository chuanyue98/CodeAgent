import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import request from '../utils/request';

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
  const [availableGroups, setAvailableGroups] = useState<string[]>(['codeagent', 'common', 'work', 'web']);
  const [error, setError] = useState<string | null>(null);
  const currentGroupRef = useRef(currentGroup);
  useEffect(() => {
    currentGroupRef.current = currentGroup;
  }, [currentGroup]);

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

      const groupSet = new Set<string>(['codeagent', 'common', 'work', 'web']);
      projectsArr.forEach((p: Project) => {
        if (p && p.group) groupSet.add(p.group);
      });
      Object.keys(groupsObj).forEach(g => groupSet.add(g));

      setAvailableGroups(Array.from(groupSet));

      if (!groupSet.has(currentGroupRef.current)) {
        setCurrentGroup('codeagent');
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
      throw err;
    }
  }, [refreshConfig]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refreshConfig();
  }, [refreshConfig]);

  return (
    <ProjectContext.Provider value={{
      currentGroup,
      setCurrentGroup,
      config,
      projects,
      groups,
      refreshConfig,
      updateConfig,
      availableGroups,
      error,
    }}>
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
