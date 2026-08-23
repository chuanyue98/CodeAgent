import { useCallback, useMemo, useState } from 'react';
import type { AgentSession, NativeAgentSession } from '../types/agent';
import type { ConversationListItem } from '../utils/agentWorkspaceHelpers';
import {
  deduplicateNativeSessions,
  workspaceLabel,
} from '../utils/agentWorkspaceHelpers';

type Project = { path: string; group: string; available?: boolean };

export interface UnavailableWorkspaceGroup {
  path: string;
  sessions: NativeAgentSession[];
  latestSession: NativeAgentSession;
  isHidden: boolean;
}

// Dismissing an unavailable workspace is a personal decluttering choice, not
// server state -- it's stored client-side so "129 unavailable workspaces"
// can shrink to just the ones a user still cares about, without needing a
// backend concept of "archived" history.
const HIDDEN_WORKSPACES_KEY = 'codeagent.hiddenUnavailableWorkspaces';

function readHiddenWorkspaces(): Set<string> {
  try {
    const raw = window.localStorage.getItem(HIDDEN_WORKSPACES_KEY);
    return new Set(raw ? (JSON.parse(raw) as string[]) : []);
  } catch {
    return new Set();
  }
}

function writeHiddenWorkspaces(paths: Set<string>): void {
  try {
    window.localStorage.setItem(HIDDEN_WORKSPACES_KEY, JSON.stringify(Array.from(paths)));
  } catch {
    // Private-mode / blocked storage: hiding still works for this session.
  }
}

function latestTimestamp(session: NativeAgentSession): string {
  return session.ended_at || session.started_at || '';
}

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

  const [hiddenWorkspaces, setHiddenWorkspaces] = useState<Set<string>>(readHiddenWorkspaces);
  const [showHiddenWorkspaces, setShowHiddenWorkspaces] = useState(false);

  const hideWorkspace = useCallback((path: string) => {
    setHiddenWorkspaces(prev => {
      const next = new Set(prev);
      next.add(path);
      writeHiddenWorkspaces(next);
      return next;
    });
  }, []);

  const unhideWorkspace = useCallback((path: string) => {
    setHiddenWorkspaces(prev => {
      const next = new Set(prev);
      next.delete(path);
      writeHiddenWorkspaces(next);
      return next;
    });
  }, []);

  // One click for "I don't care about any of these right now" -- with dozens
  // of unavailable groups, hiding them one by one is its own chore.
  const hideAllUnavailableWorkspaces = useCallback((paths: string[]) => {
    setHiddenWorkspaces(prev => {
      const next = new Set(prev);
      for (const path of paths) next.add(path);
      writeHiddenWorkspaces(next);
      return next;
    });
  }, []);

  const toggleShowHiddenWorkspaces = useCallback(() => {
    setShowHiddenWorkspaces(prev => !prev);
  }, []);

  // 129 individual session rows is noise -- what a user can actually act on
  // is the workspace they belong to (register it, or stop seeing it), so
  // group by project_path before deciding what to paginate/hide.
  const allUnavailableWorkspaceGroups = useMemo<UnavailableWorkspaceGroup[]>(() => {
    const byPath = new Map<string, NativeAgentSession[]>();
    for (const session of unavailableNativeSessions) {
      const list = byPath.get(session.project_path);
      if (list) list.push(session);
      else byPath.set(session.project_path, [session]);
    }
    const groups = Array.from(byPath.entries()).map(([path, groupSessions]) => {
      const sorted = [...groupSessions].sort(
        (a, b) => latestTimestamp(b).localeCompare(latestTimestamp(a)),
      );
      return { path, sessions: sorted, latestSession: sorted[0], isHidden: hiddenWorkspaces.has(path) };
    });
    groups.sort(
      (a, b) => latestTimestamp(b.latestSession).localeCompare(latestTimestamp(a.latestSession)),
    );
    return groups;
  }, [unavailableNativeSessions, hiddenWorkspaces]);

  const hiddenWorkspaceCount = useMemo(
    () => allUnavailableWorkspaceGroups.filter(group => hiddenWorkspaces.has(group.path)).length,
    [allUnavailableWorkspaceGroups, hiddenWorkspaces],
  );

  const unavailableWorkspaceGroups = useMemo(
    () => showHiddenWorkspaces
      ? allUnavailableWorkspaceGroups
      : allUnavailableWorkspaceGroups.filter(group => !hiddenWorkspaces.has(group.path)),
    [allUnavailableWorkspaceGroups, hiddenWorkspaces, showHiddenWorkspaces],
  );

  const visibleUnavailableWorkspaceGroups = useMemo(
    () => normalizedSessionSearch
      ? unavailableWorkspaceGroups
      : unavailableWorkspaceGroups.slice(0, unavailableSessionLimit),
    [unavailableWorkspaceGroups, unavailableSessionLimit, normalizedSessionSearch],
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
    unavailableSessionCount: unavailableNativeSessions.length,
    visibleNativeSessions,
    unavailableWorkspaceGroups,
    visibleUnavailableWorkspaceGroups,
    hiddenWorkspaceCount,
    showHiddenWorkspaces,
    onHideWorkspace: hideWorkspace,
    onUnhideWorkspace: unhideWorkspace,
    onHideAllUnavailableWorkspaces: hideAllUnavailableWorkspaces,
    onToggleShowHiddenWorkspaces: toggleShowHiddenWorkspaces,
    workspaceConversations,
  };
}
