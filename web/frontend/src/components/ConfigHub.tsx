import React, { useState, useEffect, useRef } from 'react';
import { Save, Loader2, Plus, Trash2, Folder, Layers, Globe, Zap, Check, X } from 'lucide-react';
import { useProject, type Config, type GroupDefinition, type Project } from '../context/ProjectContext';
import request from '../utils/request';

interface ProxyConfig {
  host: string;
  port: number;
}

interface EditableProxyConfig extends ProxyConfig {
  uiId: string;
}

interface EditableProject extends Project {
  uiId: string;
}

let nextEditableRowId = 0;
const createEditableRowId = (kind: 'project' | 'proxy') => `${kind}-${nextEditableRowId++}`;

const deepClone = <T,>(value: T): T => structuredClone(value);

const ConfigHub: React.FC = () => {
  const {
    config,
    projects,
    groups,
    refreshConfig,
    availableGroups
  } = useProject();

  const [localConfig, setLocalConfig] = useState<Config | null>(null);
  const [localProjects, setLocalProjects] = useState<EditableProject[]>([]);
  const [localProxies, setLocalProxies] = useState<EditableProxyConfig[]>([]);
  const [localGroups, setLocalGroups] = useState<Record<string, GroupDefinition>>({});

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [addingGroup, setAddingGroup] = useState(false);
  const [newGroupName, setNewGroupName] = useState('');
  const newGroupInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (config) {
      const cloned = deepClone(config);
      if (!cloned.proxy) cloned.proxy = [];
      else if (!Array.isArray(cloned.proxy)) cloned.proxy = [cloned.proxy];
      if (!cloned.paths) cloned.paths = {};

      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLocalConfig(cloned);
      setLocalProjects(
        deepClone(projects).map(project => ({
          ...project,
          uiId: createEditableRowId('project'),
        })),
      );
      setLocalProxies(
        (cloned.proxy || []).map(proxy => ({
          ...proxy,
          uiId: createEditableRowId('proxy'),
        })),
      );
      setLocalGroups(deepClone(groups));
      setLoading(false);
    }
  }, [config, projects, groups]);

  const handleSave = async () => {
    const normalizedProjects = localProjects.map(({ path, group }) => ({
      path: path.trim(),
      group: group.trim(),
    }));
    if (normalizedProjects.some(project => !project.path || !project.group)) {
      setError('Project path and resource group are required. Complete or remove empty project rows.');
      return;
    }
    if (new Set(normalizedProjects.map(project => project.path)).size !== normalizedProjects.length) {
      setError('Each project path can only be registered once.');
      return;
    }

    try {
      setSaving(true);

      const fullConfig = {
        ...localConfig,
        proxy: localProxies.map(({ host, port }) => ({ host, port })),
        project_registry: normalizedProjects,
        groups: localGroups
      };

      await request('/api/config', {
        method: 'POST',
        body: JSON.stringify(fullConfig),
      });

      await refreshConfig();
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setSaving(false);
    }
  };

  const updateProxy = (uiId: string, field: keyof ProxyConfig, value: string | number) => {
    setLocalProxies(current => current.map(proxy => (
      proxy.uiId === uiId ? { ...proxy, [field]: value } : proxy
    )));
  };

  const addProxy = () => {
    setLocalProxies(current => [
      ...current,
      { uiId: createEditableRowId('proxy'), host: '127.0.0.1', port: 7890 },
    ]);
  };

  const removeProxy = (uiId: string) => {
    setLocalProxies(current => current.filter(proxy => proxy.uiId !== uiId));
  };

  // Project Registry Handlers
  const addProject = () => {
    setLocalProjects(current => [
      ...current,
      { uiId: createEditableRowId('project'), path: '', group: 'common' },
    ]);
  };

  const updateProject = (uiId: string, field: keyof Project, value: string) => {
    setLocalProjects(current => current.map(project => (
      project.uiId === uiId ? { ...project, [field]: value } : project
    )));
  };

  const removeProject = (uiId: string) => {
    setLocalProjects(current => current.filter(project => project.uiId !== uiId));
  };

  // Group Handlers
  const startAddingGroup = () => {
    setAddingGroup(true);
    setNewGroupName('');
    setTimeout(() => newGroupInputRef.current?.focus(), 50);
  };

  const confirmAddGroup = () => {
    const name = newGroupName.trim().toLowerCase().replace(/\s+/g, '-');
    if (name && !localGroups[name]) {
      setLocalGroups({
        ...localGroups,
        [name]: { skills: [], prompts: [], hooks: [], plugins: [] }
      });
    }
    setAddingGroup(false);
    setNewGroupName('');
  };

  const cancelAddGroup = () => {
    setAddingGroup(false);
    setNewGroupName('');
  };

  const removeGroup = (name: string) => {
    if (window.confirm(`Delete group "${name}"?`)) {
      const newGroups = { ...localGroups };
      delete newGroups[name];
      setLocalGroups(newGroups);
    }
  };

  if (loading || !localConfig) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="p-3 sm:p-6 lg:p-8 max-w-5xl mx-auto space-y-6 lg:space-y-8 min-h-full pb-20">
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-end gap-4 pb-4">
        <div>
          <p className="text-sm text-slate-500">Manage projects, groups, and system settings in one place</p>
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-6 py-2.5 bg-primary text-white rounded-xl hover:opacity-90 disabled:opacity-50 transition-all font-semibold shadow-lg shadow-primary/20 active:scale-95 text-sm"
        >
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          Save All Changes
        </button>
      </div>

      {error && (
        <div className="p-4 bg-destructive/10 border border-destructive/20 text-destructive rounded-xl text-sm font-medium">
          Error: {error}
        </div>
      )}

      {/* General Settings */}
      <section className="glass-card p-4 sm:p-8 space-y-6">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-emerald-50 text-emerald-500 rounded-lg">
            <Zap size={20} />
          </div>
          <div>
            <h2 className="text-lg font-semibold tracking-tight">General Settings</h2>
            <p className="text-xs text-slate-500">Core system behavior and environment</p>
          </div>
        </div>
        <div className="rounded-xl border border-slate-100 bg-slate-50/60 p-4 text-sm text-slate-600">
          CodeAgent runs locally. Provider permissions, model selection, and
          response language are controlled by the selected engine and resource
          group rather than by a separate global mode switch.
        </div>

        <div className="space-y-2 pt-4">
          <label htmlFor="config-resource-root" className="text-xs font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-2">
            <Folder size={12} className="text-primary" /> Private Resource Root
          </label>
          <div className="flex gap-3">
            <input
              id="config-resource-root"
              type="text"
              value={localConfig.paths?.resource_root || ''}
              onChange={(e) => {
                const newPaths = { ...(localConfig.paths || {}), resource_root: e.target.value };
                setLocalConfig({ ...localConfig, paths: newPaths });
              }}
              placeholder="$CODEAGENT (Default under project root)"
              className="flex-1 p-3 border border-slate-100 rounded-xl bg-slate-50/50 text-sm font-mono focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-all"
            />
          </div>
          <p className="text-[10px] text-slate-500">
            Unified directory for prompts, skills, tasks, etc. Use <code className="bg-slate-100 px-1 rounded text-slate-600">$CODEAGENT</code> for project root.
          </p>
        </div>
      </section>

      {/* Project Registry */}
      <section className="glass-card p-4 sm:p-8 space-y-6">
        <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-50 text-blue-500 rounded-lg">
              <Folder size={20} />
            </div>
            <div>
              <h2 className="text-lg font-semibold tracking-tight">Project Registry</h2>
              <p className="text-xs text-slate-500">Map paths to resource groups (Longest Prefix Match)</p>
            </div>
          </div>
          <button onClick={addProject} className="text-xs flex items-center gap-2 font-semibold text-primary bg-primary/10 px-4 py-2 rounded-xl hover:bg-primary/20 transition-all">
            <Plus className="w-4 h-4" /> Add Project
          </button>
        </div>

        <div className="space-y-3">
          {localProjects.map((p, i) => (
            <div key={p.uiId} className="flex flex-col sm:flex-row gap-3 sm:gap-4 sm:items-center bg-slate-50/30 p-3 rounded-xl border border-slate-100 hover:border-slate-200 transition-colors">
              <input
                id={`project-path-${p.uiId}`}
                type="text"
                aria-label={`Project path ${i + 1}`}
                value={p.path}
                onChange={(e) => updateProject(p.uiId, 'path', e.target.value)}
                placeholder="E:/your/project/path"
                className="flex-1 p-2 bg-transparent border-b border-slate-200 focus:border-primary outline-none text-sm font-mono"
              />
              <select
                id={`project-group-${p.uiId}`}
                aria-label={`Resource group for project ${i + 1}`}
                value={p.group}
                onChange={(e) => updateProject(p.uiId, 'group', e.target.value)}
                className="w-full sm:w-40 p-2 bg-white border border-slate-200 rounded-lg text-xs outline-none focus:ring-2 focus:ring-primary/20"
              >
                {availableGroups.map(g => <option key={g} value={g}>{g}</option>)}
              </select>
              <button aria-label={`Remove project ${p.path || i + 1}`} onClick={() => removeProject(p.uiId)} className="self-end sm:self-auto p-2 text-slate-500 hover:text-red-500 transition-colors">
                <Trash2 size={18} />
              </button>
            </div>
          ))}
          {localProjects.length === 0 && <p className="text-center py-8 text-slate-500 text-sm italic">No projects registered. Add one to get started.</p>}
        </div>
      </section>

      {/* Resource Groups */}
      <section className="glass-card p-4 sm:p-8 space-y-6">
        <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-50 text-purple-500 rounded-lg">
              <Layers size={20} />
            </div>
            <div>
              <h2 className="text-lg font-semibold tracking-tight">Resource Groups</h2>
              <p className="text-xs text-slate-500">Define which skills, prompts, hooks, and plugins belong to each group</p>
            </div>
          </div>
          {addingGroup ? (
            <div className="flex flex-wrap items-center gap-2">
              <input
                ref={newGroupInputRef}
                id="config-new-group"
                type="text"
                aria-label="New group name"
                value={newGroupName}
                onChange={(e) => setNewGroupName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') confirmAddGroup();
                  if (e.key === 'Escape') cancelAddGroup();
                }}
                placeholder="group-name"
                className="text-sm px-3 py-1.5 border border-primary/30 rounded-xl outline-none focus:ring-2 focus:ring-primary/20 w-36 font-mono"
              />
              <button aria-label="Confirm new group" onClick={confirmAddGroup} className="p-1.5 bg-primary/10 text-primary rounded-lg hover:bg-primary/20 transition-colors">
                <Check className="w-4 h-4" />
              </button>
              <button aria-label="Cancel new group" onClick={cancelAddGroup} className="p-1.5 bg-slate-100 text-slate-500 rounded-lg hover:bg-slate-200 transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <button onClick={startAddingGroup} className="text-xs flex items-center gap-2 font-semibold text-primary bg-primary/10 px-4 py-2 rounded-xl hover:bg-primary/20 transition-all">
              <Plus className="w-4 h-4" /> New Group
            </button>
          )}
        </div>

        <div className="space-y-2">
          {Object.entries(localGroups).map(([name, def]) => (
            <div key={name} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 border border-slate-100 rounded-xl bg-slate-50/20 hover:border-slate-200 transition-colors">
              <div className="flex flex-wrap items-center gap-3 min-w-0">
                <span className="w-2 h-2 rounded-full bg-primary" />
                <span className="font-semibold text-sm text-slate-800 uppercase tracking-tight">{name}</span>
                <span className="text-xs text-slate-400">{def.skills?.length ?? 0} skills · {def.prompts?.length ?? 0} prompts · {def.hooks?.length ?? 0} hooks · {def.plugins?.length ?? 0} plugins</span>
              </div>
              {name !== 'codeagent' && name !== 'common' && (
                <button aria-label={`Remove group ${name}`} onClick={() => removeGroup(name)} className="p-1.5 text-slate-500 hover:text-red-500 transition-colors rounded-lg hover:bg-red-50">
                  <Trash2 size={15} />
                </button>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Proxy Settings */}
      <section className="glass-card p-4 sm:p-8 space-y-6">
        <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-orange-50 text-orange-500 rounded-lg">
              <Globe size={20} />
            </div>
            <div>
              <h2 className="text-lg font-semibold tracking-tight">Proxy Gateways</h2>
              <p className="text-xs text-slate-500">Network settings</p>
            </div>
          </div>
          <button onClick={addProxy} className="text-xs flex items-center gap-2 font-semibold text-primary bg-primary/10 px-4 py-2 rounded-xl hover:bg-primary/20 transition-all">
            <Plus className="w-4 h-4" /> Add Gateway
          </button>
        </div>
        <div className="space-y-3">
          {localProxies.map((p, i) => (
            <div key={p.uiId} className="flex flex-col sm:flex-row gap-3 sm:gap-4 sm:items-center bg-slate-50/30 p-2 rounded-xl border border-slate-100 hover:border-slate-200 transition-colors">
              <input
                id={`proxy-host-${p.uiId}`}
                type="text"
                aria-label={`Proxy host ${i + 1}`}
                value={p.host}
                onChange={(e) => updateProxy(p.uiId, 'host', e.target.value)}
                className="flex-1 p-2.5 bg-transparent border-b border-slate-100 focus:border-primary outline-none text-sm font-mono"
              />
              <input
                id={`proxy-port-${p.uiId}`}
                type="number"
                aria-label={`Proxy port ${i + 1}`}
                value={p.port}
                onChange={(e) => updateProxy(p.uiId, 'port', parseInt(e.target.value) || 0)}
                className="w-full sm:w-24 p-2.5 bg-transparent border-b border-slate-100 focus:border-primary outline-none text-sm font-mono"
              />
              <button aria-label={`Remove proxy ${p.host}:${p.port}`} onClick={() => removeProxy(p.uiId)} className="self-end sm:self-auto p-2 text-slate-500 hover:text-red-500 transition-colors">
                <Trash2 size={20} />
              </button>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
};

export default ConfigHub;
