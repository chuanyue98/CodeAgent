import { useCallback, useEffect, useMemo, useState } from 'react';
import { Server, Plus, Trash2, AlertCircle, Info } from 'lucide-react';
import { useProject } from '../context/ProjectContext';
import request from '../utils/request';
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

export default function McpPage() {
  const { currentGroup, projects } = useProject();
  const [engines, setEngines] = useState<Engine[]>([]);
  const [selectedEngine, setSelectedEngine] = useState('');
  const [projectPath, setProjectPath] = useState('');
  const [servers, setServers] = useState<McpServer[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState('');
  const [kind, setKind] = useState<'local' | 'remote'>('local');
  const [command, setCommand] = useState('');
  const [url, setUrl] = useState('');
  const [envText, setEnvText] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const groupProjects = useMemo(
    () => projects.filter(p => p.group === currentGroup),
    [projects, currentGroup],
  );

  useEffect(() => {
    request<Engine[]>('/api/engines')
      .then((list) => {
        setEngines(list);
        if (list.length > 0) setSelectedEngine(prev => prev || list[0].id);
      })
      .catch(() => setError('Failed to load engines'));
  }, []);

  useEffect(() => {
    if (!projectPath && groupProjects.length > 0) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setProjectPath(groupProjects[0].path);
    }
  }, [groupProjects, projectPath]);

  const loadServers = useCallback(() => {
    if (!selectedEngine || !projectPath) {
      setServers([]);
      return;
    }
    fetchMcpServers(selectedEngine, projectPath)
      .then(setServers)
      .catch(e => setError(e instanceof Error ? e.message : 'Failed to load MCP servers'));
  }, [selectedEngine, projectPath]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadServers();
  }, [loadServers]);

  const handleAdd = async () => {
    if (!selectedEngine || !projectPath || !name.trim()) return;
    if (kind === 'local' && !command.trim()) return;
    if (kind === 'remote' && !url.trim()) return;

    setSubmitting(true);
    setError(null);
    try {
      await addMcpServer(selectedEngine, {
        project: projectPath,
        name: name.trim(),
        command: kind === 'local' ? command.trim().split(/\s+/) : undefined,
        url: kind === 'remote' ? url.trim() : undefined,
        env: parseEnvText(envText),
      });
      setName('');
      setCommand('');
      setUrl('');
      setEnvText('');
      loadServers();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add MCP server');
    } finally {
      setSubmitting(false);
    }
  };

  const handleRemove = async (serverName: string) => {
    try {
      await removeMcpServer(selectedEngine, serverName, projectPath);
      loadServers();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to remove MCP server');
    }
  };

  return (
    <div className="flex flex-col xl:flex-row gap-4 min-h-full xl:h-full">
      <aside className="w-full xl:w-56 shrink-0 glass-card p-4 space-y-1">
        <label className="text-xs text-slate-400 font-medium block mb-2">Engine</label>
        {engines.map(engine => (
          <button
            key={engine.id}
            onClick={() => setSelectedEngine(engine.id)}
            className={`w-full text-left px-2 py-1.5 rounded-md text-xs transition-colors ${
              selectedEngine === engine.id
                ? 'bg-slate-100 text-slate-800 font-medium'
                : 'text-slate-500 hover:bg-slate-50'
            }`}
          >
            {engine.name}
          </button>
        ))}
      </aside>

      <div className="flex-1 min-w-0 flex flex-col gap-4">
        <div className="glass-card p-4 flex flex-wrap items-center gap-3">
          <Server className="w-4 h-4 text-slate-400 shrink-0" />
          <label className="text-xs text-slate-400 font-medium shrink-0">Project</label>
          {groupProjects.length > 0 ? (
            <select
              value={projectPath}
              onChange={e => setProjectPath(e.target.value)}
              className="flex-1 px-3 py-1.5 text-sm border border-slate-200 rounded-lg bg-white focus:outline-none focus:border-primary"
            >
              {groupProjects.map(p => (
                <option key={p.path} value={p.path}>
                  {p.path}
                </option>
              ))}
            </select>
          ) : (
            <span className="min-w-0 text-xs text-slate-400 italic">
              No projects registered for group "{currentGroup}" — add one in Configuration.
            </span>
          )}
        </div>

        {GLOBAL_SCOPE_ENGINES.has(selectedEngine) && (
          <div className="flex items-center gap-2 px-3 py-2 bg-amber-50/60 border border-amber-100 rounded-lg text-xs text-amber-700">
            <Info className="w-3.5 h-3.5 shrink-0" />
            {selectedEngine === 'codex' ? 'Codex' : 'OpenCode'} stores MCP servers in a single
            global config file, not scoped per project — servers added here apply everywhere this
            engine runs, regardless of which project is selected above.
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 px-3 py-2 bg-red-50/60 border border-red-100 rounded-lg text-xs text-red-600">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" /> {error}
          </div>
        )}

        <div className="flex flex-col lg:flex-row gap-4 flex-1 min-h-0">
          <div className="flex-1 glass-card p-4 overflow-y-auto space-y-2">
            <div className="text-sm font-semibold text-slate-700 mb-2">Configured Servers</div>
            {servers.length === 0 && (
              <p className="text-sm text-slate-400 text-center py-8">No MCP servers configured.</p>
            )}
            {servers.map(server => (
              <div
                key={server.name}
                className="glass-card p-3 border-slate-100 flex items-center gap-3"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm text-slate-800 truncate">
                      {server.name}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 bg-slate-100 text-slate-500 rounded font-mono">
                      {server.transport}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 bg-slate-100 text-slate-500 rounded">
                      {server.scope}
                    </span>
                  </div>
                  <div className="text-xs text-slate-400 mt-0.5 font-mono truncate">
                    {server.url || (server.command ? server.command.join(' ') : '')}
                  </div>
                </div>
                <button
                  onClick={() => void handleRemove(server.name)}
                  title="Remove"
                  className="shrink-0 p-1.5 text-slate-400 hover:text-red-500 transition-colors"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>

          <div className="w-full lg:w-80 shrink-0 glass-card p-4 space-y-3">
            <div className="text-sm font-semibold text-slate-700">Add Server</div>

            <div>
              <label className="text-xs text-slate-400 font-medium block mb-1">Name</label>
              <input
                type="text"
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="my-server"
                className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white focus:outline-none focus:border-primary"
              />
            </div>

            <div className="flex gap-2 text-xs">
              <button
                onClick={() => setKind('local')}
                className={`flex-1 px-2 py-1.5 rounded-md font-medium transition-colors ${
                  kind === 'local' ? 'bg-primary/10 text-primary' : 'text-slate-500 hover:bg-slate-50'
                }`}
              >
                Local (stdio)
              </button>
              <button
                onClick={() => setKind('remote')}
                className={`flex-1 px-2 py-1.5 rounded-md font-medium transition-colors ${
                  kind === 'remote' ? 'bg-primary/10 text-primary' : 'text-slate-500 hover:bg-slate-50'
                }`}
              >
                Remote (URL)
              </button>
            </div>

            {kind === 'local' ? (
              <div>
                <label className="text-xs text-slate-400 font-medium block mb-1">Command</label>
                <input
                  type="text"
                  value={command}
                  onChange={e => setCommand(e.target.value)}
                  placeholder="npx my-mcp-server --flag"
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white font-mono focus:outline-none focus:border-primary"
                />
              </div>
            ) : (
              <div>
                <label className="text-xs text-slate-400 font-medium block mb-1">URL</label>
                <input
                  type="text"
                  value={url}
                  onChange={e => setUrl(e.target.value)}
                  placeholder="https://mcp.example.com/mcp"
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white font-mono focus:outline-none focus:border-primary"
                />
              </div>
            )}

            <div>
              <label className="text-xs text-slate-400 font-medium block mb-1">
                Environment (one KEY=VALUE per line)
              </label>
              <textarea
                value={envText}
                onChange={e => setEnvText(e.target.value)}
                rows={3}
                placeholder="API_KEY=xxx"
                className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white font-mono focus:outline-none focus:border-primary resize-none"
              />
            </div>

            <button
              onClick={() => void handleAdd()}
              disabled={
                submitting ||
                !projectPath ||
                !name.trim() ||
                (kind === 'local' ? !command.trim() : !url.trim())
              }
              className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-primary text-white rounded-lg text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed hover:scale-[1.02] active:scale-95 transition-all"
            >
              <Plus className="w-4 h-4" /> Add Server
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
