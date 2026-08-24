import type { AgentEvent, AgentSession, ApprovalRequest } from '../types/agent';

export interface ToolCallMeta {
  label: string;
  kind: string | null;
  status: 'running' | 'completed' | 'failed';
}

export interface AgentMessage {
  id: string;
  role: 'user' | 'assistant' | 'error' | 'tool';
  text: string;
  turnId?: string | null;
  pending?: boolean;
  /** role === 'tool' 时携带的工具调用信息 */
  tool?: ToolCallMeta;
}

/** Live connectivity of the provider backing this session. */
export interface ProviderConnectivity {
  connected: boolean;
  /** Why it dropped, when known. Absent once reconnected. */
  reason?: string;
  /** Which reconnect attempt the Gateway is on. 0 before the first retry. */
  attempt: number;
}

export interface AgentSessionState {
  session: AgentSession | null;
  messages: AgentMessage[];
  activity: AgentEvent[];
  approvals: ApprovalRequest[];
  activeTurnId: string | null;
  lastSequence: number;
  provider: ProviderConnectivity | null;
}

export const initialAgentSessionState: AgentSessionState = {
  session: null,
  messages: [],
  activity: [],
  approvals: [],
  activeTurnId: null,
  lastSequence: 0,
  provider: null,
};

export type AgentSessionAction =
  | { type: 'reset'; session?: AgentSession | null }
  | { type: 'user.message'; id: string; text: string }
  | { type: 'approval.resolved'; approvalId: string }
  | { type: 'history.replace'; events: AgentEvent[] }
  | { type: 'history.prepend'; events: AgentEvent[] }
  | { type: 'event'; event: AgentEvent };

function dataString(data: Record<string, unknown>, key: string): string {
  return typeof data[key] === 'string' ? data[key] as string : '';
}

function hasVisibleText(text: string): boolean {
  return text.trim().length > 0;
}

function eventMessageId(event: AgentEvent, role: 'user' | 'assistant'): string {
  const turnScope = event.turnId || `sequence-${event.sequence}`;
  const itemScope = event.itemId || role;
  return `${turnScope}:${itemScope}`;
}

/** 各引擎工具事件的 payload 形状不同，这里归一化出展示所需字段。 */
function toolMeta(data: Record<string, unknown>, completed: boolean): ToolCallMeta {
  const tool = (typeof data.tool === 'object' && data.tool !== null ? data.tool : {}) as Record<string, unknown>;
  const label =
    (typeof tool.title === 'string' && tool.title) ||
    (typeof tool.name === 'string' && tool.name) ||
    (typeof tool.command === 'string' && tool.command) ||
    (typeof tool.kind === 'string' && tool.kind) ||
    (typeof tool.type === 'string' && tool.type) ||
    'tool';
  const status = completed
    ? tool.status === 'failed' ? 'failed' : 'completed'
    : 'running';
  return {
    label,
    kind: typeof tool.kind === 'string' ? tool.kind : null,
    status,
  };
}

function replayMessages(events: AgentEvent[]): AgentMessage[] {
  let replay = initialAgentSessionState;
  for (const event of events) {
    replay = agentSessionReducer(replay, { type: 'event', event });
  }
  return replay.messages;
}

export function agentSessionReducer(
  state: AgentSessionState,
  action: AgentSessionAction,
): AgentSessionState {
  if (action.type === 'reset') {
    return { ...initialAgentSessionState, session: action.session ?? null };
  }
  if (action.type === 'user.message') {
    return {
      ...state,
      messages: [...state.messages, { id: action.id, role: 'user', text: action.text }],
    };
  }
  if (action.type === 'approval.resolved') {
    return {
      ...state,
      approvals: state.approvals.filter(approval => approval.id !== action.approvalId),
    };
  }
  if (action.type === 'history.replace') {
    const messages = replayMessages(action.events);
    return {
      ...state,
      messages,
      lastSequence: action.events.at(-1)?.sequence ?? 0,
    };
  }
  if (action.type === 'history.prepend') {
    const page = replayMessages(action.events);
    const existingIds = new Set(state.messages.map(message => message.id));
    return {
      ...state,
      messages: [...page.filter(message => !existingIds.has(message.id)), ...state.messages],
    };
  }

  const event = action.event;
  if (event.sequence <= state.lastSequence) return state;
  const activity = [...state.activity, event].slice(-1000);
  const next: AgentSessionState = {
    ...state,
    activity,
    lastSequence: event.sequence,
  };

  if (event.type === 'session.ready') {
    const session = event.data.session;
    if (session && typeof session === 'object') next.session = session as AgentSession;
  } else if (event.type === 'message.user') {
    next.messages = [
      ...state.messages,
      {
        id: eventMessageId(event, 'user'),
        role: 'user',
        text: dataString(event.data, 'text'),
        turnId: event.turnId,
      },
    ];
  } else if (event.type === 'turn.started') {
    next.activeTurnId = event.turnId;
  } else if (event.type === 'message.delta') {
    const id = eventMessageId(event, 'assistant');
    const delta = dataString(event.data, 'delta');
    // Gateways emit empty deltas for tool, heartbeat, and provider-state
    // events. They belong in activity, not as a visible assistant bubble.
    if (!hasVisibleText(delta)) return next;
    const existing = state.messages.find(message => message.id === id);
    next.messages = existing
      ? state.messages.map(message => message.id === id
        ? { ...message, text: message.text + delta, pending: true }
        : message)
      : [...state.messages, { id, role: 'assistant', text: delta, turnId: event.turnId, pending: true }];
  } else if (event.type === 'message.completed') {
    const id = eventMessageId(event, 'assistant');
    const text = dataString(event.data, 'text');
    const existing = state.messages.find(message => message.id === id);
    if (!hasVisibleText(text) && !existing) return next;
    next.messages = existing
      ? state.messages.map(message => message.id === id
        ? { ...message, text: hasVisibleText(text) ? text : message.text, pending: false }
        : message)
      : [...state.messages, { id, role: 'assistant', text, turnId: event.turnId }];
  } else if (event.type === 'tool.started' || event.type === 'tool.completed') {
    const completed = event.type === 'tool.completed';
    // 以 itemId（toolCallId）为主键：同一次调用的 started/completed 两条事件
    // 更新同一条消息，历史回放时也不会重复。
    const id = `tool:${event.turnId || 'turn'}:${event.itemId ?? event.sequence}`;
    const meta = toolMeta(event.data, completed);
    const existing = state.messages.find(message => message.id === id);
    // completed 事件的 payload 常缺少 title/name，合并时保留已有的好标签。
    next.messages = existing
      ? state.messages.map(message => message.id === id
        ? {
            ...message,
            tool: {
              ...meta,
              label: meta.label !== 'tool' || !message.tool ? meta.label : message.tool.label,
              kind: meta.kind ?? message.tool?.kind ?? null,
            },
          }
        : message)
      : [...state.messages, { id, role: 'tool' as const, text: '', turnId: event.turnId, tool: meta }];
  } else if (event.type === 'approval.request') {
    const approval = event.data.approval;
    if (approval && typeof approval === 'object') {
      next.approvals = [...state.approvals, approval as ApprovalRequest];
    }
  } else if (event.type === 'turn.completed') {
    next.activeTurnId = null;
  } else if (event.type === 'provider.disconnected') {
    next.provider = {
      connected: false,
      reason: dataString(event.data, 'reason') || undefined,
      attempt: typeof event.data.attempt === 'number' ? event.data.attempt : 0,
    };
    // The provider is gone, so any in-flight turn cannot complete.
    // Clear activeTurnId so the composer unlocks and the user can send
    // a new message after the provider reconnects.
    next.activeTurnId = null;
  } else if (event.type === 'provider.connected') {
    next.provider = {
      connected: true,
      attempt: typeof event.data.attempt === 'number' ? event.data.attempt : 0,
    };
  } else if (event.type === 'error') {
    // A provider drop already drives the banner via provider.disconnected.
    // Appending a transcript bubble too would stack one up on every retry
    // cycle of an outage, burying the conversation under identical errors.
    if (dataString(event.data, 'code') === 'provider_disconnected') return next;
    next.messages = [
      ...state.messages,
      {
        id: `error-${event.sequence}`,
        role: 'error',
        text: dataString(event.data, 'message') || 'The provider reported an error',
      },
    ];
    // The busy-watchdog emits turn_stuck when a session has been BUSY
    // beyond the timeout.  Clear activeTurnId so the composer unlocks.
    if (dataString(event.data, 'code') === 'turn_stuck') {
      next.activeTurnId = null;
    }
  }
  return next;
}
