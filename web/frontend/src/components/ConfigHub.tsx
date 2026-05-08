import React, { useState, useEffect, useRef } from 'react';
import { Save, Loader2, Plus, Trash2, Folder, Layers, Globe, Zap, Check, X } from 'lucide-react';
import { useProject, type Config, type GroupDefinition, type Project } from '../context/ProjectContext';

interface ProxyConfig {
  host: string;
  port: number;
}

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
  const [localProjects, setLocalProjects] = useState<Project[]>([]);
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
      if (!cloned.paths) cloned.paths = {};

      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLocalConfig(cloned);
      setLocalProjects(deepClone(projects));
      setLocalGroups(deepClone(groups));
      setLoading(false);
    }
  }, [config, projects, groups]);

  const handleSave = async () => {
    try {
      setSaving(true);

      const fullConfig = {
        ...localConfig,
        project_registry: localProjects,
        groups: localGroups
      };

      const response = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(fullConfig),
      });

      if (!response.ok) throw new Error('Failed to save config');

      await refreshConfig();
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setSaving(false);
    }
  };

  const updateProxy = (index: number, field: keyof ProxyConfig, value: string | number) => {
    if (!localConfig || !localConfig.proxy) return;
    const newProxy = [...localConfig.proxy];
    newProxy[index] = { ...newProxy[index], [field]: value };
    setLocalConfig({ ...localConfig, proxy: newProxy });
  };

  const addProxy = () => {
    if (!localConfig) return;
    setLocalConfig({
      ...localConfig,
      proxy: [...(localConfig.proxy || []), { host: '127.0.0.1', port: 7890 }]
    });
  };

  const removeProxy = (index: number) => {
    if (!localConfig || !localConfig.proxy) return;
    const newProxy = localConfig.proxy.filter((_: ProxyConfig, i: number) => i !== index);
    setLocalConfig({ ...localConfig, proxy: newProxy });
  };

  // Project Registry Handlers
  const addProject = () => {
    setLocalProjects([...localProjects, { path: '', group: 'common' }]);
  };

  const updateProject = (index: number, field: keyof Project, value: string) => {
    const newProjects = [...localProjects];
    newProjects[index] = { ...newProjects[index], [field]: value };
    setLocalProjects(newProjects);
  };

  const removeProject = (index: number) => {
    setLocalProjects(localProjects.filter((_, i) => i !== index));
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
    <div className="p-8 max-w-5xl mx-auto space-y-8 min-h-full pb-20">
      <div className="flex justify-between items-end pb-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Unified Configuration</h1>
          <p className="text-sm text-slate-500 mt-1">Manage projects, groups, and system settings in one place</p>
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
      <section className="glass-card p-8 space-y-6">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-emerald-50 text-emerald-500 rounded-lg">
            <Zap size={20} />
          </div>
          <div>
            <h2 className="text-lg font-semibold tracking-tight">General Settings</h2>
            <p className="text-xs text-slate-500">Core system behavior and environment</p>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Operation Mode</label>
            <select
              value={localConfig.default_mode || 'local'}
              onChange={(e) => setLocalConfig({ ...localConfig, default_mode: e.target.value })}
              className="w-full p-3 border border-slate-100 rounded-xl bg-slate-50/50 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-all"
            >
              <option value="local">Local Instance</option>
              <option value="cloud">Cloud Synchronized</option>
              <option value="hybrid">Hybrid Protocol</option>
            </select>
          </div>
          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Language</label>
            <select
              value={localConfig.language || 'hybrid'}
              onChange={(e) => setLocalConfig({ ...localConfig, language: e.target.value })}
              className="w-full p-3 border border-slate-100 rounded-xl bg-slate-50/50 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-all"
            >
              <option value="en">English (US)</option>
              <option value="zh">Mandarin (CN)</option>
              <option value="hybrid">Multilingual</option>
            </select>
          </div>
        </div>

        <div className="space-y-2 pt-4">
          <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-2">
            <Folder size={12} className="text-primary" /> Private Resource Root
          </label>
          <div className="flex gap-3">
            <input
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
          <p className="text-[10px] text-slate-400">
            Unified directory for prompts, skills, tasks, etc. Use <code className="bg-slate-100 px-1 rounded">$CODEAGENT</code> for project root.
          </p>
        </div>
      </section>

      {/* Project Registry */}
      <section className="glass-card p-8 space-y-6">
        <div className="flex justify-between items-center">
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
            <div key={i} className="flex gap-4 items-center bg-slate-50/30 p-3 rounded-xl border border-slate-100 hover:border-slate-200 transition-all">
              <input
                type="text"
                value={p.path}
                onChange={(e) => updateProject(i, 'path', e.target.value)}
                placeholder="E:/your/project/path"
                className="flex-1 p-2 bg-transparent border-b border-slate-200 focus:border-primary outline-none text-sm font-mono"
              />
              <select
                value={p.group}
                onChange={(e) => updateProject(i, 'group', e.target.value)}
                className="w-40 p-2 bg-white border border-slate-200 rounded-lg text-xs outline-none focus:ring-2 focus:ring-primary/20"
              >
                {availableGroups.map(g => <option key={g} value={g}>{g}</option>)}
              </select>
              <button onClick={() => removeProject(i)} className="p-2 text-slate-400 hover:text-red-500 transition-colors">
                <Trash2 size={18} />
              </button>
            </div>
          ))}
          {localProjects.length === 0 && <p className="text-center py-8 text-slate-400 text-sm italic">No projects registered. Add one to get started.</p>}
        </div>
      </section>

      {/* Resource Groups */}
      <section className="glass-card p-8 space-y-6">
        <div className="flex justify-between items-center">
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
            <div className="flex items-center gap-2">
              <input
                ref={newGroupInputRef}
                type="text"
                value={newGroupName}
                onChange={(e) => setNewGroupName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') confirmAddGroup();
                  if (e.key === 'Escape') cancelAddGroup();
                }}
                placeholder="group-name"
                className="text-sm px-3 py-1.5 border border-primary/30 rounded-xl outline-none focus:ring-2 focus:ring-primary/20 w-36 font-mono"
              />
              <button onClick={confirmAddGroup} className="p-1.5 bg-primary/10 text-primary rounded-lg hover:bg-primary/20 transition-all">
                <Check className="w-4 h-4" />
              </button>
              <button onClick={cancelAddGroup} className="p-1.5 bg-slate-100 text-slate-400 rounded-lg hover:bg-slate-200 transition-all">
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
            <div key={name} className="flex items-center justify-between px-4 py-3 border border-slate-100 rounded-xl bg-slate-50/20 hover:border-slate-200 transition-all">
              <div className="flex items-center gap-3">
                <span className="w-2 h-2 rounded-full bg-primary" />
                <span className="font-semibold text-sm text-slate-800 uppercase tracking-tight">{name}</span>
                <span className="text-xs text-slate-400">{def.skills?.length ?? 0} skills · {def.prompts?.length ?? 0} prompts · {def.hooks?.length ?? 0} hooks · {def.plugins?.length ?? 0} plugins</span>
              </div>
              {name !== 'codeagent' && name !== 'common' && (
                <button onClick={() => removeGroup(name)} className="p-1.5 text-slate-300 hover:text-red-500 transition-colors rounded-lg hover:bg-red-50">
                  <Trash2 size={15} />
                </button>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Proxy Settings */}
      <section className="glass-card p-8 space-y-6">
        <div className="flex justify-between items-center">
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
          {(localConfig.proxy || []).map((p: ProxyConfig, i: number) => (
            <div key={i} className="flex gap-4 items-center bg-slate-50/30 p-2 rounded-xl border border-slate-100 hover:border-slate-200 transition-all">
              <input
                type="text"
                value={p.host}
                onChange={(e) => updateProxy(i, 'host', e.target.value)}
                className="flex-1 p-2.5 bg-transparent border-b border-slate-100 focus:border-primary outline-none text-sm font-mono"
              />
              <input
                type="number"
                value={p.port}
                onChange={(e) => updateProxy(i, 'port', parseInt(e.target.value) || 0)}
                className="w-24 p-2.5 bg-transparent border-b border-slate-100 focus:border-primary outline-none text-sm font-mono"
              />
              <button onClick={() => removeProxy(i)} className="p-2 text-slate-400 hover:text-red-500 transition-colors">
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
