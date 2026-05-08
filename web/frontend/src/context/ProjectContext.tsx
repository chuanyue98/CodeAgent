import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react';

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
}

const ProjectContext = createContext<ProjectContextType | undefined>(undefined);

export const ProjectProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [currentGroup, setCurrentGroup] = useState('codeagent');
  const [config, setConfig] = useState<Config | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [groups, setGroups] = useState<Record<string, GroupDefinition>>({});
  const [availableGroups, setAvailableGroups] = useState<string[]>(['codeagent', 'common', 'work', 'web']);

  const refreshConfig = useCallback(async () => {
    try {
      const configRes = await fetch('/api/config');
      if (configRes.ok) {
        const configData = await configRes.json();
        setConfig(configData as Config);
      }

      const projectsRes = await fetch('/api/projects');
      let projectsData: Project[] = [];
      if (projectsRes.ok) {
        projectsData = await projectsRes.json();
        if (Array.isArray(projectsData)) {
          setProjects(projectsData);
        } else {
          projectsData = [];
        }
      }

      const groupsRes = await fetch('/api/groups');
      let groupsData: Record<string, GroupDefinition> = {};
      if (groupsRes.ok) {
        groupsData = await groupsRes.json();
        if (groupsData && typeof groupsData === 'object') {
          setGroups(groupsData);
        } else {
          groupsData = {};
        }
      }

      const groupSet = new Set<string>(['codeagent', 'common', 'work', 'web']);
      if (Array.isArray(projectsData)) {
        projectsData.forEach((p: Project) => {
          if (p && p.group) groupSet.add(p.group);
        });
      }
      if (groupsData) {
        Object.keys(groupsData).forEach(g => groupSet.add(g));
      }

      setAvailableGroups(Array.from(groupSet));

      if (!groupSet.has(currentGroup)) {
        setCurrentGroup('codeagent');
      }
    } catch (error) {
      console.error('Failed to refresh project context:', error);
    }
  }, [currentGroup]);

  const updateConfig = useCallback(async (newConfig: Config) => {
    try {
      await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newConfig),
      });
      setConfig(newConfig);
      await refreshConfig();
    } catch (error) {
      console.error('Failed to update config:', error);
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
      availableGroups
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
