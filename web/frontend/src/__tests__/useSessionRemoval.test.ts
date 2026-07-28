import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import { deleteAgentSession } from '../api/agent';
import useSessionRemoval from '../pages/useSessionRemoval';
import type { AgentSession } from '../types/agent';

vi.mock('../api/agent', () => ({
  deleteAgentSession: vi.fn(),
}));

function makeSession(overrides: Partial<AgentSession> & { id: string }): AgentSession {
  return {
    provider: 'fake',
    providerSessionId: `provider-${overrides.id}`,
    projectId: '/workspace',
    cwd: '/workspace',
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

describe('useSessionRemoval', () => {
  beforeEach(() => {
    vi.mocked(deleteAgentSession).mockReset();
  });

  test('does not open the confirm dialog while a turn is active', () => {
    const { result } = renderHook(() => useSessionRemoval({
      activeTurnId: 'turn-1',
      currentSessionId: undefined,
      removeSession: vi.fn(),
      newSession: vi.fn(),
      setError: vi.fn(),
    }));

    act(() => result.current.requestRemoveSession(makeSession({ id: 's1' })));

    expect(result.current.pendingRemoveSession).toBeNull();
  });

  test('cancelRemoveSession clears the pending session without deleting', () => {
    const { result } = renderHook(() => useSessionRemoval({
      activeTurnId: null,
      currentSessionId: undefined,
      removeSession: vi.fn(),
      newSession: vi.fn(),
      setError: vi.fn(),
    }));

    act(() => result.current.requestRemoveSession(makeSession({ id: 's1' })));
    expect(result.current.pendingRemoveSession?.id).toBe('s1');

    act(() => result.current.cancelRemoveSession());
    expect(result.current.pendingRemoveSession).toBeNull();
    expect(deleteAgentSession).not.toHaveBeenCalled();
  });

  test('confirmRemoveSession deletes, removes from the list, and starts a new session only if it was the active one', async () => {
    vi.mocked(deleteAgentSession).mockResolvedValue(undefined);
    const removeSession = vi.fn();
    const newSession = vi.fn();

    const { result } = renderHook(() => useSessionRemoval({
      activeTurnId: null,
      currentSessionId: 's1',
      removeSession,
      newSession,
      setError: vi.fn(),
    }));

    act(() => result.current.requestRemoveSession(makeSession({ id: 's1' })));
    await act(async () => {
      await result.current.confirmRemoveSession();
    });

    expect(deleteAgentSession).toHaveBeenCalledWith('s1');
    expect(removeSession).toHaveBeenCalledWith('s1');
    expect(newSession).toHaveBeenCalled();
    expect(result.current.pendingRemoveSession).toBeNull();
  });

  test('confirmRemoveSession does not start a new session when removing a non-active conversation', async () => {
    vi.mocked(deleteAgentSession).mockResolvedValue(undefined);
    const removeSession = vi.fn();
    const newSession = vi.fn();

    const { result } = renderHook(() => useSessionRemoval({
      activeTurnId: null,
      currentSessionId: 'other-session',
      removeSession,
      newSession,
      setError: vi.fn(),
    }));

    act(() => result.current.requestRemoveSession(makeSession({ id: 's1' })));
    await act(async () => {
      await result.current.confirmRemoveSession();
    });

    expect(removeSession).toHaveBeenCalledWith('s1');
    expect(newSession).not.toHaveBeenCalled();
  });

  test('surfaces an error and keeps the session state on delete failure', async () => {
    vi.mocked(deleteAgentSession).mockRejectedValue(new Error('boom'));
    const setError = vi.fn();

    const { result } = renderHook(() => useSessionRemoval({
      activeTurnId: null,
      currentSessionId: 's1',
      removeSession: vi.fn(),
      newSession: vi.fn(),
      setError,
    }));

    act(() => result.current.requestRemoveSession(makeSession({ id: 's1' })));
    await act(async () => {
      await result.current.confirmRemoveSession();
    });

    await waitFor(() => expect(setError).toHaveBeenCalledWith('boom'));
  });
});
