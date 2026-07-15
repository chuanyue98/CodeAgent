import { Activity, FolderGit2, Wifi, WifiOff } from 'lucide-react';
import type { ProviderCapabilities } from '../types/agent';

type Props = {
  validProjects: { path: string; group: string; available?: boolean }[];
  providers: ProviderCapabilities[];
  selectedProvider: string;
  workspace: string;
  connected: boolean;
  stateSessionId: string | null;
  stateActiveTurnId: string | null;
  connectionLabel: string;
  onWorkspaceChange: (value: string) => void;
  onProviderChange: (value: string) => void;
  onCurrentGroupChange: (group: string) => void;
  onShowActivityChange: (value: boolean) => void;
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
  onWorkspaceChange,
  onProviderChange,
  onCurrentGroupChange,
  onShowActivityChange,
}: Props) {
  const disabled = Boolean(stateSessionId) || Boolean(stateActiveTurnId);

  return (
    <div className="mb-3 flex items-end gap-2 border-b border-slate-100 pb-3">
      <label className="min-w-0 flex-1 text-[11px] font-medium text-slate-500">
        Workspace
        <span className="relative mt-1 flex">
          <FolderGit2 className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-400" />
          <select
            aria-label="Workspace"
            value={workspace}
            disabled={disabled}
            onChange={event => {
              onWorkspaceChange(event.target.value);
              const project = validProjects.find(
                item => item.path === event.target.value,
              );
              if (project) onCurrentGroupChange(project.group);
            }}
            className="w-full rounded-lg border border-slate-200 bg-white py-2 pl-8 pr-8 text-xs outline-none focus:border-primary disabled:opacity-60"
          >
            <option value="">Select a registered workspace</option>
            {validProjects.map(project => (
              <option key={project.path} value={project.path}>
                {project.path}
              </option>
            ))}
          </select>
        </span>
      </label>
      <label className="w-40 text-[11px] font-medium text-slate-500">
        Provider
        <select
          aria-label="Provider"
          value={selectedProvider}
          disabled={disabled}
          onChange={event => {
            onProviderChange(event.target.value);
          }}
          className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs outline-none focus:border-primary disabled:opacity-60"
        >
          <option value="">No provider</option>
          {providers.map(provider => (
            <option
              key={provider.providerId}
              value={provider.providerId}
              disabled={!provider.available}
            >
              {provider.displayName}
              {provider.available ? '' : ' (unavailable)'}
            </option>
          ))}
        </select>
      </label>
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
        aria-label="Open activity"
        title="Open activity"
        onClick={() => onShowActivityChange(true)}
        className="mb-0.5 rounded-lg border border-slate-200 p-2 text-slate-500 hover:bg-slate-50"
      >
        <Activity className="h-4 w-4" />
      </button>
    </div>
  );
}
