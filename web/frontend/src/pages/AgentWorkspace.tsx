import ChatPage from '../components/ChatPage';
import AgentActivityPanel from '../components/AgentActivityPanel';
import AgentComposer from '../components/AgentComposer';
import AgentSessionBanner from '../components/AgentSessionBanner';
import AgentToolbar from '../components/AgentToolbar';
import AgentWorkspaceSidebar from '../components/AgentWorkspaceSidebar';
import useAgentWorkspace from './useAgentWorkspace';

export default function AgentWorkspace() {
  const workspace = useAgentWorkspace();

  if (workspace.legacyMode) {
    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between rounded-xl border border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-900">
          <span>Legacy chat uses one-shot provider processes and has limited interaction.</span>
          <button className="font-semibold underline" onClick={workspace.onSetLegacyMode}>Try Agent Gateway</button>
        </div>
        <ChatPage />
      </div>
    );
  }

  /* eslint-disable react-hooks/refs */
  return (
    <div className="flex min-h-full gap-3 lg:h-full">
      <AgentWorkspaceSidebar
        validProjects={workspace.validProjects}
        validProjectPaths={workspace.validProjectPaths}
        sessions={workspace.sessions}
        nativeSessionsByProvider={workspace.nativeSessionsByProvider}
        nativeLoadingProviders={workspace.nativeLoadingProviders}
        nativeSessionErrors={workspace.nativeSessionErrors}
        selectedProvider={workspace.selectedProvider}
        sessionSearch={workspace.sessionSearch}
        gatewaySessionLimit={workspace.gatewaySessionLimit}
        nativeSessionLimit={workspace.nativeSessionLimit}
        unavailableSessionLimit={workspace.unavailableSessionLimit}
        showUnavailableHistory={workspace.showUnavailableHistory}
        expandedWorkspaces={workspace.expandedWorkspaces}
        collapsedWorkspaces={workspace.collapsedWorkspaces}
        workspace={workspace.workspace}
        state={workspace.state}
        loading={workspace.loading}
        selectingKey={workspace.selectingKey}
        providers={workspace.providers}
        onNewSession={workspace.onNewSession}
        onSelectSession={workspace.onSelectSession}
        onSelectNativeSession={workspace.onSelectNativeSession}
        onRemoveSession={workspace.onRemoveSession}
        onRetryNativeSessions={workspace.onRetryNativeSessions}
        onSearchChange={workspace.onSearchChange}
        onGatewayLimitChange={workspace.onGatewayLimitChange}
        onNativeLimitChange={workspace.onNativeLimitChange}
        onUnavailableLimitChange={workspace.onUnavailableLimitChange}
        onToggleExpandedWorkspace={workspace.onToggleExpandedWorkspace}
        onToggleCollapsedWorkspace={workspace.onToggleCollapsedWorkspace}
        onShowUnavailableHistoryChange={workspace.onShowUnavailableHistoryChange}
        onSetLegacyMode={workspace.onSetLegacyMode}
      />

      <section className="glass-card flex min-w-0 flex-1 flex-col p-4">
        <AgentToolbar
          validProjects={workspace.validProjects}
          providers={workspace.providers}
          selectedProvider={workspace.selectedProvider}
          workspace={workspace.workspace}
          connected={workspace.connected}
          stateSessionId={workspace.state.session?.id ?? null}
          stateActiveTurnId={workspace.state.activeTurnId}
          connectionLabel={workspace.connectionLabel}
          onWorkspaceChange={workspace.onWorkspaceChange}
          onProviderChange={workspace.onProviderChange}
          onCurrentGroupChange={workspace.onSetCurrentGroup}
          onShowActivityChange={workspace.onShowActivityChange}
        />

        {workspace.validProjects.length === 0 && (
          <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            Register an available workspace before starting an Agent session.{' '}
            <a href="/settings/workspace" className="font-semibold underline">Open Workspace settings</a>
          </div>
        )}
        {workspace.noGatewayProvider && (
          <div className="mb-3 flex items-start justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            <div>
              <p className="font-semibold">No interactive provider is available</p>
              <p className="mt-0.5">{workspace.providers[0]?.unavailableReason || 'The Agent Gateway could not start.'}</p>
            </div>
            <button className="shrink-0 font-semibold underline" onClick={workspace.onSetLegacyMode}>Use legacy chat</button>
          </div>
        )}
        {workspace.error && (
          <div className="mb-3 flex items-center justify-between gap-3 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-700">
            <span className="flex items-center gap-2">{workspace.error}</span>
            {workspace.error.startsWith('Register this workspace before resuming:') ? (
              <a href="/settings/workspace" className="shrink-0 font-semibold underline">Open Workspace settings</a>
            ) : null}
          </div>
        )}

        {workspace.state.session && (() => {
          const session = workspace.state.session;
          return (
            <AgentSessionBanner
              session={session}
              connected={workspace.connected}
              connecting={workspace.connecting}
              stateActiveTurnId={workspace.state.activeTurnId}
              sessionResourceSnapshot={workspace.sessionResourceSnapshot}
              sessionResourceGroup={workspace.sessionResourceGroup}
              resourceCount={workspace.resourceCount}
              onConnect={() => workspace.onConnect(session, workspace.state.lastSequence, false)}
              onRemoveSession={() => workspace.onRemoveSession(session)}
            />
          );
        })()}

        <div className="relative min-h-0 flex-1">
          <div
            ref={workspace.setScrollRef}
            onScroll={workspace.onScroll}
            className="custom-scrollbar h-full space-y-3 overflow-y-auto pr-1"
          >
            {workspace.state.messages.length === 0 && !workspace.state.activeTurnId && (
              <div className="flex h-full min-h-48 flex-col items-center justify-center text-center text-slate-400">
                <p className="text-sm font-medium text-slate-600">
                  {!workspace.workspace ? 'Choose a workspace to begin' : !workspace.selectedProvider ? 'Choose a provider to begin' : 'Start a new conversation'}
                </p>
                <p className="mt-1 max-w-md text-xs">
                  {!workspace.workspace
                    ? 'Select a registered workspace above. The agent will only operate inside that directory.'
                    : !workspace.selectedProvider
                      ? 'Select an available provider to start an interactive session.'
                      : `Send a message to start ${workspace.selectedCapabilities?.displayName || 'the agent'} in ${workspace.workspace}.`}
                </p>
                {workspace.canCompose && (
                  <button
                    onClick={workspace.focusComposer}
                    className="mt-4 rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-white hover:bg-primary/90"
                  >Start with {workspace.selectedCapabilities?.displayName || workspace.selectedProvider}</button>
                )}
              </div>
            )}
            {workspace.state.messages.map(message => (
              <div
                key={message.id}
                className={`max-w-[85%] rounded-xl px-4 py-2.5 text-sm ${
                  message.role === 'user'
                    ? 'ml-auto bg-primary/10 text-slate-800'
                    : message.role === 'error'
                      ? 'border border-red-100 bg-red-50 text-red-700'
                      : 'border border-slate-100 bg-slate-50 text-slate-700'
                }`}
              >
                {message.role === 'assistant'
                  ? <div className="prose prose-sm prose-slate max-w-none break-words">{message.text || '…'}</div>
                  : <span className="whitespace-pre-wrap">{message.text}</span>}
              </div>
            ))}
            {workspace.state.activeTurnId && !workspace.state.messages.some(message => message.pending) && (
              <div className="flex max-w-[85%] items-center gap-2 rounded-xl border border-slate-100 bg-slate-50 px-4 py-2.5 text-sm text-slate-400">
                Working…
              </div>
            )}
          </div>
          {workspace.showScrollToBottom && (
            <button
              onClick={() => workspace.scrollToLatest()}
              className="absolute bottom-3 right-3 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-semibold text-primary shadow-md hover:bg-slate-50"
            >
              Jump to latest
            </button>
          )}
        </div>

        {workspace.state.approvals.map(approval => (
          <div key={approval.id} className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-950">
            <p className="font-semibold">Approval required</p>
            {approval.reason && <p className="mt-1 text-amber-800">{approval.reason}</p>}
            {approval.command && <pre className="mt-2 overflow-x-auto rounded-lg bg-slate-900 p-2 text-[11px] text-slate-100">{approval.command}</pre>}
            {approval.cwd && <p className="mt-1 break-all text-[10px] text-amber-700">Working directory: {approval.cwd}</p>}
            <div className="mt-2 flex justify-end gap-2">
              <button onClick={() => workspace.onRespondApproval(approval.id, 'cancel')} className="rounded-lg border border-amber-300 px-3 py-1.5 font-semibold hover:bg-amber-100">Cancel turn</button>
              <button onClick={() => workspace.onRespondApproval(approval.id, 'decline')} className="rounded-lg border border-amber-300 px-3 py-1.5 font-semibold hover:bg-amber-100">Decline</button>
              <button onClick={() => workspace.onRespondApproval(approval.id, 'acceptForSession')} className="rounded-lg border border-primary/30 px-3 py-1.5 font-semibold text-primary hover:bg-primary/10">Approve for session</button>
              <button onClick={() => workspace.onRespondApproval(approval.id, 'accept')} className="rounded-lg bg-primary px-3 py-1.5 font-semibold text-white hover:bg-primary/90">Approve once</button>
            </div>
          </div>
        ))}

        <AgentComposer
          input={workspace.input}
          activeTurnId={workspace.state.activeTurnId}
          connecting={workspace.connecting}
          canCompose={workspace.canCompose}
          composerPlaceholder={workspace.composerPlaceholder}
          sessionCapabilitySnapshot={workspace.state.session?.capabilitySnapshot}
          onInputChange={workspace.onInputChange}
          onSend={workspace.onSend}
          onCancel={workspace.onCancel}
        />
      </section>

      <AgentActivityPanel
        showActivity={workspace.showActivity}
        activity={workspace.state.activity}
        onClose={workspace.onShowActivityChange.bind(null, false)}
      />
    </div>
  );
  /* eslint-enable react-hooks/refs */
}
