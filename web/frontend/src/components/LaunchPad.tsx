import { useEffect, useState } from 'react';
import { AlertTriangle, TerminalSquare, X } from 'lucide-react';
import { fetchPtyStatus } from '../api/pty';
import { useProject } from '../context/ProjectContext';
import BrowserTerminal from './BrowserTerminal';

interface Engine {
  id: string;
  name: string;
  description: string;
  color: string;
}

// The UI language is Chinese; keep engine names (Claude/Gemini/...) as brands.
const ENGINES: Engine[] = [
  { id: 'claude',    name: 'Claude',    description: 'Anthropic · Claude Code CLI',      color: 'bg-orange-50 border-orange-200 text-orange-700' },
  { id: 'gemini',    name: 'Gemini',    description: 'Google · Gemini CLI',              color: 'bg-blue-50 border-blue-200 text-blue-700' },
  { id: 'opencode',  name: 'OpenCode',  description: '本地 npm CLI，带完整 TUI',           color: 'bg-violet-50 border-violet-200 text-violet-700' },
  { id: 'codex',     name: 'Codex',     description: 'OpenAI · Codex CLI',               color: 'bg-emerald-50 border-emerald-200 text-emerald-700' },
];

export default function LaunchPad() {
  const {
    validProjects,
    selectedWorkspace,
    setSelectedWorkspace,
  } = useProject();

  const [available, setAvailable] = useState<boolean | null>(null);
  const [reason, setReason] = useState<string | null>(null);
  const [activeSession, setActiveSession] = useState<{ engine: string; cwd: string } | null>(null);

  useEffect(() => {
    fetchPtyStatus()
      .then(status => {
        setAvailable(status.available);
        setReason(status.reason);
      })
      .catch(err => {
        setAvailable(false);
        setReason(err instanceof Error ? err.message : '检测浏览器终端支持失败');
      });
  }, []);

  const effectiveProject = validProjects.some(project => project.path === selectedWorkspace)
    ? selectedWorkspace
    : (validProjects[0]?.path ?? '');

  if (activeSession) {
    return (
      <div className="flex h-full min-h-0 flex-col gap-2">
        <div className="flex shrink-0 items-center justify-between">
          <div className="text-sm font-medium text-slate-700">
            {ENGINES.find(engine => engine.id === activeSession.engine)?.name} · {activeSession.cwd}
          </div>
          <button
            onClick={() => setActiveSession(null)}
            className="flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
          >
            <X size={14} /> 关闭终端
          </button>
        </div>
        <BrowserTerminal
          engine={activeSession.engine}
          cwd={activeSession.cwd}
          onExit={() => {}}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <p className="text-sm text-slate-600">
          在浏览器终端中打开引擎 CLI，运行在托管 CodeAgent 的本机上。
        </p>
        <p className="text-xs text-slate-400">
          相应 CLI 必须已在本机安装并登录。与 Web Agent 不同，终端展示的是引擎自己的界面——CodeAgent
          只负责设置工作目录并注入你配置的资源。
        </p>
      </div>

      {available === false && (
        <div role="status" className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-semibold">浏览器终端不可用</p>
            <p className="mt-0.5 text-xs">{reason}</p>
          </div>
        </div>
      )}

      {validProjects.length === 0 ? (
        <div role="status" className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
          打开终端前请先在“设置”中注册一个工作区。
        </div>
      ) : (
        <div className="max-w-sm space-y-1">
          <label htmlFor="launchpad-project" className="text-xs font-medium text-slate-500">工作区</label>
          <select
            id="launchpad-project"
            value={effectiveProject}
            onChange={event => setSelectedWorkspace(event.target.value)}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
          >
            {validProjects.map(project => (
              <option key={project.path} value={project.path}>{project.path}</option>
            ))}
          </select>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {ENGINES.map((engine) => (
          <div
            key={engine.id}
            className="glass-card p-6 flex items-center justify-between gap-4"
          >
            <div className="space-y-1">
              <div className="font-semibold text-slate-800">{engine.name}</div>
              <div className="text-xs text-slate-500">{engine.description}</div>
            </div>

            <button
              onClick={() => setActiveSession({ engine: engine.id, cwd: effectiveProject })}
              disabled={!available || !effectiveProject}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium border transition-all
                ${!available || !effectiveProject
                  ? 'opacity-50 cursor-not-allowed'
                  : 'hover:scale-105 active:scale-95 cursor-pointer'}
                ${engine.color}`}
            >
              <TerminalSquare size={15} />
              打开终端
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
