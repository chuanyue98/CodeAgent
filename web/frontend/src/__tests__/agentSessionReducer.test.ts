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

  test('keeps OpenCode messages separate when text item ids repeat across turns', () => {
    const firstDelta = agentSessionReducer(initialAgentSessionState, {
      type: 'event',
      event: { ...event(1, 'message.delta', { delta: 'first' }), itemId: 'text-0' },
    });
    const firstCompleted = agentSessionReducer(firstDelta, {
      type: 'event',
      event: { ...event(2, 'message.completed', { text: 'first answer' }), itemId: 'text-0' },
    });
    const secondDelta = agentSessionReducer(firstCompleted, {
      type: 'event',
      event: {
        ...event(3, 'message.delta', { delta: 'second' }),
        turnId: 'turn-2',
        itemId: 'text-0',
      },
    });
    const secondCompleted = agentSessionReducer(secondDelta, {
      type: 'event',
      event: {
        ...event(4, 'message.completed', { text: 'second answer' }),
        turnId: 'turn-2',
        itemId: 'text-0',
      },
    });

    expect(secondCompleted.messages).toHaveLength(2);
    expect(secondCompleted.messages.map(message => message.text)).toEqual([
      'first answer',
      'second answer',
    ]);
    expect(secondCompleted.messages[0].id).not.toBe(secondCompleted.messages[1].id);
  });
});
