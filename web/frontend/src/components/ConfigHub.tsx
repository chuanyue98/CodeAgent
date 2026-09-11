import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  Save,
  Plus,
  Trash2,
  Folder,
  Languages,
  Layers,
  Globe,
  Zap,
  Check,
  X,
  AlertTriangle,
  CheckCircle2,
  ArrowRight,
  Eraser,
  TerminalSquare,
} from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router';
import { useProject, type Config, type GroupDefinition, type Project } from '../context/ProjectContext';
import { useLanguage, useT } from '../i18n/context';
import { SUPPORTED_LANGUAGES, type Language } from '../i18n/language';
import request from '../utils/request';
import LoadingState from './shared/LoadingState';
import ErrorBar from './shared/ErrorBar';
import Button from './shared/Button';
import SectionLabel from './shared/SectionLabel';
import { Input, Select, SearchInput } from './shared/Field';
import { ACTIVE_CHIP } from './shared/activeChip';

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

export type ConfigSectionId = 'workspaces' | 'groups' | 'general' | 'proxy';

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
    setCurrentGroup,
    setSelectedWorkspace,
  } = useProject();
  const t = useT();
  const { language, setLanguage } = useLanguage();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const initialSection = (searchParams.get('tab') as ConfigSectionId) || 'workspaces';
  const [activeSection, setActiveSection] = useState<ConfigSectionId>(
    ['workspaces', 'groups', 'general', 'proxy'].includes(initialSection) ? initialSection : 'workspaces'
  );

  const [localConfig, setLocalConfig] = useState<Config | null>(null);
  const [localProjects, setLocalProjects] = useState<EditableProject[]>([]);
  const [localProxies, setLocalProxies] = useState<EditableProxyConfig[]>([]);
  const [localGroups, setLocalGroups] = useState<Record<string, GroupDefinition>>({});

  const [workspaceSearch, setWorkspaceSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [addingGroup, setAddingGroup] = useState(false);
  const [newGroupName, setNewGroupName] = useState('');
  const newGroupInputRef = useRef<HTMLInputElement>(null);

  const [isDirty, setIsDirty] = useState(false);

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
    if (isDirty) return;

    if (config) {
      const cloned = deepClone(config);
      if (!cloned.proxy) cloned.proxy = [];
      else if (!Array.isArray(cloned.proxy)) cloned.proxy = [cloned.proxy];
      if (!cloned.paths) cloned.paths = {};

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

  const switchSection = (section: ConfigSectionId) => {
    setActiveSection(section);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set('tab', section);
    setSearchParams(nextParams, { replace: true });
  };

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
        groups: localGroups,
      };

      await request('/api/config', {
        method: 'POST',
        body: JSON.stringify(fullConfig),
      });

      await refreshConfig();
      setError(null);
      setIsDirty(false);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('config.genericError'));
    } finally {
      setSaving(false);
    }
  };

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

  const addProject = () => {
    setIsDirty(true);
    setLocalProjects(current => [
      ...current,
      { uiId: createEditableRowId('project'), path: '', group: 'common' },
    ]);
  };

  const removeMissingPaths = () => {
    setIsDirty(true);
    setLocalProjects(current => current.filter(p => {
      const savedProject = projects.find(project => project.path === p.path.trim());
      return !(p.path.trim() && savedProject?.available === false);
    }));
  };

  const missingRowCount = useMemo(
    () => localProjects.filter(p => {
      const savedProject = projects.find(project => project.path === p.path.trim());
      return Boolean(p.path.trim()) && savedProject?.available === false;
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

  const openInTerminal = (projectPath: string) => {
    setSelectedWorkspace(projectPath);
    navigate(`/agent/terminal?project=${encodeURIComponent(projectPath)}`);
  };

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
        [name]: { skills: [], prompts: [], hooks: [], plugins: [] },
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
    setIsDirty(false);
  };

  const filteredProjects = useMemo(() => {
    if (!workspaceSearch.trim()) return localProjects;
    const term = workspaceSearch.toLowerCase().trim();
    return localProjects.filter(p =>
      p.path.toLowerCase().includes(term) || p.group.toLowerCase().includes(term),
    );
  }, [localProjects, workspaceSearch]);

  if (loading || !localConfig) {
    return <LoadingState height="h-full" />;
  }

  return (
    <div className="flex h-full min-h-0 flex-col md:flex-row gap-4">
      {/* ── Left Navigation Rail ────────────────────────────────────────── */}
      <div className="w-full md:w-64 shrink-0 flex flex-col gap-3 glass-card p-4 overflow-y-auto custom-scrollbar">
        <div>
          <h2 className="text-base font-bold tracking-tight text-slate-800">
            {t('config.workspacesTitle')}
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">{t('config.subtitle')}</p>
        </div>

        <nav aria-label={t('nav.settings')} className="space-y-1 pt-1">
          {/* Workspaces */}
          <button
            type="button"
            onClick={() => switchSection('workspaces')}
            className={`w-full flex items-center justify-between gap-2.5 px-3 py-2.5 rounded-xl text-xs font-semibold transition-all ${
              activeSection === 'workspaces'
                ? ACTIVE_CHIP
                : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
            }`}
          >
            <div className="flex items-center gap-2.5 truncate">
              <Folder size={16} className={activeSection === 'workspaces' ? 'text-primary' : 'text-slate-400'} />
              <span>{t('config.nav.workspaces')}</span>
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              {missingRowCount > 0 && (
                <span
                  title={t('config.removeMissing', { count: missingRowCount })}
                  className="w-2 h-2 rounded-full bg-amber-500 animate-pulse"
                />
              )}
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-600">
                {localProjects.length}
              </span>
            </div>
          </button>

          {/* Groups */}
          <button
            type="button"
            onClick={() => switchSection('groups')}
            className={`w-full flex items-center justify-between gap-2.5 px-3 py-2.5 rounded-xl text-xs font-semibold transition-all ${
              activeSection === 'groups'
                ? ACTIVE_CHIP
                : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
            }`}
          >
            <div className="flex items-center gap-2.5 truncate">
              <Layers size={16} className={activeSection === 'groups' ? 'text-primary' : 'text-slate-400'} />
              <span>{t('config.nav.groups')}</span>
            </div>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-600">
              {Object.keys(localGroups).length}
            </span>
          </button>

          {/* General */}
          <button
            type="button"
            onClick={() => switchSection('general')}
            className={`w-full flex items-center justify-between gap-2.5 px-3 py-2.5 rounded-xl text-xs font-semibold transition-all ${
              activeSection === 'general'
                ? ACTIVE_CHIP
                : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
            }`}
          >
            <div className="flex items-center gap-2.5 truncate">
              <Zap size={16} className={activeSection === 'general' ? 'text-primary' : 'text-slate-400'} />
              <span>{t('config.nav.general')}</span>
            </div>
          </button>

          {/* Proxy */}
          <button
            type="button"
            onClick={() => switchSection('proxy')}
            className={`w-full flex items-center justify-between gap-2.5 px-3 py-2.5 rounded-xl text-xs font-semibold transition-all ${
              activeSection === 'proxy'
                ? ACTIVE_CHIP
                : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
            }`}
          >
            <div className="flex items-center gap-2.5 truncate">
              <Globe size={16} className={activeSection === 'proxy' ? 'text-primary' : 'text-slate-400'} />
              <span>{t('config.nav.proxy')}</span>
            </div>
            {localProxies.length > 0 && (
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-600">
                {localProxies.length}
              </span>
            )}
          </button>
        </nav>

        {/* Global Language Selector */}
        <div className="pt-3 border-t border-slate-100 space-y-2">
          <SectionLabel className="flex items-center gap-1.5 text-[11px]">
            <Languages size={13} className="text-primary" /> {t('language.label')}
          </SectionLabel>
          <div
            role="radiogroup"
            data-testid="language-switcher"
            aria-label={t('language.label')}
            className="grid grid-cols-2 gap-1.5"
          >
            {SUPPORTED_LANGUAGES.map(code => (
              <button
                key={code}
                type="button"
                role="radio"
                aria-checked={code === language}
                onClick={() => chooseLanguage(code)}
                className={`rounded-xl border py-1.5 px-2 text-xs font-medium transition-colors text-center ${
                  code === language
                    ? `border-primary/40 ${ACTIVE_CHIP}`
                    : 'border-slate-100 bg-slate-50/50 text-slate-600 hover:bg-slate-100'
                }`}
              >
                {t(LANGUAGE_LABEL_KEYS[code])}
              </button>
            ))}
          </div>
          <p className="text-[10px] text-slate-400 leading-tight">{t('config.languageHint')}</p>
        </div>

        {/* Persistent Local Security Note */}
        <div className="mt-auto pt-3 border-t border-slate-100 space-y-2.5">
          <div className="rounded-xl border border-slate-100 bg-slate-50/70 p-3 text-[11px] leading-relaxed text-slate-500">
            {t('config.localOnlyNotice')}
          </div>

          {/* Save Status & Action Controls */}
          <div className="rounded-xl border border-slate-100 bg-white/70 p-3 shadow-xs space-y-2.5">
            <div aria-live="polite" className="text-xs font-medium">
              {saved ? (
                <span className="flex items-center gap-1.5 text-emerald-600">
                  <CheckCircle2 className="w-4 h-4 shrink-0" /> {t('config.savedToFile')}
                </span>
              ) : dirty ? (
                <span className="flex items-center gap-1.5 text-amber-700 font-semibold">
                  <span className="w-2 h-2 rounded-full bg-amber-500 animate-ping shrink-0" />
                  {t('config.unsavedChanges')}
                </span>
              ) : (
                <span className="text-slate-400">{t('config.allSaved')}</span>
              )}
            </div>

            <div className="flex items-center gap-2">
              {dirty && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={discardChanges}
                  disabled={saving}
                  className="flex-1 text-xs"
                >
                  {t('config.discard')}
                </Button>
              )}
              <Button
                size="sm"
                onClick={handleSave}
                loading={saving}
                disabled={!dirty}
                icon={Save}
                className={`flex-1 text-xs ${dirty ? 'shadow-md shadow-primary/20' : ''}`}
              >
                {t('config.saveAll')}
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* ── Right Content Area ─────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0 h-full glass-card p-4 sm:p-6 overflow-hidden">
        {error && (
          <div className="mb-4 shrink-0">
            <ErrorBar message={t('config.error', { message: error })} />
          </div>
        )}

        {/* ── SECTION: Workspaces ── */}
        {activeSection === 'workspaces' && (
          <div className="flex-1 flex flex-col min-h-0">
            {/* Header / Filter Toolbar */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100 shrink-0">
              <div>
                <h3 className="text-base font-bold text-slate-800 flex items-center gap-2">
                  <Folder size={18} className="text-primary" /> {t('config.workspacesTitle')}
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">{t('config.workspacesSubtitle')}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {missingRowCount > 0 && (
                  <button
                    onClick={removeMissingPaths}
                    title={missingRowCount === 1
                      ? t('config.removeMissingTitleOne', { count: missingRowCount })
                      : t('config.removeMissingTitle', { count: missingRowCount })}
                    className="text-xs flex items-center gap-1.5 font-semibold text-amber-700 bg-amber-50 border border-amber-200 px-3 py-1.5 rounded-xl hover:bg-amber-100 transition-all"
                  >
                    <Eraser className="w-3.5 h-3.5" /> {missingRowCount === 1
                      ? t('config.removeMissingOne', { count: missingRowCount })
                      : t('config.removeMissing', { count: missingRowCount })}
                  </button>
                )}
                <Button variant="soft" icon={Plus} onClick={addProject}>
                  {t('config.addWorkspace')}
                </Button>
              </div>
            </div>

            {/* Search filter row */}
            {localProjects.length > 0 && (
              <div className="pt-3 pb-2 shrink-0">
                <SearchInput
                  type="text"
                  value={workspaceSearch}
                  onChange={e => setWorkspaceSearch(e.target.value)}
                  placeholder={t('config.searchWorkspaces')}
                  className="w-full sm:max-w-md"
                />
              </div>
            )}

            {/* Workspace cards list */}
            <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto pt-2 space-y-3 pr-1">
              {filteredProjects.map((p, i) => {
                const savedProject = projects.find(project => project.path === p.path.trim());
                const missing = Boolean(p.path.trim()) && savedProject?.available === false;
                const pathSegments = p.path.split('/').filter(Boolean);
                const folderName = pathSegments.pop() || (p.path ? p.path : `Workspace ${i + 1}`);

                return (
                  <div
                    key={p.uiId}
                    className="rounded-xl border border-slate-100 bg-slate-50/40 p-3 sm:p-4 hover:border-slate-200 hover:bg-white transition-all space-y-2.5 shadow-xs"
                  >
                    {/* Top Row: Icon + Folder Title + Group Badge + Quick Actions */}
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <Folder className="w-4 h-4 text-primary shrink-0" data-testid="workspace-folder-icon" />
                        <span className="text-sm font-semibold text-slate-800 truncate" title={folderName}>
                          {folderName}
                        </span>
                        {missing ? (
                          <span className="flex items-center gap-1 rounded-full bg-amber-50 border border-amber-200 px-2 py-0.5 text-[10px] font-bold text-amber-700 shrink-0">
                            <AlertTriangle className="w-3 h-3 text-amber-500" data-testid="workspace-status-missing" />
                            {t('config.pathMissing')}
                          </span>
                        ) : savedProject?.available === true ? (
                          <span className="flex items-center gap-1 rounded-full bg-emerald-50 border border-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-700 shrink-0">
                            <CheckCircle2 className="w-3 h-3 text-emerald-500" data-testid="workspace-status-available" />
                            {t('config.pathValid')}
                          </span>
                        ) : null}
                      </div>

                      <div className="flex items-center gap-2">
                        {p.path.trim() && !missing && (
                          <button
                            type="button"
                            onClick={() => openInTerminal(p.path)}
                            title={t('config.openInTerminal')}
                            className="flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-medium text-slate-600 hover:text-primary hover:bg-primary/10 transition-colors border border-slate-200"
                          >
                            <TerminalSquare size={13} />
                            <span>{t('config.openInTerminal')}</span>
                          </button>
                        )}
                        <Select
                          id={`project-group-${p.uiId}`}
                          aria-label={t('config.groupForWorkspace', { index: i + 1 })}
                          value={p.group}
                          onChange={(e) => updateProject(p.uiId, 'group', e.target.value)}
                          className="w-32 py-1 text-xs"
                        >
                          {availableGroups.map(g => <option key={g} value={g}>{g}</option>)}
                        </Select>
                        <button
                          aria-label={t('config.removeWorkspace', { name: p.path || i + 1 })}
                          title={t('config.unregisterWorkspace')}
                          onClick={() => removeProject(p.uiId)}
                          className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </div>

                    {/* Path Input Row */}
                    <div
                      className={`flex items-center gap-2.5 px-3 py-1.5 rounded-xl border shadow-xs transition-all focus-within:ring-2 focus-within:ring-primary/20 focus-within:border-primary ${
                        missing
                          ? 'border-amber-300 bg-amber-50/20'
                          : 'border-slate-200 bg-white/90'
                      }`}
                    >
                      <input
                        id={`project-path-${p.uiId}`}
                        type="text"
                        aria-label={t('config.workspacePath', { index: i + 1 })}
                        value={p.path}
                        onChange={(e) => updateProject(p.uiId, 'path', e.target.value)}
                        placeholder="/absolute/path/to/your/project"
                        className={`flex-1 min-w-0 bg-transparent border-none outline-none font-mono text-xs ${
                          missing ? 'text-amber-800 font-semibold' : 'text-slate-800'
                        }`}
                      />
                    </div>
                  </div>
                );
              })}

              {localProjects.length === 0 && (
                <div className="text-center py-12 space-y-3">
                  <div className="w-12 h-12 rounded-2xl bg-primary/10 text-primary flex items-center justify-center mx-auto">
                    <Folder size={24} />
                  </div>
                  <p className="text-slate-700 text-sm font-semibold">{t('config.noWorkspaces')}</p>
                  <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
                    {t('config.noWorkspacesHint')}
                    {' '}<code className="bg-slate-100 px-1 rounded text-slate-600 font-mono">/home/you/code/my-app</code>
                    {' '}{t('config.noWorkspacesHint2')}
                  </p>
                  <Button variant="soft" icon={Plus} onClick={addProject}>
                    {t('config.addFirstWorkspace')}
                  </Button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── SECTION: Groups ── */}
        {activeSection === 'groups' && (
          <div className="flex-1 flex flex-col min-h-0">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100 shrink-0">
              <div>
                <h3 className="text-base font-bold text-slate-800 flex items-center gap-2">
                  <Layers size={18} className="text-primary" /> {t('config.groupsTitle')}
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">{t('config.groupsSubtitle')}</p>
              </div>
              <div>
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
                      className="text-xs px-3 py-1.5 border border-primary/30 rounded-xl outline-none focus:ring-2 focus:ring-primary/20 w-36 font-mono"
                    />
                    <button
                      aria-label={t('config.confirmNewGroup')}
                      onClick={confirmAddGroup}
                      className="p-1.5 bg-primary/10 text-primary rounded-lg hover:bg-primary/20 transition-colors"
                    >
                      <Check className="w-4 h-4" />
                    </button>
                    <button
                      aria-label={t('config.cancelNewGroup')}
                      onClick={cancelAddGroup}
                      className="p-1.5 bg-slate-100 text-slate-500 rounded-lg hover:bg-slate-200 transition-colors"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ) : (
                  <Button variant="soft" icon={Plus} onClick={startAddingGroup}>
                    {t('config.newGroup')}
                  </Button>
                )}
              </div>
            </div>

            <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto pt-4 space-y-3 pr-1">
              {Object.entries(localGroups).map(([name, def]) => (
                <div
                  key={name}
                  className="flex flex-wrap items-center justify-between gap-3 p-4 border border-slate-100 rounded-xl bg-slate-50/30 hover:border-slate-200 hover:bg-white transition-all shadow-xs"
                >
                  <div className="flex flex-wrap items-center gap-3 min-w-0">
                    <span className="w-2.5 h-2.5 rounded-full bg-primary" />
                    <span className="font-bold text-sm text-slate-800 uppercase tracking-tight">{name}</span>
                    <span className="text-xs text-slate-500">
                      {t('config.groupCounts', {
                        skills: def.skills?.length ?? 0,
                        prompts: def.prompts?.length ?? 0,
                        hooks: def.hooks?.length ?? 0,
                        plugins: def.plugins?.length ?? 0,
                      })}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    {!dirty && (
                      <button
                        onClick={() => {
                          setCurrentGroup(name);
                          navigate(`/settings/resources?group=${encodeURIComponent(name)}`);
                        }}
                        className="flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-semibold text-primary bg-primary/5 hover:bg-primary/10 transition-colors border border-primary/20"
                      >
                        {t('config.viewResources')} <ArrowRight className="w-3.5 h-3.5" />
                      </button>
                    )}
                    {name !== 'codeagent' && name !== 'common' && (
                      <button
                        aria-label={t('config.removeGroup', { name })}
                        onClick={() => removeGroup(name)}
                        className="p-1.5 text-slate-400 hover:text-red-500 transition-colors rounded-lg hover:bg-red-50"
                      >
                        <Trash2 size={16} />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── SECTION: General ── */}
        {activeSection === 'general' && (
          <div className="flex-1 flex flex-col min-h-0 overflow-y-auto custom-scrollbar space-y-6 pr-1">
            <div className="pb-4 border-b border-slate-100 shrink-0">
              <h3 className="text-base font-bold text-slate-800 flex items-center gap-2">
                <Zap size={18} className="text-primary" /> {t('config.generalTitle')}
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">{t('config.generalSubtitle')}</p>
            </div>

            {/* Resource Root Configuration */}
            <div className="p-4 rounded-xl border border-slate-100 bg-slate-50/40 space-y-3">
              <label
                htmlFor="config-resource-root"
                className="text-xs font-semibold text-slate-700 uppercase tracking-wider flex items-center gap-2"
              >
                <Folder size={14} className="text-primary" /> {t('config.privateRoot')}
              </label>
              <Input
                id="config-resource-root"
                type="text"
                value={localConfig.paths?.resource_root || ''}
                onChange={(e) => {
                  setIsDirty(true);
                  const newPaths = { ...(localConfig.paths || {}), resource_root: e.target.value };
                  setLocalConfig({ ...localConfig, paths: newPaths });
                }}
                placeholder={t('config.privateRootPlaceholder')}
                className="w-full font-mono text-sm"
              />
              <p className="text-[11px] text-slate-500">
                {t('config.privateRootHintPrefix')}{' '}
                <code className="bg-slate-100 px-1 rounded text-slate-700 font-mono">$CODEAGENT</code>
                {t('config.privateRootHintSuffix')}
              </p>
            </div>

            {/* Language & Local Scope Summary Card */}
            <div className="p-4 rounded-xl border border-slate-100 bg-slate-50/40 space-y-3">
              <div className="text-xs font-semibold text-slate-700 flex items-center gap-2">
                <Languages size={14} className="text-primary" /> {t('language.label')}
              </div>
              <div className="flex gap-2">
                {SUPPORTED_LANGUAGES.map(code => (
                  <button
                    key={code}
                    type="button"
                    role="radio"
                    aria-checked={code === language}
                    onClick={() => chooseLanguage(code)}
                    className={`rounded-xl border px-4 py-2 text-xs font-semibold transition-colors ${
                      code === language
                        ? `border-primary/40 ${ACTIVE_CHIP}`
                        : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                    }`}
                  >
                    {t(LANGUAGE_LABEL_KEYS[code])}
                  </button>
                ))}
              </div>
              <p className="text-[11px] text-slate-500">{t('config.languageHint')}</p>
            </div>
          </div>
        )}

        {/* ── SECTION: Proxy ── */}
        {activeSection === 'proxy' && (
          <div className="flex-1 flex flex-col min-h-0">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100 shrink-0">
              <div>
                <h3 className="text-base font-bold text-slate-800 flex items-center gap-2">
                  <Globe size={18} className="text-primary" /> {t('config.proxyTitle')}
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">{t('config.proxySubtitle')}</p>
              </div>
              <Button variant="soft" icon={Plus} onClick={addProxy}>
                {t('config.addGateway')}
              </Button>
            </div>

            <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto pt-4 space-y-3 pr-1">
              {localProxies.map((p, i) => (
                <div
                  key={p.uiId}
                  className="flex flex-col sm:flex-row gap-3 sm:items-center bg-slate-50/40 p-3 rounded-xl border border-slate-100 hover:border-slate-200 hover:bg-white transition-all shadow-xs"
                >
                  <div className="flex-1 min-w-0">
                    <label htmlFor={`proxy-host-${p.uiId}`} className="text-[10px] uppercase font-bold text-slate-400 block mb-1">
                      {t('config.proxyHost', { index: i + 1 })}
                    </label>
                    <Input
                      id={`proxy-host-${p.uiId}`}
                      type="text"
                      aria-label={t('config.proxyHost', { index: i + 1 })}
                      value={p.host}
                      onChange={(e) => updateProxy(p.uiId, 'host', e.target.value)}
                      className="font-mono text-xs w-full"
                    />
                  </div>
                  <div className="w-full sm:w-28 shrink-0">
                    <label htmlFor={`proxy-port-${p.uiId}`} className="text-[10px] uppercase font-bold text-slate-400 block mb-1">
                      {t('config.proxyPort', { index: i + 1 })}
                    </label>
                    <Input
                      id={`proxy-port-${p.uiId}`}
                      type="number"
                      aria-label={t('config.proxyPort', { index: i + 1 })}
                      value={p.port}
                      onChange={(e) => updateProxy(p.uiId, 'port', parseInt(e.target.value) || 0)}
                      className="font-mono text-xs w-full"
                    />
                  </div>
                  <button
                    aria-label={t('config.removeProxy', { name: `${p.host}:${p.port}` })}
                    onClick={() => removeProxy(p.uiId)}
                    className="self-end sm:self-center p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors mt-4 sm:mt-0"
                  >
                    <Trash2 size={18} />
                  </button>
                </div>
              ))}

              {localProxies.length === 0 && (
                <div className="text-center py-12 space-y-2 text-slate-400 text-xs">
                  <Globe size={32} className="mx-auto text-slate-300 mb-2" />
                  <p>{t('config.proxySubtitle')}</p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ConfigHub;
