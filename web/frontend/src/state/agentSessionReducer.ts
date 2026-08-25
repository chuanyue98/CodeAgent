import type { AgentEvent, AgentSession, ApprovalRequest } from '../types/agent';

export interface ToolCallMeta {
  label: string;
  kind: string | null;
  status: 'running' | 'completed' | 'failed';
  /** Live stdout/stderr, for tools that stream it (`command.output`). */
  output?: string;
  /** Files this tool reported changing (`file.diff`). */
  files?: string[];
}

/**
 * Token and cost totals as last reported by the provider.
 *
 * The engines do not agree on what a `usage.updated` payload means: Codex
 * pushes a running total for the whole thread, while Claude emits one at the
 * end of each turn covering only that turn. Tokens therefore hold the latest
 * snapshot rather than a sum -- summing would double-count Codex badly --
 * while cost accumulates across the events that carry one, which is what
 * makes a per-turn number add up to a session number.
 */
export interface SessionUsage {
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens: number;
  cacheWriteTokens: number;
  costUsd: number | null;
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
  usage: SessionUsage | null;
}

export const initialAgentSessionState: AgentSessionState = {
  session: null,
  messages: [],
  activity: [],
  approvals: [],
  activeTurnId: null,
  lastSequence: 0,
  provider: null,
  usage: null,
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

/** Longest stretch of a command's output kept per tool row. */
const MAX_TOOL_OUTPUT = 4000;

/** Reads the first numeric field present, since each engine names them differently. */
function pickNumber(source: Record<string, unknown>, keys: string[]): number {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === 'number' && Number.isFinite(value)) return value;
  }
  return 0;
}

function usageFrom(
  data: Record<string, unknown>,
  previous: SessionUsage | null,
): SessionUsage {
  const usage = (
    typeof data.usage === 'object' && data.usage !== null ? data.usage : {}
  ) as Record<string, unknown>;
  const reportedCost =
    typeof data.cost === 'number' && Number.isFinite(data.cost)
      ? data.cost
      : null;
  return {
    inputTokens: pickNumber(usage, ['input_tokens', 'inputTokens', 'input']),
    outputTokens: pickNumber(usage, ['output_tokens', 'outputTokens', 'output']),
    cacheReadTokens: pickNumber(usage, [
      'cache_read_input_tokens',
      'cacheReadInputTokens',
      'cached_input_tokens',
      'cacheReadTokens',
    ]),
    cacheWriteTokens: pickNumber(usage, [
      'cache_creation_input_tokens',
      'cacheCreationInputTokens',
      'cacheWriteTokens',
    ]),
    costUsd:
      reportedCost === null
        ? (previous?.costUsd ?? null)
        : (previous?.costUsd ?? 0) + reportedCost,
  };
}

/**
 * Best-effort file paths out of a `file.diff` payload.
 *
 * The shape genuinely differs per engine -- Codex forwards whatever the
 * provider sent under `changes`/`diff`, CodeBuddy a list of content blocks --
 * so this collects the path-ish fields it recognizes rather than asserting a
 * schema. An unrecognized payload yields no names and the row still shows
 * that something changed.
 */
function diffFiles(value: unknown, found: string[] = []): string[] {
  if (Array.isArray(value)) {
    for (const item of value) diffFiles(item, found);
    return found;
  }
  if (typeof value === 'object' && value !== null) {
    const record = value as Record<string, unknown>;
    for (const key of ['path', 'file', 'filePath', 'file_path', 'uri']) {
      const candidate = record[key];
      if (typeof candidate === 'string' && candidate && !found.includes(candidate)) {
        found.push(candidate);
      }
    }
    for (const nested of Object.values(record)) {
      if (typeof nested === 'object' && nested !== null) diffFiles(nested, found);
    }
  }
  return found;
}

/** The message id `tool.started`/`tool.completed` gave this call. */
function toolMessageId(turnId: string | null | undefined, itemId: string): string {
  return `tool:${turnId || 'turn'}:${itemId}`;
}

function replayState(events: AgentEvent[]): AgentSessionState {
  let replay = initialAgentSessionState;
  for (const event of events) {
    replay = agentSessionReducer(replay, { type: 'event', event });
  }
  return replay;
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
    const replay = replayState(action.events);
    return {
      ...state,
      messages: replay.messages,
      // Replayed history carries the usage totals too; dropping them meant a
      // reconnect blanked the cost that had already been reported.
      usage: replay.usage ?? state.usage,
      lastSequence: action.events.at(-1)?.sequence ?? 0,
    };
  }
  if (action.type === 'history.prepend') {
    const page = replayState(action.events).messages;
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
  } else if (event.type === 'usage.updated') {
    next.usage = usageFrom(event.data, state.usage);
  } else if (event.type === 'command.output') {
    // Streamed stdout/stderr from a running command, keyed to the tool row
    // that started it. Kept trimmed: a build can emit megabytes.
    const commandId =
      event.itemId || dataString(event.data, 'commandId') || null;
    const delta = dataString(event.data, 'delta');
    if (!commandId || !delta) return next;
    const id = toolMessageId(event.turnId, commandId);
    next.messages = state.messages.map(message =>
      message.id === id && message.tool
        ? {
            ...message,
            tool: {
              ...message.tool,
              output: ((message.tool.output ?? '') + delta).slice(-MAX_TOOL_OUTPUT),
            },
          }
        : message);
  } else if (event.type === 'file.diff') {
    const itemId = event.itemId;
    const files = diffFiles(event.data.diff ?? event.data);
    if (!itemId) return next;
    const id = toolMessageId(event.turnId, itemId);
    next.messages = state.messages.map(message =>
      message.id === id && message.tool
        ? {
            ...message,
            tool: {
              ...message.tool,
              files: Array.from(new Set([...(message.tool.files ?? []), ...files])),
            },
          }
        : message);
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
