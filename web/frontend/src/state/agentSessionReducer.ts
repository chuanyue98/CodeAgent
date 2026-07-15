import type { AgentEvent, AgentSession, ApprovalRequest } from '../types/agent';

export interface AgentMessage {
  id: string;
  role: 'user' | 'assistant' | 'error';
  text: string;
  turnId?: string | null;
  pending?: boolean;
}

export interface AgentSessionState {
  session: AgentSession | null;
  messages: AgentMessage[];
  activity: AgentEvent[];
  approvals: ApprovalRequest[];
  activeTurnId: string | null;
  lastSequence: number;
}

export const initialAgentSessionState: AgentSessionState = {
  session: null,
  messages: [],
  activity: [],
  approvals: [],
  activeTurnId: null,
  lastSequence: 0,
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
  } else if (event.type === 'approval.request') {
    const approval = event.data.approval;
    if (approval && typeof approval === 'object') {
      next.approvals = [...state.approvals, approval as ApprovalRequest];
    }
  } else if (event.type === 'turn.completed') {
    next.activeTurnId = null;
  } else if (event.type === 'error') {
    next.messages = [
      ...state.messages,
      {
        id: `error-${event.sequence}`,
        role: 'error',
        text: dataString(event.data, 'message') || 'The provider reported an error',
      },
    ];
  }
  return next;
}
