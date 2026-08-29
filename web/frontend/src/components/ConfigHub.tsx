import React, { useState, useEffect, useMemo, useRef } from 'react';
import { Save, Loader2, Plus, Trash2, Folder, Languages, Layers, Globe, Zap, Check, X, AlertTriangle, CheckCircle2, ArrowRight, Eraser } from 'lucide-react';
import { useNavigate } from 'react-router';
import { useProject, type Config, type GroupDefinition, type Project } from '../context/ProjectContext';
import { useLanguage, useT } from '../i18n/context';
import { SUPPORTED_LANGUAGES, type Language } from '../i18n/language';
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

const LANGUAGE_LABEL_KEYS = { en: 'language.en', zh: 'language.zh' } as const;

const ConfigHub: React.FC = () => {
  const {
    config,
    projects,
    groups,
    refreshConfig,
    updateConfig,
    availableGroups,
    setCurrentGroup
  } = useProject();
  const t = useT();
  const { language, setLanguage } = useLanguage();
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

  /**
   * Persisted the moment it is picked, unlike the rest of this page.
   *
   * `language` is the same config.json field core/i18n.py reads, so it also
   * decides what `ca` prints in the terminal; staging it behind Save would
   * leave the UI repainted and the CLI not. The draft is patched in step so
   * this page's own Save -- which posts the snapshot it loaded -- cannot
   * quietly put the old language back.
   */
  const chooseLanguage = (next: Language) => {
    if (next === language) return;
    setLanguage(next);
    setLocalConfig(previous => (previous ? { ...previous, language: next } : previous));
    void updateConfig({ ...(config ?? {}), language: next });
  };

  const handleSave = async () => {
    setSaved(false);
    const normalizedProjects = localProjects.map(({ path, group }) => ({
      path: path.trim(),
      group: group.trim(),
    }));
    if (normalizedProjects.some(project => !project.path || !project.group)) {
      setError(t('config.pathsRequired'));
      return;
    }
    if (new Set(normalizedProjects.map(project => project.path)).size !== normalizedProjects.length) {
      setError(t('config.duplicatePath'));
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
      setError(err instanceof Error ? err.message : t('config.genericError'));
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
        <p className="text-sm text-slate-500">{t('config.subtitle')}</p>
        <p className="mt-1 text-xs text-slate-400">
          {t('config.draftNoticePrefix')}{' '}
          <code className="bg-slate-100 px-1 rounded text-slate-600">config.json</code>
          {t('config.draftNoticeSuffix')}
        </p>
      </div>

      {error && (
        <div role="alert" className="p-4 bg-destructive/10 border border-destructive/20 text-destructive rounded-xl text-sm font-medium">
          {t('config.error', { message: error })}
        </div>
      )}

      {/* General Settings */}
      <section className="glass-card p-4 sm:p-8 space-y-6">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-emerald-50 text-emerald-500 rounded-lg">
            <Zap size={20} />
          </div>
          <div>
            <h2 className="text-lg font-semibold tracking-tight">{t('config.generalTitle')}</h2>
            <p className="text-xs text-slate-500">{t('config.generalSubtitle')}</p>
          </div>
        </div>
        <div className="rounded-xl border border-slate-100 bg-slate-50/60 p-4 text-sm text-slate-600">
          {t('config.localOnlyNotice')}
        </div>

        {/* The language lived in the app header, permanently, next to four
            controls of four different kinds. It is a one-time preference and
            it is a config.json field, which makes this page — the config.json
            editor — where it belongs. */}
        <div className="space-y-2 pt-4">
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-2">
            <Languages size={12} className="text-primary" /> {t('language.label')}
          </span>
          <div
            role="radiogroup"
            data-testid="language-switcher"
            aria-label={t('language.label')}
            className="flex flex-wrap gap-2"
          >
            {SUPPORTED_LANGUAGES.map(code => (
              <button
                key={code}
                type="button"
                role="radio"
                aria-checked={code === language}
                onClick={() => chooseLanguage(code)}
                className={`rounded-xl border px-4 py-2 text-sm font-medium transition-colors ${
                  code === language
                    ? 'border-primary/40 bg-primary/10 text-primary'
                    : 'border-slate-100 bg-slate-50/50 text-slate-600 hover:bg-slate-100'
                }`}
              >
                {t(LANGUAGE_LABEL_KEYS[code])}
              </button>
            ))}
          </div>
          <p className="text-[10px] text-slate-500">{t('config.languageHint')}</p>
        </div>

        <div className="space-y-2 pt-4">
          <label htmlFor="config-resource-root" className="text-xs font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-2">
            <Folder size={12} className="text-primary" /> {t('config.privateRoot')}
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
              placeholder={t('config.privateRootPlaceholder')}
              className="flex-1 p-3 border border-slate-100 rounded-xl bg-slate-50/50 text-sm font-mono focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-all"
            />
          </div>
          <p className="text-[10px] text-slate-500">
            {t('config.privateRootHintPrefix')}{' '}
            <code className="bg-slate-100 px-1 rounded text-slate-600">$CODEAGENT</code>
            {t('config.privateRootHintSuffix')}
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
              <h2 className="text-lg font-semibold tracking-tight">{t('config.workspacesTitle')}</h2>
              <p className="text-xs text-slate-500">{t('config.workspacesSubtitle')}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {missingRowCount > 0 && (
              <button
                onClick={removeMissingPaths}
                title={missingRowCount === 1
                  ? t('config.removeMissingTitleOne', { count: missingRowCount })
                  : t('config.removeMissingTitle', { count: missingRowCount })}
                className="text-xs flex items-center gap-2 font-semibold text-amber-700 bg-amber-50 border border-amber-200 px-3 py-2 rounded-xl hover:bg-amber-100 transition-all"
              >
                <Eraser className="w-4 h-4" /> {missingRowCount === 1
                  ? t('config.removeMissingOne', { count: missingRowCount })
                  : t('config.removeMissing', { count: missingRowCount })}
              </button>
            )}
            <button onClick={addProject} className="text-xs flex items-center gap-2 font-semibold text-primary bg-primary/10 px-4 py-2 rounded-xl hover:bg-primary/20 transition-all">
              <Plus className="w-4 h-4" /> {t('config.addWorkspace')}
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
                  aria-label={t('config.workspacePath', { index: i + 1 })}
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
                    {t('config.pathMissing')}
                  </p>
                )}
              </div>
              <select
                id={`project-group-${p.uiId}`}
                aria-label={t('config.groupForWorkspace', { index: i + 1 })}
                value={p.group}
                onChange={(e) => updateProject(p.uiId, 'group', e.target.value)}
                className="w-full sm:w-40 p-2 bg-white border border-slate-200 rounded-lg text-xs outline-none focus:ring-2 focus:ring-primary/20"
              >
                {availableGroups.map(g => <option key={g} value={g}>{g}</option>)}
              </select>
              <button aria-label={t('config.removeWorkspace', { name: p.path || i + 1 })} title={t('config.unregisterWorkspace')} onClick={() => removeProject(p.uiId)} className="self-end sm:self-auto p-2 text-slate-500 hover:text-red-500 transition-colors">
                <Trash2 size={18} />
              </button>
            </div>
            );
          })}
          {localProjects.length === 0 && (
            <div className="text-center py-8 space-y-2">
              <p className="text-slate-500 text-sm">{t('config.noWorkspaces')}</p>
              <p className="text-xs text-slate-400">
                {t('config.noWorkspacesHint')}
                {' '}<code className="bg-slate-100 px-1 rounded text-slate-600 font-mono">/home/you/code/my-app</code>
                {' '}{t('config.noWorkspacesHint2')}
              </p>
              <button onClick={addProject} className="mt-1 inline-flex items-center gap-2 text-xs font-semibold text-primary bg-primary/10 px-4 py-2 rounded-xl hover:bg-primary/20 transition-all">
                <Plus className="w-4 h-4" /> {t('config.addFirstWorkspace')}
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
              <h2 className="text-lg font-semibold tracking-tight">{t('config.groupsTitle')}</h2>
              <p className="text-xs text-slate-500">{t('config.groupsSubtitle')}</p>
            </div>
          </div>
          {addingGroup ? (
            <div className="flex flex-wrap items-center gap-2">
              <input
                ref={newGroupInputRef}
                id="config-new-group"
                type="text"
                aria-label={t('config.newGroupName')}
                value={newGroupName}
                onChange={(e) => setNewGroupName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') confirmAddGroup();
                  if (e.key === 'Escape') cancelAddGroup();
                }}
                placeholder="group-name"
                className="text-sm px-3 py-1.5 border border-primary/30 rounded-xl outline-none focus:ring-2 focus:ring-primary/20 w-36 font-mono"
              />
              <button aria-label={t('config.confirmNewGroup')} onClick={confirmAddGroup} className="p-1.5 bg-primary/10 text-primary rounded-lg hover:bg-primary/20 transition-colors">
                <Check className="w-4 h-4" />
              </button>
              <button aria-label={t('config.cancelNewGroup')} onClick={cancelAddGroup} className="p-1.5 bg-slate-100 text-slate-500 rounded-lg hover:bg-slate-200 transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <button onClick={startAddingGroup} className="text-xs flex items-center gap-2 font-semibold text-primary bg-primary/10 px-4 py-2 rounded-xl hover:bg-primary/20 transition-all">
              <Plus className="w-4 h-4" /> {t('config.newGroup')}
            </button>
          )}
        </div>

        <div className="space-y-2">
          {Object.entries(localGroups).map(([name, def]) => (
            <div key={name} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 border border-slate-100 rounded-xl bg-slate-50/20 hover:border-slate-200 transition-colors">
              <div className="flex flex-wrap items-center gap-3 min-w-0">
                <span className="w-2 h-2 rounded-full bg-primary" />
                <span className="font-semibold text-sm text-slate-800 uppercase tracking-tight">{name}</span>
                <span className="text-xs text-slate-400">{t('config.groupCounts', {
                      skills: def.skills?.length ?? 0,
                      prompts: def.prompts?.length ?? 0,
                      hooks: def.hooks?.length ?? 0,
                      plugins: def.plugins?.length ?? 0,
                    })}</span>
              </div>
              <div className="flex items-center gap-1">
                {/* Group membership is edited on the Resources page — link
                    there instead of leaving "where do I actually tick the
                    boxes?" unanswered. It lands on all four kinds at once now
                    rather than on skills with three tabs still to visit.
                    Hidden while dirty so navigating away can't silently drop
                    unsaved edits. */}
                {!dirty && (
                  <button
                    onClick={() => {
                      setCurrentGroup(name);
                      navigate('/settings/resources');
                    }}
                    className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs font-semibold text-primary hover:bg-primary/10 transition-colors"
                  >
                    {t('config.manageMembers')} <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                )}
                {name !== 'codeagent' && name !== 'common' && (
                  <button aria-label={t('config.removeGroup', { name })} onClick={() => removeGroup(name)} className="p-1.5 text-slate-500 hover:text-red-500 transition-colors rounded-lg hover:bg-red-50">
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
              <h2 className="text-lg font-semibold tracking-tight">{t('config.proxyTitle')}</h2>
              <p className="text-xs text-slate-500">{t('config.proxySubtitle')}</p>
            </div>
          </div>
          <button onClick={addProxy} className="text-xs flex items-center gap-2 font-semibold text-primary bg-primary/10 px-4 py-2 rounded-xl hover:bg-primary/20 transition-all">
            <Plus className="w-4 h-4" /> {t('config.addGateway')}
          </button>
        </div>
        <div className="space-y-3">
          {localProxies.map((p, i) => (
            <div key={p.uiId} className="flex flex-col sm:flex-row gap-3 sm:gap-4 sm:items-center bg-slate-50/30 p-2 rounded-xl border border-slate-100 hover:border-slate-200 transition-colors">
              <input
                id={`proxy-host-${p.uiId}`}
                type="text"
                aria-label={t('config.proxyHost', { index: i + 1 })}
                value={p.host}
                onChange={(e) => updateProxy(p.uiId, 'host', e.target.value)}
                className="flex-1 p-2.5 bg-transparent border-b border-slate-100 focus:border-primary outline-none text-sm font-mono"
              />
              <input
                id={`proxy-port-${p.uiId}`}
                type="number"
                aria-label={t('config.proxyPort', { index: i + 1 })}
                value={p.port}
                onChange={(e) => updateProxy(p.uiId, 'port', parseInt(e.target.value) || 0)}
                className="w-full sm:w-24 p-2.5 bg-transparent border-b border-slate-100 focus:border-primary outline-none text-sm font-mono"
              />
              <button aria-label={t('config.removeProxy', { name: `${p.host}:${p.port}` })} onClick={() => removeProxy(p.uiId)} className="self-end sm:self-auto p-2 text-slate-500 hover:text-red-500 transition-colors">
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
                <CheckCircle2 className="w-3.5 h-3.5" /> {t('config.savedToFile')}
              </span>
            ) : dirty ? (
              <span className="text-amber-700">{t('config.unsavedChanges')}</span>
            ) : (
              <span className="text-slate-400">{t('config.allSaved')}</span>
            )}
          </p>
          <div className="flex items-center gap-2">
            {dirty && (
              <button
                onClick={discardChanges}
                disabled={saving}
                className="px-4 py-2.5 border border-slate-200 text-slate-600 rounded-xl hover:bg-slate-50 disabled:opacity-50 transition-colors font-medium text-sm"
              >
                {t('config.discard')}
              </button>
            )}
            <button
              onClick={handleSave}
              disabled={saving || !dirty}
              className="flex items-center gap-2 px-6 py-2.5 bg-primary text-white rounded-xl hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-all font-semibold shadow-lg shadow-primary/20 active:scale-95 text-sm"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              {t('config.saveAll')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ConfigHub;
