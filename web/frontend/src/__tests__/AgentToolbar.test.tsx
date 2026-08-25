import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';
import AgentToolbar from '../components/AgentToolbar';
import type { ProviderCapabilities } from '../types/agent';

const PROJECTS = [
  { path: '/workspace/project-a', group: 'codeagent', available: true },
  { path: '/workspace/project-b', group: 'codeagent', available: true },
];

const PROVIDERS: ProviderCapabilities[] = [
  { providerId: 'claude', displayName: 'Claude', available: true } as ProviderCapabilities,
  { providerId: 'codex', displayName: 'Codex', available: true } as ProviderCapabilities,
];

function renderToolbar(overrides: Record<string, unknown> = {}) {
  const handlers = {
    onWorkspaceChange: vi.fn(),
    onProviderChange: vi.fn(),
    onShowActivityChange: vi.fn(),
    onPermissionModeChange: vi.fn(),
    onNewSession: vi.fn(),
  };
  render(
    <AgentToolbar
      validProjects={PROJECTS}
      providers={PROVIDERS}
      selectedProvider="claude"
      workspace="/workspace/project-a"
      connected
      stateSessionId={null}
      stateActiveTurnId={null}
      connectionLabel="Connected"
      permissionMode="workspace-write"
      currentGroup="codeagent"
      {...handlers}
      {...overrides}
    />,
  );
  return handlers;
}

describe('AgentToolbar session-bound controls', () => {
  test('a turn in flight locks the controls', () => {
    renderToolbar({ stateSessionId: 'session-1', stateActiveTurnId: 'turn-1' });

    expect(screen.getByLabelText('Workspace')).toBeDisabled();
    expect(screen.getByLabelText('Engine')).toBeDisabled();
    expect(screen.getByLabelText('Permission mode')).toBeDisabled();
  });

  test('an idle session leaves them usable', () => {
    renderToolbar({ stateSessionId: 'session-1', stateActiveTurnId: null });

    expect(screen.getByLabelText('Workspace')).toBeEnabled();
    expect(screen.getByLabelText('Engine')).toBeEnabled();
    expect(screen.getByLabelText('Permission mode')).toBeEnabled();
  });

  test('changing a setting on an idle session starts a new one', () => {
    const handlers = renderToolbar({ stateSessionId: 'session-1', stateActiveTurnId: null });

    fireEvent.change(screen.getByLabelText('Workspace'), {
      target: { value: '/workspace/project-b' },
    });

    // The value only takes effect at session creation, so applying it means a
    // new session rather than silently doing nothing to the current one.
    expect(handlers.onNewSession).toHaveBeenCalledTimes(1);
    expect(handlers.onWorkspaceChange).toHaveBeenCalledWith('/workspace/project-b');
  });

  test('changing a setting with no session open does not reset anything', () => {
    const handlers = renderToolbar({ stateSessionId: null, stateActiveTurnId: null });

    fireEvent.change(screen.getByLabelText('Engine'), { target: { value: 'codex' } });

    expect(handlers.onNewSession).not.toHaveBeenCalled();
    expect(handlers.onProviderChange).toHaveBeenCalledWith('codex');
  });
});
