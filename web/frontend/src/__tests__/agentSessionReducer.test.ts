import { describe, expect, test } from 'vitest';
import {
  agentSessionReducer,
  initialAgentSessionState,
} from '../state/agentSessionReducer';
import type { AgentEvent } from '../types/agent';

function event(sequence: number, type: string, data: Record<string, unknown> = {}): AgentEvent {
  return {
    type,
    sequence,
    timestamp: '2026-07-14T00:00:00Z',
    sessionId: 'agent-1',
    turnId: 'turn-1',
    itemId: 'item-1',
    data,
  };
}

describe('agentSessionReducer', () => {
  test('merges deltas and ignores replayed duplicate sequences', () => {
    const first = agentSessionReducer(initialAgentSessionState, {
      type: 'event',
      event: event(1, 'message.delta', { delta: 'Hello ' }),
    });
    const second = agentSessionReducer(first, {
      type: 'event',
      event: event(2, 'message.delta', { delta: 'world' }),
    });
    const duplicate = agentSessionReducer(second, {
      type: 'event',
      event: event(2, 'message.delta', { delta: 'world' }),
    });
    expect(duplicate.messages[0].text).toBe('Hello world');
    expect(duplicate.lastSequence).toBe(2);
  });

  test('uses completed text as the authoritative assistant message', () => {
    const partial = agentSessionReducer(initialAgentSessionState, {
      type: 'event',
      event: event(1, 'message.delta', { delta: 'partial' }),
    });
    const completed = agentSessionReducer(partial, {
      type: 'event',
      event: event(2, 'message.completed', { text: 'final answer' }),
    });
    expect(completed.messages[0]).toMatchObject({
      text: 'final answer',
      pending: false,
    });
  });
});
