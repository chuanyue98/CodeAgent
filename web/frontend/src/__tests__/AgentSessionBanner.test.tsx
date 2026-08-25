import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';
import AgentSessionBanner from '../components/AgentSessionBanner';
import type { SessionUsage } from '../state/agentSessionReducer';
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

function renderBanner(props: { snapshot?: ResourceSnapshot; usage?: SessionUsage }) {
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
      usage={props.usage ?? null}
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


describe('AgentSessionBanner usage', () => {
  // usage.updated has always been streamed; the reducer had no branch for it,
  // so a session's real cost never reached the page.

  test('shows nothing until the provider reports usage', () => {
    renderBanner({});

    expect(screen.queryByText(/in \//)).not.toBeInTheDocument();
  });

  test('reports cost and tokens once they arrive', () => {
    renderBanner({
      usage: {
        inputTokens: 12_500,
        outputTokens: 800,
        cacheReadTokens: 0,
        cacheWriteTokens: 0,
        costUsd: 0.4237,
      },
    });

    expect(screen.getByText('$0.424')).toBeInTheDocument();
    expect(screen.getByText('12.5K in / 800 out')).toBeInTheDocument();
  });

  test('a sub-cent cost keeps enough digits to be readable', () => {
    renderBanner({
      usage: {
        inputTokens: 1,
        outputTokens: 1,
        cacheReadTokens: 0,
        cacheWriteTokens: 0,
        costUsd: 0.0004,
      },
    });

    // Two decimals would render this as "$0.00".
    expect(screen.getByText('$0.0004')).toBeInTheDocument();
  });

  test('cache totals only appear when there are any', () => {
    renderBanner({
      usage: {
        inputTokens: 10,
        outputTokens: 5,
        cacheReadTokens: 2_000,
        cacheWriteTokens: 300,
        costUsd: null,
      },
    });

    expect(screen.getByText('cache 2.0K read / 300 written')).toBeInTheDocument();
  });
});
