import { Activity, FolderGit2, Layers, Wifi, WifiOff } from 'lucide-react';
import type { PermissionMode, ProviderCapabilities } from '../types/agent';
import { workspaceLabel } from '../utils/agentWorkspaceHelpers';

type Props = {
  validProjects: { path: string; group: string; available?: boolean }[];
  providers: ProviderCapabilities[];
  selectedProvider: string;
  workspace: string;
  connected: boolean;
  stateSessionId: string | null;
  stateActiveTurnId: string | null;
  connectionLabel: string;
  permissionMode: PermissionMode;
  currentGroup: string;
  onWorkspaceChange: (value: string) => void;
  onProviderChange: (value: string) => void;
  onShowActivityChange: (value: boolean) => void;
  onPermissionModeChange: (value: PermissionMode) => void;
};

export default function AgentToolbar({
  validProjects,
  providers,
  selectedProvider,
  workspace,
  connected,
  stateSessionId,
  stateActiveTurnId,
  connectionLabel,
  permissionMode,
  currentGroup,
  onWorkspaceChange,
  onProviderChange,
  onShowActivityChange,
  onPermissionModeChange,
}: Props) {
  const disabled = Boolean(stateSessionId) || Boolean(stateActiveTurnId);
  const activeProject = validProjects.find(project => project.path === workspace);

  return (
    <div className="mb-3 flex flex-wrap items-end gap-2 border-b border-slate-100 pb-3">
      {/* basis-56 (not flex-1 alone) so the most important control keeps a
          readable width and the row wraps instead of shrinking it to "Sele…". */}
      <label className="min-w-0 flex-1 basis-56 text-[11px] font-medium text-slate-500">
        工作区
        <span className="relative mt-1 flex">
          <FolderGit2 className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-400" />
          <select
            aria-label="工作区"
            value={workspace}
            disabled={disabled}
            onChange={event => {
              // Selecting a workspace also switches the resource group --
              // ProjectContext owns that pairing, so no extra call here.
              onWorkspaceChange(event.target.value);
            }}
            className="w-full rounded-lg border border-slate-200 bg-white py-2 pl-8 pr-8 text-xs outline-none focus:border-primary disabled:opacity-60"
          >
            <option value="">选择已注册的工作区</option>
            {validProjects.map(project => (
              <option key={project.path} value={project.path}>
                {workspaceLabel(project.path)} — {project.path}
              </option>
            ))}
          </select>
        </span>
        {activeProject && (
          // No `title` here on purpose: the sidebar already exposes each
          // workspace row under title={path}, and a second element carrying
          // the same path makes that row ambiguous to title-based lookups.
          <span className="mt-1 block truncate text-[10px] font-normal text-slate-400">
            {activeProject.path}
          </span>
        )}
      </label>
      <label className="w-40 text-[11px] font-medium text-slate-500">
        引擎
        <select
          aria-label="引擎"
          value={selectedProvider}
          disabled={disabled}
          onChange={event => {
            onProviderChange(event.target.value);
          }}
          className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs outline-none focus:border-primary disabled:opacity-60"
        >
          <option value="">无引擎</option>
          {providers.map(provider => (
            <option
              key={provider.providerId}
              value={provider.providerId}
              disabled={!provider.available}
            >
              {provider.displayName}
              {provider.available ? '' : '（不可用）'}
            </option>
          ))}
        </select>
      </label>
      <label className="w-40 text-[11px] font-medium text-slate-500">
        权限
        <select
          aria-label="权限模式"
          // Permission mode is the highest-consequence control here, and
          // "workspace-write" says nothing about what it permits. Spell out
          // the blast radius rather than assuming the term is understood.
          title={
            permissionMode === 'workspace-write'
              ? '智能体可以在所选工作区内读写文件，并在运行命令前询问。'
              : '智能体只能读取文件，不能修改工作区中的任何内容。'
          }
          value={permissionMode}
          disabled={disabled}
          onChange={event => onPermissionModeChange(event.target.value as PermissionMode)}
          className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs outline-none focus:border-primary disabled:opacity-60"
        >
          <option value="workspace-write">可编辑文件</option>
          <option value="read-only">只读</option>
        </select>
      </label>
      <span
        title={`会话开始时将从资源组 "${currentGroup}" 注入资源`}
        className="mb-0.5 flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 px-2 py-2 text-[10px] font-semibold text-slate-500"
      >
        <Layers className="h-3 w-3" />
        {currentGroup}
      </span>
      <span
        title={connectionLabel}
        className={`mb-0.5 flex items-center gap-1 rounded-lg border px-2 py-2 text-[10px] font-semibold ${
          connected
            ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
            : stateSessionId
              ? 'border-amber-200 bg-amber-50 text-amber-800'
              : 'border-slate-200 bg-slate-50 text-slate-500'
        }`}
      >
        {connected ? (
          <Wifi className="h-3 w-3" />
        ) : (
          <WifiOff className="h-3 w-3" />
        )}
        {connectionLabel}
      </span>
      <button
        aria-label="查看回合事件"
        title="查看回合事件"
        onClick={() => onShowActivityChange(true)}
        className="mb-0.5 rounded-lg border border-slate-200 p-2 text-slate-500 hover:bg-slate-50"
      >
        <Activity className="h-4 w-4" />
      </button>
    </div>
  );
}
