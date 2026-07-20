import { renderHook } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import useAgentWorkspaceSessions from '../pages/useAgentWorkspaceSessions';
import type { AgentSession } from '../types/agent';

function makeSession(overrides: Partial<AgentSession> & { id: string; projectId: string }): AgentSession {
  return {
    provider: 'fake',
    providerSessionId: `provider-${overrides.id}`,
    cwd: overrides.projectId,
    title: null,
    model: null,
    permissionMode: 'workspace-write',
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    status: 'ready',
    lastSequence: 0,
    capabilitySnapshot: {
      providerId: 'fake',
      displayName: 'Fake',
      available: true,
      unavailableReason: null,
      supportsResume: true,
      supportsSteer: true,
      supportsCancel: true,
      supportsApprovals: true,
      supportsFileDiff: true,
      supportsToolEvents: true,
      supportsAttachments: false,
      supportsModelSwitch: false,
    },
    resourceSnapshot: {},
    ...overrides,
  };
}

describe('useAgentWorkspaceSessions', () => {
  test('truncates recentSessions to the page limit when not searching', () => {
    const projects = [{ path: '/workspace', group: 'common' }];
    const sessions = Array.from({ length: 25 }, (_, i) =>
      makeSession({ id: `s${i}`, projectId: '/workspace', updatedAt: `2026-01-01T00:00:${String(i).padStart(2, '0')}Z` }),
    );

    const { result } = renderHook(() =>
      useAgentWorkspaceSessions({
        projects,
        sessions,
        nativeSessionsByProvider: {},
        sessionSearch: '',
        gatewaySessionLimit: 20,
        nativeSessionLimit: 20,
        unavailableSessionLimit: 20,
        workspace: '/workspace',
      }),
    );

    expect(result.current.recentSessions).toHaveLength(20);
  });

  test('a matching session past the global page limit still appears in its workspace group while searching', () => {
    // Simulates the reported bug: 25 sessions across two workspaces ALL
    // match "needle" (so the search filter alone can't be why one drops
    // out), listed with workspace A's 24 sessions first and workspace B's
    // single session last -- past the default page size of 20. Slicing
    // filteredGatewaySessions to that limit *before* grouping by workspace
    // would drop workspace B's group entirely even though it has a real
    // match; the fix must show every match while searching instead.
    const projects = [
      { path: '/workspace-a', group: 'common' },
      { path: '/workspace-b', group: 'common' },
    ];
    const workspaceASessions = Array.from({ length: 24 }, (_, i) =>
      makeSession({
        id: `a${i}`,
        projectId: '/workspace-a',
        title: 'needle in haystack A',
        updatedAt: `2026-01-02T00:00:${String(i).padStart(2, '0')}Z`,
      }),
    );
    const workspaceBSession = makeSession({
      id: 'b0',
      projectId: '/workspace-b',
      title: 'needle in haystack B',
      updatedAt: '2026-01-01T00:00:00Z',
    });
    const sessions = [...workspaceASessions, workspaceBSession];

    const { result } = renderHook(() =>
      useAgentWorkspaceSessions({
        projects,
        sessions,
        nativeSessionsByProvider: {},
        sessionSearch: 'needle',
        gatewaySessionLimit: 20,
        nativeSessionLimit: 20,
        unavailableSessionLimit: 20,
        workspace: '/workspace-a',
      }),
    );

    // All 25 sessions match the search term -- the bug isn't in filtering,
    // it's in slicing the already-filtered list before grouping.
    expect(result.current.filteredGatewaySessions).toHaveLength(25);

    const groupB = result.current.workspaceConversations.find(
      group => group.path === '/workspace-b',
    );
    expect(groupB).toBeDefined();
    expect(groupB?.conversations).toHaveLength(1);
    expect(groupB?.conversations[0].key).toBe(workspaceBSession.id);
  });
});
