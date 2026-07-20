import { useMemo } from 'react';
import type { AgentSession, NativeAgentSession } from '../types/agent';
import type { ConversationListItem } from '../utils/agentWorkspaceHelpers';
import {
  deduplicateNativeSessions,
  workspaceLabel,
} from '../utils/agentWorkspaceHelpers';

type Project = { path: string; group: string; available?: boolean };

export default function useAgentWorkspaceSessions({
  projects,
  sessions,
  nativeSessionsByProvider,
  sessionSearch,
  gatewaySessionLimit,
  nativeSessionLimit,
  unavailableSessionLimit,
  workspace,
}: {
  projects: Project[];
  sessions: AgentSession[];
  nativeSessionsByProvider: Record<string, NativeAgentSession[]>;
  sessionSearch: string;
  gatewaySessionLimit: number;
  nativeSessionLimit: number;
  unavailableSessionLimit: number;
  workspace: string;
}) {
  const validProjects = useMemo(
    () => projects.filter(project => project.path.trim() && project.available !== false),
    [projects],
  );
  const validProjectPaths = useMemo(
    () => new Set(validProjects.map(project => project.path)),
    [validProjects],
  );
  const allNativeSessions = useMemo(
    () => deduplicateNativeSessions(Object.values(nativeSessionsByProvider).flat()),
    [nativeSessionsByProvider],
  );
  const normalizedSessionSearch = sessionSearch.trim().toLocaleLowerCase();
  const filteredGatewaySessions = useMemo(
    () => sessions.filter(session => !normalizedSessionSearch || [
      session.title,
      session.provider,
      session.cwd,
      session.model,
      session.status,
    ].some(value => value?.toLocaleLowerCase().includes(normalizedSessionSearch))),
    [normalizedSessionSearch, sessions],
  );
  const recentSessions = useMemo(
    // The page-size limit is for the default (unfiltered) "recent N, load
    // more" view. Applying it before workspaceConversations groups by
    // workspace would silently drop a workspace whose search matches all
    // happen to sort past the limit in the global list -- so while
    // searching, show every match instead of a truncated window of them.
    () => normalizedSessionSearch
      ? filteredGatewaySessions
      : filteredGatewaySessions.slice(0, gatewaySessionLimit),
    [filteredGatewaySessions, gatewaySessionLimit, normalizedSessionSearch],
  );
  const mappedProviderSessions = useMemo(
    () => new Set(sessions.map(session => `${session.provider}:${session.providerSessionId}`)),
    [sessions],
  );
  const filteredNativeSessions = useMemo(
    () => allNativeSessions
      .filter(session => !mappedProviderSessions.has(`${session.engine}:${session.session_id}`))
      .filter(session => !normalizedSessionSearch || [
        session.title,
        session.engine,
        session.project_path,
        session.model,
      ].some(value => value?.toLocaleLowerCase().includes(normalizedSessionSearch))),
    [allNativeSessions, mappedProviderSessions, normalizedSessionSearch],
  );
  const resumableNativeSessions = useMemo(
    () => filteredNativeSessions.filter(session => validProjectPaths.has(session.project_path)),
    [filteredNativeSessions, validProjectPaths],
  );
  const unavailableNativeSessions = useMemo(
    () => filteredNativeSessions.filter(session => !validProjectPaths.has(session.project_path)),
    [filteredNativeSessions, validProjectPaths],
  );
  const visibleNativeSessions = useMemo(
    () => normalizedSessionSearch
      ? resumableNativeSessions
      : resumableNativeSessions.slice(0, nativeSessionLimit),
    [resumableNativeSessions, nativeSessionLimit, normalizedSessionSearch],
  );
  const visibleUnavailableSessions = useMemo(
    () => normalizedSessionSearch
      ? unavailableNativeSessions
      : unavailableNativeSessions.slice(0, unavailableSessionLimit),
    [unavailableNativeSessions, unavailableSessionLimit, normalizedSessionSearch],
  );
  const workspaceConversations = useMemo(() => {
    const byWorkspace = new Map<string, ConversationListItem[]>(
      validProjects.map(project => [project.path, []]),
    );
    recentSessions.forEach(session => {
      const items = byWorkspace.get(session.projectId);
      if (!items) return;
      items.push({
        source: 'gateway', key: session.id, projectPath: session.projectId,
        updatedAt: session.updatedAt, session,
      });
    });
    visibleNativeSessions.forEach(session => {
      const items = byWorkspace.get(session.project_path);
      if (!items) return;
      items.push({
        source: 'native', key: `${session.engine}:${session.session_id}`,
        projectPath: session.project_path,
        updatedAt: session.ended_at || session.started_at, session,
      });
    });
    return validProjects
      .map(project => ({
        path: project.path,
        label: workspaceLabel(project.path),
        conversations: (byWorkspace.get(project.path) || []).sort(
          (left, right) => right.updatedAt.localeCompare(left.updatedAt),
        ),
      }))
      .filter(group => group.conversations.length > 0 || !normalizedSessionSearch)
      .sort((left, right) => {
        if (left.path === workspace) return -1;
        if (right.path === workspace) return 1;
        return left.label.localeCompare(right.label);
      });
  }, [normalizedSessionSearch, recentSessions, validProjects, visibleNativeSessions, workspace]);

  return {
    validProjects,
    validProjectPaths,
    allNativeSessions,
    normalizedSessionSearch,
    filteredGatewaySessions,
    recentSessions,
    mappedProviderSessions,
    filteredNativeSessions,
    resumableNativeSessions,
    unavailableNativeSessions,
    visibleNativeSessions,
    visibleUnavailableSessions,
    workspaceConversations,
  };
}
