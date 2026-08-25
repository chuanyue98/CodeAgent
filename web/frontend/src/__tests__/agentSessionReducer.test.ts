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

  test('does not create visible messages for empty provider deltas or completions', () => {
    const emptyDelta = agentSessionReducer(initialAgentSessionState, {
      type: 'event',
      event: event(1, 'message.delta', { delta: '   ' }),
    });
    const emptyCompleted = agentSessionReducer(emptyDelta, {
      type: 'event',
      event: event(2, 'message.completed', { text: '' }),
    });

    expect(emptyCompleted.messages).toEqual([]);
    expect(emptyCompleted.lastSequence).toBe(2);
  });

  test('finishes a visible delta when its completion carries no text', () => {
    const partial = agentSessionReducer(initialAgentSessionState, {
      type: 'event',
      event: event(1, 'message.delta', { delta: 'partial' }),
    });
    const completed = agentSessionReducer(partial, {
      type: 'event',
      event: event(2, 'message.completed', { text: '' }),
    });

    expect(completed.messages[0]).toMatchObject({ text: 'partial', pending: false });
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
  test('tracks provider connectivity across a drop and recovery', () => {
    const dropped = agentSessionReducer(initialAgentSessionState, {
      type: 'event',
      event: event(1, 'provider.disconnected', {
        provider: 'claude',
        connected: false,
        reason: 'adapter process died',
        attempt: 2,
      }),
    });
    expect(dropped.provider).toEqual({
      connected: false,
      reason: 'adapter process died',
      attempt: 2,
    });

    const recovered = agentSessionReducer(dropped, {
      type: 'event',
      event: event(2, 'provider.connected', { provider: 'claude', connected: true, attempt: 0 }),
    });
    expect(recovered.provider).toEqual({ connected: true, attempt: 0 });
  });

  test('keeps provider_disconnected errors out of the transcript', () => {
    // The Gateway emits one of these per retry cycle. Rendering each as an
    // error bubble would bury the conversation during a long outage — the
    // banner reports the outage instead.
    const state = agentSessionReducer(initialAgentSessionState, {
      type: 'event',
      event: event(1, 'error', {
        code: 'provider_disconnected',
        message: 'adapter process died',
      }),
    });
    expect(state.messages).toHaveLength(0);
  });

  test('still shows genuine provider errors in the transcript', () => {
    const state = agentSessionReducer(initialAgentSessionState, {
      type: 'event',
      event: event(1, 'error', { code: 'provider_error', message: 'model refused' }),
    });
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0].role).toBe('error');
    expect(state.messages[0].text).toBe('model refused');
  });
});

describe('agentSessionReducer: events that used to be dropped', () => {
  // The gateway has always pushed these three. The reducer had no branch for
  // any of them, so file changes, real cost and live command output reached
  // the browser and were thrown away.

  function apply(events: AgentEvent[]) {
    let state = initialAgentSessionState;
    for (const next of events) {
      state = agentSessionReducer(state, { type: 'event', event: next });
    }
    return state;
  }

  test('usage.updated is read whichever spelling the engine uses', () => {
    const snake = apply([
      event(1, 'usage.updated', {
        usage: {
          input_tokens: 100,
          output_tokens: 20,
          cache_read_input_tokens: 5,
          cache_creation_input_tokens: 7,
        },
      }),
    ]);
    expect(snake.usage).toMatchObject({
      inputTokens: 100,
      outputTokens: 20,
      cacheReadTokens: 5,
      cacheWriteTokens: 7,
    });

    const camel = apply([
      event(1, 'usage.updated', {
        usage: { inputTokens: 3, outputTokens: 4 },
      }),
    ]);
    expect(camel.usage).toMatchObject({ inputTokens: 3, outputTokens: 4 });
  });

  test('cost accumulates while tokens hold the latest snapshot', () => {
    const state = apply([
      event(1, 'usage.updated', { usage: { input_tokens: 10 }, cost: 0.25 }),
      event(2, 'usage.updated', { usage: { input_tokens: 40 }, cost: 0.5 }),
    ]);

    // Per-turn costs add up to a session cost; token counts do not, because
    // some engines report a running total for the whole thread.
    expect(state.usage?.costUsd).toBeCloseTo(0.75);
    expect(state.usage?.inputTokens).toBe(40);
  });

  test('a usage payload without a cost leaves the running cost alone', () => {
    const state = apply([
      event(1, 'usage.updated', { usage: { input_tokens: 10 }, cost: 0.25 }),
      event(2, 'usage.updated', { usage: { input_tokens: 40 } }),
    ]);

    expect(state.usage?.costUsd).toBeCloseTo(0.25);
  });

  test('command.output streams onto the tool row that started it', () => {
    const state = apply([
      event(1, 'tool.started', { tool: { title: 'pytest', kind: 'command' } }),
      event(2, 'command.output', { commandId: 'item-1', delta: '12 passed' }),
      event(3, 'command.output', { commandId: 'item-1', delta: ' in 3.4s' }),
    ]);

    const tool = state.messages.find(message => message.role === 'tool');
    expect(tool?.tool?.output).toBe('12 passed in 3.4s');
  });

  test('command output is trimmed rather than grown without bound', () => {
    const state = apply([
      event(1, 'tool.started', { tool: { title: 'build' } }),
      event(2, 'command.output', { commandId: 'item-1', delta: 'x'.repeat(9000) }),
    ]);

    const tool = state.messages.find(message => message.role === 'tool');
    expect(tool?.tool?.output?.length).toBe(4000);
  });

  test('output for a tool that was never announced is ignored', () => {
    const state = apply([
      event(1, 'command.output', { commandId: 'nope', delta: 'orphan' }),
    ]);

    expect(state.messages).toHaveLength(0);
  });

  test('file.diff names the changed files on the tool row', () => {
    const state = apply([
      event(1, 'tool.started', { tool: { title: 'edit', kind: 'fileChange' } }),
      event(2, 'file.diff', {
        diff: [{ path: 'core/a.py' }, { path: 'core/b.py' }],
      }),
    ]);

    const tool = state.messages.find(message => message.role === 'tool');
    expect(tool?.tool?.files).toEqual(['core/a.py', 'core/b.py']);
  });

  test('file.diff digs paths out of a nested payload and de-duplicates', () => {
    const state = apply([
      event(1, 'tool.started', { tool: { title: 'edit' } }),
      event(2, 'file.diff', {
        diff: { changes: [{ file: 'x.ts', hunks: [{ path: 'x.ts' }] }] },
      }),
    ]);

    const tool = state.messages.find(message => message.role === 'tool');
    expect(tool?.tool?.files).toEqual(['x.ts']);
  });

  test('replayed history keeps the usage totals', () => {
    const state = agentSessionReducer(initialAgentSessionState, {
      type: 'history.replace',
      events: [
        event(1, 'message.completed', { text: 'done' }),
        event(2, 'usage.updated', { usage: { input_tokens: 11 }, cost: 1.5 }),
      ],
    });

    // A reconnect replays history; dropping usage here blanked a cost that
    // had already been reported.
    expect(state.usage?.costUsd).toBeCloseTo(1.5);
    expect(state.usage?.inputTokens).toBe(11);
  });
});
