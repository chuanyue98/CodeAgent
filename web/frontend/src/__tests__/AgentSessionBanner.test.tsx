import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';
import AgentSessionBanner from '../components/AgentSessionBanner';
import type { AgentSession, ResourceSnapshot } from '../types/agent';

vi.mock('../api/agent', () => ({
  reconnectAgentProvider: vi.fn(),
}));

const capabilities = {
  providerId: 'codex',
  displayName: 'Codex',
  available: true,
  unavailableReason: null,
  supportsResume: true,
  supportsSteer: true,
  supportsCancel: true,
  supportsApprovals: true,
  supportsFileDiff: false,
  supportsToolEvents: true,
  supportsAttachments: false,
  supportsModelSwitch: true,
};

function makeSession(overrides: Partial<AgentSession> = {}): AgentSession {
  return {
    id: 'agent_1',
    provider: 'codex',
    providerSessionId: 'thread-1',
    projectId: 'E:/demo/project',
    cwd: 'E:/demo/project',
    title: 'My conversation',
    model: null,
    permissionMode: 'workspace-write',
    createdAt: '2026-08-21T00:00:00Z',
    updatedAt: '2026-08-21T00:00:00Z',
    status: 'ready',
    lastSequence: 0,
    capabilitySnapshot: capabilities,
    resourceSnapshot: {},
    ...overrides,
  };
}

function renderBanner(props: { snapshot?: ResourceSnapshot }) {
  const snapshot = props.snapshot;
  return render(
    <AgentSessionBanner
      session={makeSession()}
      connected
      connecting={false}
      stateActiveTurnId={null}
      provider={null}
      sessionResourceSnapshot={snapshot}
      sessionResourceGroup={snapshot?.group || 'Unknown'}
      resourceCount={(snapshot?.skills?.length ?? 0)
        + (snapshot?.prompts?.length ?? 0)
        + (snapshot?.hooks?.length ?? 0)
        + (snapshot?.plugins?.length ?? 0)}
      onConnect={() => {}}
      onRemoveSession={() => {}}
    />,
  );
}

describe('AgentSessionBanner resource honesty', () => {
  test('flags kinds without a receipt as not injected', () => {
    renderBanner({
      snapshot: {
        group: 'web',
        skills: ['base/review'],
        prompts: ['base'],
        digest: 'abc123',
        appliedKinds: ['prompts'],
      },
    });

    // Prompts carry a receipt; skills do not -- only skills get flagged.
    expect(screen.getByText('not applied')).toBeInTheDocument();
    fireEvent.click(screen.getByText(/Configured resources/));
    expect(screen.getByText('not injected')).toBeInTheDocument();
    expect(screen.getByText(/Amber kinds are configured/)).toBeInTheDocument();
  });

  test('shows everything applied when every configured kind has a receipt', () => {
    renderBanner({
      snapshot: {
        group: 'web',
        prompts: ['base'],
        digest: 'abc123',
        appliedKinds: ['prompts'],
      },
    });

    expect(screen.getByText('applied')).toBeInTheDocument();
    expect(screen.queryByText('not applied')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText(/Configured resources/));
    expect(screen.queryByText('not injected')).not.toBeInTheDocument();
  });

  test('flags all configured kinds when nothing carries a receipt', () => {
    renderBanner({
      snapshot: { group: 'web', skills: ['base/review'], prompts: ['base'] },
    });

    expect(screen.getByText('not applied')).toBeInTheDocument();
    fireEvent.click(screen.getByText(/Configured resources/));
    expect(screen.getAllByText('not injected')).toHaveLength(2);
  });

  test('stays quiet when nothing is configured', () => {
    renderBanner({ snapshot: { group: 'web' } });

    expect(screen.queryByText('not applied')).not.toBeInTheDocument();
    expect(screen.queryByText('applied')).not.toBeInTheDocument();
  });
});
