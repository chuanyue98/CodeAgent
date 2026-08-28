import { useCallback, useEffect, useMemo, useState } from 'react';
import { useIsMounted } from '../hooks/useAsyncGuards';
import { Pencil, Plus, Search, Server, Trash2 } from 'lucide-react';
import { Link } from 'react-router';
import { useProject } from '../context/ProjectContext';
import { useT } from '../i18n/context';
import request from '../utils/request';
import ConfirmDialog from './shared/ConfirmDialog';
import ErrorState from './shared/ErrorState';
import Modal from './shared/Modal';
import { fetchMcpServers, addMcpServer, removeMcpServer, type McpServer } from '../api/mcp';

interface Engine {
  id: string;
  name: string;
}

// codex and opencode register MCP servers in a single global config file
// regardless of cwd — confirmed live, see docs/mcp-cli-spike-results.md.
const GLOBAL_SCOPE_ENGINES = new Set(['codex', 'opencode']);

function parseEnvText(text: string): Record<string, string> {
  const env: Record<string, string> = {};
  for (const line of text.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const idx = trimmed.indexOf('=');
    if (idx === -1) continue;
    env[trimmed.slice(0, idx).trim()] = trimmed.slice(idx + 1).trim();
  }
  return env;
}

function envToText(env: Record<string, string>): string {
  return Object.entries(env).map(([k, v]) => `${k}=${v}`).join('\n');
}

/** Server form fields shared by the Add and Edit modal. */
interface ServerDraft {
  name: string;
  kind: 'local' | 'remote';
  command: string;
  url: string;
  envText: string;
}

const EMPTY_DRAFT: ServerDraft = { name: '', kind: 'local', command: '', url: '', envText: '' };

/**
 * MCP servers, laid out like the four resource galleries: engine list on the
 * left (the "category" axis), server cards in a grid, and add/edit in a modal
 * instead of a permanent side form — so every Settings tab reads as the same
 * feature with a different noun.
 */
export default function McpPage() {
  const { currentGroup, projects, selectedWorkspace } = useProject();
  const t = useT();
  const [engines, setEngines] = useState<Engine[]>([]);
  const [selectedEngine, setSelectedEngine] = useState('');
  const [projectPath, setProjectPath] = useState('');
  const [servers, setServers] = useState<McpServer[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [serverSearch, setServerSearch] = useState('');

  // Modal state: null = closed, a draft = add/edit form open. `editName`
  // distinguishes "add" from "edit <existing server>".
  const [draft, setDraft] = useState<ServerDraft | null>(null);
  const [editName, setEditName] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [pendingRemoveServer, setPendingRemoveServer] = useState<string | null>(null);

  const isMounted = useIsMounted();

  const groupProjects = useMemo(
    () => projects.filter(p => p.group === currentGroup),
    [projects, currentGroup],
  );

  const filteredServers = useMemo(() => {
    const q = serverSearch.trim().toLowerCase();
    if (!q) return servers;
    return servers.filter(server =>
      server.name.toLowerCase().includes(q) ||
      (server.url || '').toLowerCase().includes(q) ||
      (server.command || []).join(' ').toLowerCase().includes(q),
    );
  }, [servers, serverSearch]);

  useEffect(() => {
    request<Engine[]>('/api/engines')
      .then((list) => {
        if (!isMounted()) return;
        setEngines(list);
        if (list.length > 0) setSelectedEngine(prev => prev || list[0].id);
      })
      .catch(() => {
        if (!isMounted()) return;
        setError(t('mcp.loadEnginesFailed'));
      });
  }, [isMounted, t]);

  useEffect(() => {
    if (projectPath || groupProjects.length === 0) return;
    // Open on the workspace the user is already working in, when this group
    // contains it, rather than always snapping to the first path in the list.
    const shared = groupProjects.some(project => project.path === selectedWorkspace)
      ? selectedWorkspace
      : groupProjects[0].path;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setProjectPath(shared);
  }, [groupProjects, projectPath, selectedWorkspace]);

  const loadServers = useCallback(() => {
    if (!selectedEngine || !projectPath) {
      setServers([]);
      return;
    }
    fetchMcpServers(selectedEngine, projectPath)
      .then(list => {
        if (!isMounted()) return;
        setServers(list);
      })
      .catch(e => {
        if (!isMounted()) return;
        setError(e instanceof Error ? e.message : t('mcp.loadServersFailed'));
      });
  }, [selectedEngine, projectPath, isMounted, t]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadServers();
  }, [loadServers]);

  const retryServers = useCallback(() => {
    setError(null);
    loadServers();
  }, [loadServers]);

  // Editing a server from a different engine/project than the one it was
  // opened from would silently apply the edit to the wrong target, so drop
  // out of edit mode whenever either selector changes.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDraft(null);
    setEditName(null);
  }, [selectedEngine, projectPath]);

  const openAdd = () => {
    setEditName(null);
    setDraft({ ...EMPTY_DRAFT });
  };

  const openEdit = (server: McpServer) => {
    setEditName(server.name);
    setDraft({
      name: server.name,
      kind: server.url ? 'remote' : 'local',
      command: server.command ? server.command.join(' ') : '',
      url: server.url || '',
      envText: envToText(server.env || {}),
    });
    setError(null);
  };

  const closeModal = () => {
    setDraft(null);
    setEditName(null);
  };

  const handleSubmit = async () => {
    if (!draft || !selectedEngine || !projectPath || !draft.name.trim()) return;
    if (draft.kind === 'local' && !draft.command.trim()) return;
    if (draft.kind === 'remote' && !draft.url.trim()) return;

    const payload = {
      project: projectPath,
      name: draft.name.trim(),
      command: draft.kind === 'local' ? draft.command.trim().split(/\s+/) : undefined,
      url: draft.kind === 'remote' ? draft.url.trim() : undefined,
      env: parseEnvText(draft.envText),
    };

    setSubmitting(true);
    setError(null);
    try {
      if (editName) {
        // There's no in-place update in any of the four engines' own MCP
        // CLIs, so an edit is a remove-then-re-add under the hood. If the
        // re-add fails, the server is already gone -- say so plainly rather
        // than leaving the user to notice it missing later.
        await removeMcpServer(selectedEngine, editName, projectPath);
        try {
          await addMcpServer(selectedEngine, payload);
        } catch (addErr) {
          setError(
            t('mcp.removedButSaveFailed', {
              name: editName,
              error: addErr instanceof Error ? addErr.message : t('mcp.unknownError'),
            }),
          );
          closeModal();
          loadServers();
          return;
        }
      } else {
        await addMcpServer(selectedEngine, payload);
      }
      closeModal();
      loadServers();
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : editName ? t('mcp.updateFailed') : t('mcp.addFailed'),
      );
    } finally {
      setSubmitting(false);
    }
  };

  const confirmRemove = async () => {
    const serverName = pendingRemoveServer;
    if (!serverName) return;
    setPendingRemoveServer(null);
    try {
      await removeMcpServer(selectedEngine, serverName, projectPath);
      loadServers();
    } catch (e) {
      setError(e instanceof Error ? e.message : t('mcp.removeFailed'));
    }
  };

  return (
    <div className="flex h-full overflow-hidden p-6 gap-6">
      {/* Engine sidebar — mirrors the galleries' category sidebar. */}
      <div className="animate-slide-left stagger-1 w-64 shrink-0 glass-card flex flex-col overflow-hidden">
        <div className="p-6 border-b border-slate-100">
          <h2 className="text-sm font-semibold flex items-center gap-2 uppercase tracking-widest text-slate-400">
            <Server className="w-4 h-4 text-primary" />
            {t('mcp.engines')}
          </h2>
        </div>
        <div className="custom-scrollbar flex-1 overflow-y-auto p-4 space-y-1">
          {engines.map((engine, i) => (
            <button
              key={engine.id}
              onClick={() => setSelectedEngine(engine.id)}
              className={`animate-fade-rise stagger-${Math.min(i + 2, 7)} w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all ${
                selectedEngine === engine.id
                  ? 'bg-primary/10 text-primary'
                  : 'hover:bg-slate-50 text-slate-500 hover:text-slate-900'
              }`}
            >
              <span className="min-w-0 flex-1 truncate text-left">{engine.name}</span>
              {selectedEngine === engine.id && (
                <span className="text-[10px] px-2 py-0.5 rounded-full border border-primary/20 bg-primary/10 text-cyan-800">
                  {servers.length}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Server cards */}
      <div className="flex-1 flex flex-col min-w-0 gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-slate-400 font-medium shrink-0">
            {t('filters.workspace')}
            <select
              aria-label={t('filters.workspace')}
              value={projectPath}
              onChange={e => setProjectPath(e.target.value)}
              disabled={groupProjects.length === 0}
              className="px-3 py-1.5 text-sm border border-slate-200 rounded-lg bg-white focus:outline-none focus:border-primary"
            >
              {groupProjects.map(p => (
                <option key={p.path} value={p.path}>
                  {p.path}
                </option>
              ))}
            </select>
          </label>
          <div className="relative min-w-0 flex-1 max-w-72">
            <label htmlFor="mcp-server-search" className="sr-only">{t('mcp.searchLabel')}</label>
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
            <input
              id="mcp-server-search"
              type="text"
              value={serverSearch}
              onChange={e => setServerSearch(e.target.value)}
              placeholder={t('mcp.searchPlaceholder')}
              disabled={servers.length === 0}
              className="w-full pl-8 pr-3 py-1.5 text-xs border border-slate-200 rounded-lg bg-white focus:outline-none focus:border-primary disabled:opacity-50"
            />
          </div>
          <button
            onClick={openAdd}
            disabled={groupProjects.length === 0}
            title={groupProjects.length === 0 ? t('mcp.registerWorkspaceFirst') : t('mcp.addServerTitle')}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-xl hover:opacity-90 transition-all font-semibold text-sm disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Plus className="w-4 h-4" /> {t('mcp.addServer')}
          </button>
        </div>

        {groupProjects.length === 0 && (
          <div className="glass-card p-6 text-sm text-slate-500 text-center">
            {t('mcp.noWorkspaceForGroup', { group: currentGroup })}{' '}
            <Link to="/settings/workspace" className="font-semibold text-primary hover:underline">
              {t('mcp.registerInSettings')}
            </Link>。
          </div>
        )}

        {GLOBAL_SCOPE_ENGINES.has(selectedEngine) && (
          <div className="flex items-center gap-2 px-3 py-2 bg-amber-50/60 border border-amber-100 rounded-lg text-xs text-amber-700">
            {t('mcp.globalScopeNotice', { engine: selectedEngine === 'codex' ? 'Codex' : 'OpenCode' })}
          </div>
        )}

        {error && <ErrorState message={error} onRetry={retryServers} />}

        <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto">
          {servers.length === 0 ? (
            <div className="glass-card p-10 text-center">
              <p className="text-sm text-slate-400">{t('mcp.noServers')}</p>
            </div>
          ) : filteredServers.length === 0 ? (
            <div className="glass-card p-10 text-center text-sm text-slate-400">
              {t('mcp.noSearchMatch')}
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 pb-2">
              {filteredServers.map((server, i) => (
                <div
                  key={server.name}
                  className={`animate-fade-rise stagger-${Math.min(i + 3, 7)} glass-card p-4 flex flex-col gap-2 group`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="p-2 rounded-xl bg-slate-100 text-slate-500 shrink-0">
                        <Server className="w-4 h-4" />
                      </span>
                      <span className="font-semibold text-sm text-slate-800 truncate" title={server.name}>
                        {server.name}
                      </span>
                    </div>
                    <div className="flex items-center gap-1 shrink-0 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
                      <button
                        onClick={() => openEdit(server)}
                        aria-label={t('mcp.editServer', { name: server.name })}
                        title={t('common.edit')}
                        className="p-1.5 text-slate-400 hover:text-primary transition-colors"
                      >
                        <Pencil className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => setPendingRemoveServer(server.name)}
                        aria-label={t('mcp.removeServer', { name: server.name })}
                        title={t('common.remove')}
                        className="p-1.5 text-slate-400 hover:text-red-500 transition-colors"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                  <div className="text-xs text-slate-400 font-mono break-all line-clamp-2">
                    {server.url || (server.command ? server.command.join(' ') : '')}
                  </div>
                  <div className="mt-auto flex flex-wrap gap-1.5">
                    <span className="text-[10px] px-1.5 py-0.5 bg-slate-100 text-slate-500 rounded font-mono">
                      {server.transport}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 bg-slate-100 text-slate-500 rounded">
                      {server.scope}
                    </span>
                    {server.env && Object.keys(server.env).length > 0 && (
                      <span className="text-[10px] px-1.5 py-0.5 bg-slate-100 text-slate-500 rounded">
                        {t('mcp.envCount', { count: Object.keys(server.env).length })}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {draft && (
        <Modal onClose={closeModal} ariaLabelledBy="mcp-modal-title">
          <h3 id="mcp-modal-title" className="text-lg font-semibold text-slate-800">
            {editName ? t('mcp.editTitle', { name: editName }) : t('mcp.addTitle')}
          </h3>
          <div className="space-y-3">
            <div>
              <label htmlFor="mcp-name" className="text-xs text-slate-400 font-medium block mb-1">{t('mcp.name')}</label>
              <input
                id="mcp-name"
                type="text"
                value={draft.name}
                onChange={e => setDraft({ ...draft, name: e.target.value })}
                placeholder="my-server"
                className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white focus:outline-none focus:border-primary"
              />
            </div>
            <div className="flex gap-2 text-xs">
              <button
                onClick={() => setDraft({ ...draft, kind: 'local' })}
                className={`flex-1 px-2 py-1.5 rounded-md font-medium transition-colors ${
                  draft.kind === 'local' ? 'bg-primary/10 text-primary' : 'text-slate-500 hover:bg-slate-50'
                }`}
              >
                {t('mcp.localStdio')}
              </button>
              <button
                onClick={() => setDraft({ ...draft, kind: 'remote' })}
                className={`flex-1 px-2 py-1.5 rounded-md font-medium transition-colors ${
                  draft.kind === 'remote' ? 'bg-primary/10 text-primary' : 'text-slate-500 hover:bg-slate-50'
                }`}
              >
                {t('mcp.remoteUrl')}
              </button>
            </div>
            {draft.kind === 'local' ? (
              <div>
                <label htmlFor="mcp-command" className="text-xs text-slate-400 font-medium block mb-1">{t('mcp.command')}</label>
                <input
                  id="mcp-command"
                  type="text"
                  value={draft.command}
                  onChange={e => setDraft({ ...draft, command: e.target.value })}
                  placeholder="npx my-mcp-server --flag"
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white font-mono focus:outline-none focus:border-primary"
                />
              </div>
            ) : (
              <div>
                <label htmlFor="mcp-url" className="text-xs text-slate-400 font-medium block mb-1">URL</label>
                <input
                  id="mcp-url"
                  type="text"
                  value={draft.url}
                  onChange={e => setDraft({ ...draft, url: e.target.value })}
                  placeholder="https://mcp.example.com/mcp"
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white font-mono focus:outline-none focus:border-primary"
                />
              </div>
            )}
            <div>
              <label htmlFor="mcp-env" className="text-xs text-slate-400 font-medium block mb-1">
                {t('mcp.environment')}
              </label>
              <textarea
                id="mcp-env"
                value={draft.envText}
                onChange={e => setDraft({ ...draft, envText: e.target.value })}
                rows={3}
                placeholder="API_KEY=xxx"
                className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white font-mono focus:outline-none focus:border-primary resize-none"
              />
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <button
              onClick={closeModal}
              className="px-4 py-2 border border-slate-200 text-slate-600 rounded-xl hover:bg-slate-50 transition-colors font-medium text-sm"
            >
              {t('common.cancel')}
            </button>
            <button
              onClick={() => void handleSubmit()}
              disabled={
                submitting ||
                !projectPath ||
                !draft.name.trim() ||
                (draft.kind === 'local' ? !draft.command.trim() : !draft.url.trim())
              }
              className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-90 transition-all"
            >
              {editName
                ? (submitting ? t('mcp.saving') : t('mcp.saveChanges'))
                : <><Plus className="w-4 h-4" /> {submitting ? t('mcp.adding') : t('mcp.addServer')}</>}
            </button>
          </div>
        </Modal>
      )}

      {pendingRemoveServer && (
        <ConfirmDialog
          title={t('mcp.confirmRemoveTitle')}
          description={t('mcp.confirmRemoveDescription', { name: pendingRemoveServer, engine: selectedEngine })}
          confirmLabel={t('common.remove')}
          onConfirm={() => void confirmRemove()}
          onCancel={() => setPendingRemoveServer(null)}
        />
      )}
    </div>
  );
}
