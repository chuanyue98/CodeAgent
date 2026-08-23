import React, { useState, useEffect, useMemo, useRef } from 'react';
import { Save, Loader2, Plus, Trash2, Folder, Layers, Globe, Zap, Check, X, AlertTriangle, CheckCircle2, ArrowRight, Eraser } from 'lucide-react';
import { useNavigate } from 'react-router';
import { useProject, type Config, type GroupDefinition, type Project } from '../context/ProjectContext';
import request from '../utils/request';
import LoadingState from './shared/LoadingState';

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
    availableGroups,
    setCurrentGroup
  } = useProject();
  const navigate = useNavigate();

  const [localConfig, setLocalConfig] = useState<Config | null>(null);
  const [localProjects, setLocalProjects] = useState<EditableProject[]>([]);
  const [localProxies, setLocalProxies] = useState<EditableProxyConfig[]>([]);
  const [localGroups, setLocalGroups] = useState<Record<string, GroupDefinition>>({});

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [addingGroup, setAddingGroup] = useState(false);
  const [newGroupName, setNewGroupName] = useState('');
  const newGroupInputRef = useRef<HTMLInputElement>(null);

  // Tracks whether the user has unsaved local edits. While dirty, the sync
  // effect below must NOT overwrite local state from context (which would
  // discard those edits). It is cleared after a successful save so the next
  // context refresh can repopulate local state with the persisted values.
  //
  // Deliberately a plain flag rather than the derived `dirty` below: the sync
  // effect *writes* the state `dirty` is computed from (and mints fresh uiIds
  // each pass), so guarding it on a derived value would re-trigger it forever.
  const [isDirty, setIsDirty] = useState(false);

  // Serialized snapshot of what the server last confirmed. Drives the save
  // bar only, so it can say "nothing to save" instead of always looking
  // actionable -- and unlike the flag, it clears itself when an edit is
  // manually undone back to the saved values.
  const savedSnapshot = useMemo(
    () => JSON.stringify({
      resourceRoot: config?.paths?.resource_root || '',
      projects: projects.map(({ path, group }) => ({ path, group })),
      proxies: (config?.proxy || []).map(({ host, port }) => ({ host, port })),
      groups,
    }),
    [config, projects, groups],
  );
  const draftSnapshot = useMemo(
    () => JSON.stringify({
      resourceRoot: localConfig?.paths?.resource_root || '',
      projects: localProjects.map(({ path, group }) => ({ path, group })),
      proxies: localProxies.map(({ host, port }) => ({ host, port })),
      groups: localGroups,
    }),
    [localConfig, localProjects, localProxies, localGroups],
  );
  const dirty = !loading && savedSnapshot !== draftSnapshot;

  useEffect(() => {
    // Context data may change (e.g. a resource toggle in another view calls
    // refreshConfig). If the user has unsaved edits here, keep them and skip
    // the reset; we only re-sync from context when there are no local edits.
    if (isDirty) return;

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
  }, [config, projects, groups, isDirty]);

  const handleSave = async () => {
    setSaved(false);
    const normalizedProjects = localProjects.map(({ path, group }) => ({
      path: path.trim(),
      group: group.trim(),
    }));
    if (normalizedProjects.some(project => !project.path || !project.group)) {
      setError('Workspace path and resource group are required. Complete or remove empty rows.');
      return;
    }
    if (new Set(normalizedProjects.map(project => project.path)).size !== normalizedProjects.length) {
      setError('Each workspace path can only be registered once.');
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
      // Local edits are now persisted. Clear the dirty flag so the sync effect
      // (re-triggered by refreshConfig) is allowed to repopulate local state
      // from the freshly-fetched context.
      setIsDirty(false);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setSaving(false);
    }
  };

  // Clear the success confirmation once it has been read, so it never lingers
  // next to edits it does not describe.
  useEffect(() => {
    if (!saved) return;
    const timer = window.setTimeout(() => setSaved(false), 4000);
    return () => window.clearTimeout(timer);
  }, [saved]);

  const updateProxy = (uiId: string, field: keyof ProxyConfig, value: string | number) => {
    setIsDirty(true);
    setLocalProxies(current => current.map(proxy => (
      proxy.uiId === uiId ? { ...proxy, [field]: value } : proxy
    )));
  };

  const addProxy = () => {
    setIsDirty(true);
    setLocalProxies(current => [
      ...current,
      { uiId: createEditableRowId('proxy'), host: '127.0.0.1', port: 7890 },
    ]);
  };

  const removeProxy = (uiId: string) => {
    setIsDirty(true);
    setLocalProxies(current => current.filter(proxy => proxy.uiId !== uiId));
  };

  // Project Registry Handlers
  const addProject = () => {
    setIsDirty(true);
    setLocalProjects(current => [
      ...current,
      { uiId: createEditableRowId('project'), path: '', group: 'common' },
    ]);
  };

  // Batch version of removeProject for rows whose saved path no longer
  // exists on disk. Still a draft: the save bar shows the pending removal
  // and "Discard changes" brings every row back.
  const removeMissingPaths = () => {
    setIsDirty(true);
    setLocalProjects(current => current.filter(p => {
      const saved = projects.find(project => project.path === p.path.trim());
      return !(p.path.trim() && saved?.available === false);
    }));
  };

  // Whether any row is currently flagged as missing, so the batch cleanup
  // button only appears when it has something to do.
  const missingRowCount = useMemo(
    () => localProjects.filter(p => {
      const saved = projects.find(project => project.path === p.path.trim());
      return Boolean(p.path.trim()) && saved?.available === false;
    }).length,
    [localProjects, projects],
  );

  const updateProject = (uiId: string, field: keyof Project, value: string) => {
    setIsDirty(true);
    setLocalProjects(current => current.map(project => (
      project.uiId === uiId ? { ...project, [field]: value } : project
    )));
  };

  const removeProject = (uiId: string) => {
    setIsDirty(true);
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
      setIsDirty(true);
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

  // Every edit on this page is a draft -- nothing reaches config.json until
  // "Save All Changes". So removals need no modal confirm; the save bar makes
  // the pending change visible and "Discard changes" undoes it.
  const removeGroup = (name: string) => {
    setIsDirty(true);
    const newGroups = { ...localGroups };
    delete newGroups[name];
    setLocalGroups(newGroups);
  };

  const discardChanges = () => {
    if (!config) return;
    const cloned = deepClone(config);
    if (!cloned.proxy) cloned.proxy = [];
    else if (!Array.isArray(cloned.proxy)) cloned.proxy = [cloned.proxy];
    if (!cloned.paths) cloned.paths = {};
    setLocalConfig(cloned);
    setLocalProjects(
      deepClone(projects).map(project => ({ ...project, uiId: createEditableRowId('project') })),
    );
    setLocalProxies(
      (cloned.proxy || []).map(proxy => ({ ...proxy, uiId: createEditableRowId('proxy') })),
    );
    setLocalGroups(deepClone(groups));
    setError(null);
    setSaved(false);
    // Hand control back to the sync effect now that local state matches
    // context again.
    setIsDirty(false);
  };

  if (loading || !localConfig) {
    return <LoadingState height="h-full" />;
  }

  return (
    <div className="p-3 sm:p-6 lg:p-8 max-w-5xl mx-auto space-y-6 lg:space-y-8 min-h-full pb-28">
      <div className="pb-4">
        <p className="text-sm text-slate-500">Manage projects, groups, and system settings in one place</p>
        <p className="mt-1 text-xs text-slate-400">
          Edits here are a draft — nothing is written to <code className="bg-slate-100 px-1 rounded text-slate-600">config.json</code> until you save.
        </p>
      </div>

      {error && (
        <div role="alert" className="p-4 bg-destructive/10 border border-destructive/20 text-destructive rounded-xl text-sm font-medium">
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
                setIsDirty(true);
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

      {/* Workspace Registry */}
      <section className="glass-card p-4 sm:p-8 space-y-6">
        <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-50 text-blue-500 rounded-lg">
              <Folder size={20} />
            </div>
            <div>
              <h2 className="text-lg font-semibold tracking-tight">Workspaces</h2>
              <p className="text-xs text-slate-500">Registered directories CodeAgent can work in, mapped to resource groups (longest prefix match)</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {missingRowCount > 0 && (
              <button
                onClick={removeMissingPaths}
                title={`Remove the ${missingRowCount} registered path${missingRowCount === 1 ? '' : 's'} that no longer exist on disk`}
                className="text-xs flex items-center gap-2 font-semibold text-amber-700 bg-amber-50 border border-amber-200 px-3 py-2 rounded-xl hover:bg-amber-100 transition-all"
              >
                <Eraser className="w-4 h-4" /> Remove {missingRowCount} missing path{missingRowCount === 1 ? '' : 's'}
              </button>
            )}
            <button onClick={addProject} className="text-xs flex items-center gap-2 font-semibold text-primary bg-primary/10 px-4 py-2 rounded-xl hover:bg-primary/20 transition-all">
              <Plus className="w-4 h-4" /> Add Workspace
            </button>
          </div>
        </div>

        <div className="space-y-3">
          {localProjects.map((p, i) => {
            // `available` comes from the server's last scan, so it only
            // describes rows that were already saved -- a freshly typed path
            // is "unknown", not "broken", until the next save + refresh.
            const savedProject = projects.find(project => project.path === p.path.trim());
            const missing = Boolean(p.path.trim()) && savedProject?.available === false;
            return (
            <div key={p.uiId} className="flex flex-col sm:flex-row gap-3 sm:gap-4 sm:items-center bg-slate-50/30 p-3 rounded-xl border border-slate-100 hover:border-slate-200 transition-colors">
              <div className="flex-1 min-w-0">
                <input
                  id={`project-path-${p.uiId}`}
                  type="text"
                  aria-label={`Workspace path ${i + 1}`}
                  value={p.path}
                  onChange={(e) => updateProject(p.uiId, 'path', e.target.value)}
                  placeholder="/absolute/path/to/your/project"
                  className={`w-full p-2 bg-transparent border-b outline-none text-sm font-mono ${
                    missing ? 'border-amber-400 text-amber-800' : 'border-slate-200 focus:border-primary'
                  }`}
                />
                {missing && (
                  <p className="mt-1 flex items-center gap-1 text-[11px] text-amber-700">
                    <AlertTriangle className="w-3 h-3 shrink-0" />
                    This path was not found on disk, so it is hidden from every workspace picker.
                  </p>
                )}
              </div>
              <select
                id={`project-group-${p.uiId}`}
                aria-label={`Resource group for workspace ${i + 1}`}
                value={p.group}
                onChange={(e) => updateProject(p.uiId, 'group', e.target.value)}
                className="w-full sm:w-40 p-2 bg-white border border-slate-200 rounded-lg text-xs outline-none focus:ring-2 focus:ring-primary/20"
              >
                {availableGroups.map(g => <option key={g} value={g}>{g}</option>)}
              </select>
              <button aria-label={`Remove workspace ${p.path || i + 1}`} title="Unregister this workspace" onClick={() => removeProject(p.uiId)} className="self-end sm:self-auto p-2 text-slate-500 hover:text-red-500 transition-colors">
                <Trash2 size={18} />
              </button>
            </div>
            );
          })}
          {localProjects.length === 0 && (
            <div className="text-center py-8 space-y-2">
              <p className="text-slate-500 text-sm">No workspaces registered yet.</p>
              <p className="text-xs text-slate-400">
                Add the absolute path of a directory you want CodeAgent to work in — for example
                {' '}<code className="bg-slate-100 px-1 rounded text-slate-600 font-mono">/home/you/code/my-app</code>.
                The agent never operates outside a registered path.
              </p>
              <button onClick={addProject} className="mt-1 inline-flex items-center gap-2 text-xs font-semibold text-primary bg-primary/10 px-4 py-2 rounded-xl hover:bg-primary/20 transition-all">
                <Plus className="w-4 h-4" /> Add your first workspace
              </button>
            </div>
          )}
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
              <div className="flex items-center gap-1">
                {/* Group membership is edited in the capability galleries, one
                    kind at a time — link there instead of leaving "where do I
                    actually tick the boxes?" unanswered. Hidden while dirty so
                    navigating away can't silently drop unsaved edits. */}
                {!dirty && (
                  <button
                    onClick={() => {
                      setCurrentGroup(name);
                      navigate('/settings/skills');
                    }}
                    className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs font-semibold text-primary hover:bg-primary/10 transition-colors"
                  >
                    Manage members <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                )}
                {name !== 'codeagent' && name !== 'common' && (
                  <button aria-label={`Remove group ${name}`} onClick={() => removeGroup(name)} className="p-1.5 text-slate-500 hover:text-red-500 transition-colors rounded-lg hover:bg-red-50">
                    <Trash2 size={15} />
                  </button>
                )}
              </div>
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

      {/* Sticky save bar: the Save button used to sit at the very top, so on
          a long form you had to scroll back up to commit an edit made at the
          bottom -- and nothing ever confirmed that the save landed. */}
      <div className="sticky bottom-0 -mx-3 sm:-mx-6 lg:-mx-8 px-3 sm:px-6 lg:px-8 pb-3 pt-2">
        <div className="glass-card flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          <p aria-live="polite" className="text-xs font-medium">
            {saved ? (
              <span className="flex items-center gap-1.5 text-emerald-600">
                <CheckCircle2 className="w-3.5 h-3.5" /> Saved to config.json
              </span>
            ) : dirty ? (
              <span className="text-amber-700">Unsaved changes</span>
            ) : (
              <span className="text-slate-400">All changes saved</span>
            )}
          </p>
          <div className="flex items-center gap-2">
            {dirty && (
              <button
                onClick={discardChanges}
                disabled={saving}
                className="px-4 py-2.5 border border-slate-200 text-slate-600 rounded-xl hover:bg-slate-50 disabled:opacity-50 transition-colors font-medium text-sm"
              >
                Discard changes
              </button>
            )}
            <button
              onClick={handleSave}
              disabled={saving || !dirty}
              className="flex items-center gap-2 px-6 py-2.5 bg-primary text-white rounded-xl hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-all font-semibold shadow-lg shadow-primary/20 active:scale-95 text-sm"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              Save All Changes
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ConfigHub;
