import { Loader2, X } from 'lucide-react';
import { Link } from 'react-router';
import AgentActivityPanel from '../components/AgentActivityPanel';
import AgentComposer from '../components/AgentComposer';
import AgentMessage from '../components/AgentMessage';
import AgentSessionBanner from '../components/AgentSessionBanner';
import AgentToolbar from '../components/AgentToolbar';
import AgentWorkspaceSidebar from '../components/AgentWorkspaceSidebar';
import ConfirmDialog from '../components/shared/ConfirmDialog';
import useAgentWorkspace from './useAgentWorkspace';
import { useT } from '../i18n/context';

export default function AgentWorkspace() {
  const t = useT();
  const workspace = useAgentWorkspace();

  /* eslint-disable react-hooks/refs */
  return (
    <div className="flex min-h-full gap-3 lg:h-full">
      <AgentWorkspaceSidebar
        nativeLoadingProviders={workspace.nativeLoadingProviders}
        nativeSessionErrors={workspace.nativeSessionErrors}
        selectedProvider={workspace.selectedProvider}
        sessionSearch={workspace.sessionSearch}
        normalizedSessionSearch={workspace.normalizedSessionSearch}
        filteredGatewaySessions={workspace.filteredGatewaySessions}
        recentSessions={workspace.recentSessions}
        gatewaySessionLimit={workspace.gatewaySessionLimit}
        nativeSessionLimit={workspace.nativeSessionLimit}
        unavailableSessionLimit={workspace.unavailableSessionLimit}
        resumableNativeSessions={workspace.resumableNativeSessions}
        visibleNativeSessions={workspace.visibleNativeSessions}
        unavailableSessionCount={workspace.unavailableSessionCount}
        unavailableWorkspaceGroups={workspace.unavailableWorkspaceGroups}
        visibleUnavailableWorkspaceGroups={workspace.visibleUnavailableWorkspaceGroups}
        hiddenWorkspaceCount={workspace.hiddenWorkspaceCount}
        showHiddenWorkspaces={workspace.showHiddenWorkspaces}
        onHideWorkspace={workspace.onHideWorkspace}
        onUnhideWorkspace={workspace.onUnhideWorkspace}
        onHideAllUnavailable={() => workspace.onHideAllUnavailableWorkspaces(
          workspace.unavailableWorkspaceGroups.map(group => group.path),
        )}
        onToggleShowHiddenWorkspaces={workspace.onToggleShowHiddenWorkspaces}
        onRegisterWorkspace={workspace.onRegisterWorkspace}
        registeringWorkspace={workspace.registeringWorkspace}
        workspaceConversations={workspace.workspaceConversations}
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
      />

      <section className="animate-fade-rise stagger-2 glass-card flex min-w-0 flex-1 flex-col p-4">
        <AgentToolbar
          validProjects={workspace.validProjects}
          providers={workspace.providers}
          selectedProvider={workspace.selectedProvider}
          workspace={workspace.workspace}
          connected={workspace.connected}
          stateSessionId={workspace.state.session?.id ?? null}
          stateActiveTurnId={workspace.state.activeTurnId}
          connectionLabel={workspace.connectionLabel}
          permissionMode={workspace.permissionMode}
          currentGroup={workspace.currentGroup}
          onWorkspaceChange={workspace.onWorkspaceChange}
          onProviderChange={workspace.onProviderChange}
          onShowActivityChange={workspace.onShowActivityChange}
          onPermissionModeChange={workspace.onPermissionModeChange}
        />

        {workspace.validProjects.length === 0 && (
          <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            {t('agentPage.registerFirst')}{' '}
            <Link to="/settings/workspace" className="font-semibold underline">{t('agentPage.openWorkspaceSettings')}</Link>
          </div>
        )}
        {workspace.noGatewayProvider && (
          <div className="mb-3 flex items-start justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            <div>
              <p className="font-semibold">{t('agentPage.noInteractiveEngine')}</p>
              <p className="mt-0.5">{workspace.providers[0]?.unavailableReason || t('agentPage.gatewayCouldNotStart')}</p>
            </div>
          </div>
        )}
        {!workspace.loading && !workspace.gatewayStatus.enabled && (
          <div className="mb-3 flex items-start justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
            <div>
              <p className="font-semibold">{t('agentPage.gatewayDisabled')}</p>
              <p className="mt-0.5">{t('agentPage.enableInConfig')}</p>
            </div>
          </div>
        )}
        {workspace.error && (
          <div className="mb-3 flex items-center justify-between gap-3 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-700">
            <span className="flex items-center gap-2">{workspace.error}</span>
            <span className="flex shrink-0 items-center gap-3">
              {workspace.errorAction === 'register-workspace' ? (
                <Link to="/settings/workspace" className="font-semibold underline">{t('agentPage.openWorkspaceSettings')}</Link>
              ) : null}
              <button
                aria-label={t('agentPage.dismissError')}
                onClick={workspace.onDismissError}
                className="rounded-md p-0.5 text-red-400 hover:bg-red-100 hover:text-red-700"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </span>
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
              provider={workspace.state.provider}
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
            {workspace.loadingOlderMessages && (
              <div className="py-1 text-center text-xs text-slate-400">{t('agentPage.loadingEarlier')}</div>
            )}
            {!workspace.loadingOlderMessages && workspace.hasOlderMessages && (
              <div className="py-1 text-center text-xs text-slate-400">{t('agentPage.scrollUpForEarlier')}</div>
            )}
            {workspace.state.messages.length === 0 && !workspace.state.activeTurnId && (
              <div className="flex h-full min-h-48 flex-col items-center justify-center text-center text-slate-400">
                <p className="animate-fade-rise stagger-1 text-sm font-medium text-slate-600">
                  {!workspace.workspaceIsUsable
                    ? t('agentPage.chooseWorkspace')
                    : !workspace.selectedProvider
                      ? t('agentPage.chooseEngine')
                      : t('agentPage.startNew')}
                </p>
                <p className="animate-fade-rise stagger-2 mt-1 max-w-md text-xs">
                  {!workspace.workspaceIsUsable
                    ? t('agentPage.chooseWorkspaceHint')
                    : !workspace.selectedProvider
                      ? t('agentPage.chooseEngineHint')
                      : t('agentPage.sendToStart', {
                        workspace: workspace.workspace,
                        provider: workspace.selectedCapabilities?.displayName || t('agent.theAgent'),
                      })}
                </p>
                {workspace.canCompose && (
                  <button
                    onClick={workspace.focusComposer}
                    className="animate-fade-rise stagger-3 mt-4 rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-white transition-all duration-300 hover:-translate-y-0.5 hover:bg-primary/90 hover:shadow-[0_12px_20px_-8px_hsl(192_82%_31%/0.4)]"
                  >{t('agentPage.startWith', {
                      provider: workspace.selectedCapabilities?.displayName || workspace.selectedProvider,
                    })}</button>
                )}
              </div>
            )}
            {workspace.state.messages.filter(message => message.role !== 'assistant' || message.text.trim()).map(message => (
              <AgentMessage key={message.id} role={message.role} text={message.text} />
            ))}
            {workspace.state.activeTurnId && !workspace.state.messages.some(message => message.pending) && (
              <div className="flex max-w-[85%] items-center gap-2 rounded-xl border border-slate-100 bg-slate-50 px-4 py-2.5 text-sm text-slate-400">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> {t('agentPage.working')}
              </div>
            )}
          </div>
          {workspace.showScrollToBottom && (
            <button
              onClick={() => workspace.scrollToLatest()}
              className="absolute bottom-3 right-3 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-semibold text-primary shadow-md hover:bg-slate-50"
            >
              {t('agentPage.jumpToLatest')}
            </button>
          )}
        </div>

        {workspace.state.approvals.map(approval => (
          <div key={approval.id} className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-950">
            <p className="font-semibold">{t('agentPage.approvalRequired')}</p>
            {approval.reason && <p className="mt-1 text-amber-800">{approval.reason}</p>}
            {approval.command && <pre className="mt-2 overflow-x-auto rounded-lg bg-slate-900 p-2 text-[11px] text-slate-100">{approval.command}</pre>}
            {approval.cwd && <p className="mt-1 break-all text-[10px] text-amber-700">{t('agentPage.workingDirectory', { path: approval.cwd })}</p>}
            <div className="mt-2 flex justify-end gap-2">
              <button onClick={() => workspace.onRespondApproval(approval.id, 'cancel')} className="rounded-lg border border-amber-300 px-3 py-1.5 font-semibold hover:bg-amber-100">{t('agentPage.cancelTurn')}</button>
              <button onClick={() => workspace.onRespondApproval(approval.id, 'decline')} className="rounded-lg border border-amber-300 px-3 py-1.5 font-semibold hover:bg-amber-100">{t('agentPage.decline')}</button>
              <button onClick={() => workspace.onRespondApproval(approval.id, 'acceptForSession')} className="rounded-lg border border-primary/30 px-3 py-1.5 font-semibold text-primary hover:bg-primary/10">{t('agentPage.approveForSession')}</button>
              <button onClick={() => workspace.onRespondApproval(approval.id, 'accept')} className="rounded-lg bg-primary px-3 py-1.5 font-semibold text-white hover:bg-primary/90">{t('agentPage.approveOnce')}</button>
            </div>
          </div>
        ))}

        <AgentComposer
          input={workspace.input}
          activeTurnId={workspace.state.activeTurnId}
          connecting={workspace.connecting}
          sending={workspace.sending}
          canCompose={workspace.canCompose}
          composerPlaceholder={workspace.composerPlaceholder}
          sessionCapabilitySnapshot={workspace.state.session?.capabilitySnapshot}
          setComposerRef={workspace.setComposerRef}
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

      {workspace.pendingRemoveSession && (
        <ConfirmDialog
          title={t('agentPage.confirmRemoveTitle')}
          description={t('agentPage.confirmRemoveDescription', {
            name: workspace.pendingRemoveSession.title || t('agent.untitled'),
          })}
          confirmLabel={t('common.remove')}
          onConfirm={workspace.onConfirmRemoveSession}
          onCancel={workspace.onCancelRemoveSession}
        />
      )}
    </div>
  );
  /* eslint-enable react-hooks/refs */
}
